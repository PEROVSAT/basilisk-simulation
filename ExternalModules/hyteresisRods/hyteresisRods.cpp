#include "hyteresisRods.h"
#include "architecture/utilities/avsEigenSupport.h"
#include "architecture/utilities/rigidBodyKinematics.h"
#include <cmath>

// Vacuum permeability mu_0 [T*m/A], used to convert the geomagnetic flux density
// B [T] into a magnetic field strength H [A/m] that is consistent with the
// Jiles-Atherton parameters a and k (which are expressed in A/m).
static const double MU0 = 1.25663706212e-6;

// ---------------------------------------------------------------------------
// Construction / destruction
// ---------------------------------------------------------------------------

HysteresisRods::HysteresisRods() {
    // Jiles-Atherton parameters — safe defaults until overridden from Python
    this->Ms    = 0.0;
    this->a     = 1.0;   // Avoid divide-by-zero in Langevin function
    this->alpha = 0.0;
    this->k     = 1.0;   // Avoid divide-by-zero in dM/dH
    this->c     = 0.0;
    this->M0    = 0.0;

    // Rod geometry
    this->u_B.setZero();
    this->V = 0.0;

    // Numerical smoothing default (A/m/s); override from Python if needed
    this->deltaSmoothing = 0.1;

    // Internal pointers
    this->magState = nullptr;
    this->hubSigma = nullptr;
    this->hubOmega = nullptr;

    // Field derivative bookkeeping
    this->B_N_prev.setZero();
    this->t_prev_s = 0.0;
    this->fieldInertialDot_N.setZero();
    this->firstFieldRead = true;
    this->B_B_cached.setZero();

    // StateEffector base-class force/torque containers
    this->forceOnBody_B.setZero();
    this->torqueOnBodyPntB_B.setZero();
}

HysteresisRods::~HysteresisRods() {}

// ---------------------------------------------------------------------------
// SysModel interface
// ---------------------------------------------------------------------------

void HysteresisRods::Reset(uint64_t CurrentSimNanos) {
    if (!this->magFieldInMsg.isLinked()) {
        this->bskLogger.bskLog(BSK_ERROR,
            "HysteresisRods: magFieldInMsg is not linked.");
    }
    if (this->Ms <= 0.0) {
        this->bskLogger.bskLog(BSK_WARNING,
            "HysteresisRods: Ms (saturation magnetization) is not set.");
    }
    if (this->V <= 0.0) {
        this->bskLogger.bskLog(BSK_WARNING,
            "HysteresisRods: Rod volume V is not set.");
    }
    if (this->u_B.norm() < 0.99) {
        this->bskLogger.bskLog(BSK_WARNING,
            "HysteresisRods: u_B does not appear to be a unit vector.");
    }

    // Seed the field-derivative tracker so the first dB/dt estimate is valid
    this->B_N_prev.setZero();
    this->t_prev_s = CurrentSimNanos * 1.0e-9;
    this->fieldInertialDot_N.setZero();
    this->firstFieldRead = true;

    // Initialise the ODE state to M0
    if (this->magState != nullptr) {
        Eigen::MatrixXd M_init(1, 1);
        M_init(0, 0) = this->M0;
        this->magState->setState(M_init);
    }
}

void HysteresisRods::UpdateState(uint64_t CurrentSimNanos) {
    // Read the discrete inertial magnetic field once per task timestep
    if (this->magFieldInMsg.isWritten()) {
        this->magFieldMsgBuffer = this->magFieldInMsg();
    }

    // Update the inertial-field finite difference:  $\dot{B}_N \approx \frac{B_N(t) - B_N(t_{prev})}{t - t_{prev}}$
    // The WMM field is zero-order-held between task steps, so evaluating this once
    // per discrete step (rather than per integrator sub-step) is the correct rate.
    double t_now_s = CurrentSimNanos * 1.0e-9;
    double dt_s = t_now_s - this->t_prev_s;
    Eigen::Vector3d fieldInertial_N(this->magFieldMsgBuffer.magField_N);
    if (this->firstFieldRead || dt_s <= 0.0) {
        // First sample (or non-advancing time): no valid rate yet, avoid a spike
        this->fieldInertialDot_N.setZero();
        this->firstFieldRead = false;
    } else {
        this->fieldInertialDot_N = (fieldInertial_N - this->B_N_prev) / dt_s;
    }
    this->B_N_prev = fieldInertial_N;
    this->t_prev_s = t_now_s;

    // Write current torque for logging / plotting
    CmdTorqueBodyMsgPayload torqueMsg = {};
    eigenVector3d2CArray(this->torqueOnBodyPntB_B, torqueMsg.torqueRequestBody);
    this->torqueLogOutMsg.write(&torqueMsg, this->moduleID, CurrentSimNanos);
}

// ---------------------------------------------------------------------------
// StateEffector pure-virtual interface
// ---------------------------------------------------------------------------

void HysteresisRods::registerStates(DynParamManager& states) {
    // Register a 1×1 state for the scalar magnetization M [A/m].
    // Using ModelTag keeps the name unique when multiple instances are attached.
    this->magState = states.registerState(1, 1, "hysteresisM_" + this->ModelTag);
}

void HysteresisRods::linkInStates(DynParamManager& states) {
    // stateNameOfSigma / stateNameOfOmega are protected StateEffector members
    // automatically set (and spacecraft-prefixed) when the effector is attached.
    this->hubSigma = states.getStateObject(this->stateNameOfSigma);
    this->hubOmega = states.getStateObject(this->stateNameOfOmega);
}

void HysteresisRods::computeDerivatives(double integTime,
                                         Eigen::Vector3d rDDot_BN_N,
                                         Eigen::Vector3d omegaDot_BN_B,
                                         Eigen::Vector3d sigma_BN) {
    // === Field kinematics =================================================

    // $[BN]$: direction cosine matrix from the current integrator sub-step MRP.
    double dcm_BN_array[3][3];
    MRP2C(sigma_BN.data(), dcm_BN_array);
    Eigen::Matrix3d dcm_BN;
    for (int i = 0; i < 3; i++)
        for (int j = 0; j < 3; j++)
            dcm_BN(i, j) = dcm_BN_array[i][j];

    // $\omega_{B/N}$: body angular velocity from the continuous hub state.
    Eigen::Vector3d omega_BN_B = this->hubOmega->getState();

    // $B_N$ (discrete, ZOH) and $\dot{B}_N$ (finite difference from UpdateState).
    Eigen::Vector3d fieldInertial_N(this->magFieldMsgBuffer.magField_N);
    Eigen::Vector3d fieldInertialDot_N = this->fieldInertialDot_N;

    // $B_B = [BN]\,B_N$
    Eigen::Vector3d fieldBody_B = dcm_BN * fieldInertial_N;
    this->B_B_cached = fieldBody_B;

    // $\dot{B}_B = [BN]\,\dot{B}_N - \omega_{B/N} \times B_B$  (transport theorem)
    Eigen::Vector3d fieldBodyDot_B = dcm_BN * fieldInertialDot_N
                                     - omega_BN_B.cross(fieldBody_B);

    // $H = (B_B \cdot \hat{u})/\mu_0$ and $\dot{H} = (\dot{B}_B \cdot \hat{u})/\mu_0$
    double axialFieldH     = fieldBody_B.dot(this->u_B) / MU0;
    double axialFieldRateH = fieldBodyDot_B.dot(this->u_B) / MU0;

    // === Jiles-Atherton ODE ==============================================

    // $M$: current magnetization from the ODE state.
    double magnetization = this->magState->getState()(0, 0);

    // $H_e = H + \alpha M$: effective field seen by the magnetic domains.
    double effectiveFieldHe = axialFieldH + this->alpha * magnetization;

    // $M_{an} = M_s\left(\coth(H_e/a) - a/H_e\right)$ and its slope
    // $\frac{dM_{an}}{dH_e} = \frac{M_s}{a}\left(1 - \coth^2(H_e/a) + (a/H_e)^2\right)$.
    // Near $H_e=0$ both are removable singularities; use the small-argument
    // Langevin expansion $M_{an}\to M_s x/3$, $dM_{an}/dH_e \to M_s/(3a)$.
    double anhystereticMag;
    double anhystereticSlope;  // dM_an/dH_e
    double x = effectiveFieldHe / this->a;
    const double xSmall = 1.0e-4;
    if (std::fabs(x) < xSmall) {
        anhystereticMag   = this->Ms * x / 3.0;
        anhystereticSlope = this->Ms / (3.0 * this->a);
    } else {
        double cothx = 1.0 / std::tanh(x);
        anhystereticMag   = this->Ms * (cothx - 1.0 / x);
        anhystereticSlope = (this->Ms / this->a)
                            * (1.0 - cothx * cothx + 1.0 / (x * x));
    }

    // $\delta = \tanh(\dot{H}/\varepsilon) \approx \mathrm{sgn}(\dot{H})$
    // Smoothed to keep the derivative continuous and stop solver chattering.
    double fieldDirection = std::tanh(axialFieldRateH / this->deltaSmoothing);

    // Irreversible differential susceptibility (w.r.t. $H_e$):
    // $\chi_{irr} = \frac{M_{an}-M}{k\delta - \alpha(M_{an}-M)}$
    // Gated to zero when $\delta(M_{an}-M) \le 0$ (field pushing M unphysically),
    // and its denominator is floored away from zero.
    double manMinusM = anhystereticMag - magnetization;
    double chiIrr;
    if (fieldDirection * manMinusM <= 0.0) {
        chiIrr = 0.0;
    } else {
        double denom = this->k * fieldDirection - this->alpha * manMinusM;
        const double denomFloor = 1.0e-12;
        if (std::fabs(denom) < denomFloor) {
            denom = std::copysign(denomFloor, denom);
        }
        chiIrr = manMinusM / denom;
    }

    // Full JA total susceptibility:
    // $\frac{dM}{dH} = \frac{K}{1-\alpha K}$, with
    // $K = (1-c)\,\chi_{irr} + c\,\frac{dM_{an}}{dH_e}$.
    double K = (1.0 - this->c) * chiIrr + this->c * anhystereticSlope;
    double couplingDenom = 1.0 - this->alpha * K;
    const double couplingFloor = 1.0e-12;
    if (std::fabs(couplingDenom) < couplingFloor) {
        couplingDenom = std::copysign(couplingFloor, couplingDenom);
    }
    double dMag_dField = K / couplingDenom;

    // $\frac{dM}{dt} = \frac{dM}{dH}\,\dot{H}$: value handed to the integrator.
    double magnetizationRate = dMag_dField * axialFieldRateH;

    Eigen::MatrixXd Mdot(1, 1);
    Mdot(0, 0) = magnetizationRate;
    this->magState->setDerivative(Mdot);
}

// ---------------------------------------------------------------------------
// StateEffector optional overrides
// ---------------------------------------------------------------------------

void HysteresisRods::updateEffectorMassProps(double integTime) {
    // Hysteresis rods are rigid; they contribute no mass or inertia changes
    return;
}

void HysteresisRods::updateContributions(double integTime,
                                          BackSubMatrices& backSubContr,
                                          Eigen::Vector3d sigma_BN,
                                          Eigen::Vector3d omega_BN_B,
                                          Eigen::Vector3d g_N) {
    // Called at every integrator sub-step with the current continuous states.
    // This is where the torque enters the spacecraft equations of motion.

    // 1. Build [BN] from the sub-step MRP attitude
    double dcm_BN_array[3][3];
    MRP2C(sigma_BN.data(), dcm_BN_array);
    Eigen::Matrix3d dcm_BN;
    for (int i = 0; i < 3; i++)
        for (int j = 0; j < 3; j++)
            dcm_BN(i, j) = dcm_BN_array[i][j];

    // 2. Rotate the discrete inertial field into the body frame
    Eigen::Vector3d B_N(this->magFieldMsgBuffer.magField_N);
    this->B_B_cached = dcm_BN * B_N;

    // 3. Retrieve the current magnetization from the ODE state
    double M = this->magState->getState()(0, 0);

    // 4. Rod dipole moment in body frame: m_rod = M * V * u_hat
    Eigen::Vector3d m_rod = (M * this->V) * this->u_B;

    // 5. Magnetic torque in body frame: tau_B = m_rod x B_B
    Eigen::Vector3d tau_B = m_rod.cross(this->B_B_cached);

    // 6. Contribute as an external torque into the back-substitution solver.
    //    Matrices A–D remain zero (no inertial coupling from the rods).
    backSubContr.vecRot += tau_B;
}

void HysteresisRods::calcForceTorqueOnBody(double integTime,
                                            Eigen::Vector3d omega_BN_B) {
    // Called once per discrete timestep after integration completes.
    // Recompute the torque from the settled state for logging/output purposes.
    this->forceOnBody_B.setZero();
    this->torqueOnBodyPntB_B.setZero();

    // 1. Settled attitude from the fully integrated state
    Eigen::Vector3d sigma_BN = this->hubSigma->getState();

    double dcm_BN_array[3][3];
    MRP2C(sigma_BN.data(), dcm_BN_array);
    Eigen::Matrix3d dcm_BN;
    for (int i = 0; i < 3; i++)
        for (int j = 0; j < 3; j++)
            dcm_BN(i, j) = dcm_BN_array[i][j];

    Eigen::Vector3d B_N(this->magFieldMsgBuffer.magField_N);
    Eigen::Vector3d B_B = dcm_BN * B_N;

    // 2. Current magnetization
    double M = this->magState->getState()(0, 0);

    // 3. Torque: tau_B = (M * V * u_hat) x B_B
    Eigen::Vector3d m_rod = (M * this->V) * this->u_B;
    this->torqueOnBodyPntB_B = m_rod.cross(B_B);
}
