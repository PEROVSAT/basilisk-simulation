#include "hyteresisRods.h"
#include "architecture/utilities/avsEigenSupport.h"
#include "architecture/utilities/rigidBodyKinematics.h"
#include <cmath>

// Vacuum permeability mu_0 [T*m/A]
static const double MU0 = 1.25663706212e-6;
static const double PI = 3.14159265358979323846;

// ---------------------------------------------------------------------------
// Construction / destruction
// ---------------------------------------------------------------------------

HysteresisRods::HysteresisRods() {
    // Flatley–Henretty parameters — safe defaults until overridden from Python
    this->Bs = 0.75;
    this->Br = 0.001;
    this->Hc = 5.0;
    this->M0 = 0.0;
    this->kShape = 0.0;

    // Rod geometry
    this->u_B.setZero();
    this->V = 0.0;

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

    // Debug payload defaults
    this->debug_H = 0.0;
    this->debug_Hdot = 0.0;
    this->debug_B = 0.0;
    this->debug_S = 0.0;
    this->debug_dBdH = 0.0;
    this->debug_M = 0.0;

    // StateEffector base-class force/torque containers
    this->forceOnBody_B.setZero();
    this->torqueOnBodyPntB_B.setZero();
}

HysteresisRods::~HysteresisRods() {}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

double HysteresisRods::fluxFromS(double S) const {
    return (2.0 * this->Bs / PI) * std::atan(S);
}

double HysteresisRods::magnetizationFromSB(double S, double H) const {
    return this->fluxFromS(S) / MU0 - H;
}

void HysteresisRods::projectS(double H, double& S) const {
    // Bound S to the major-loop strip [k(H−Hc), k(H+Hc)] (Burton AAS 12-169).
    const double S_lo = this->kShape * (H - this->Hc);
    const double S_hi = this->kShape * (H + this->Hc);
    if (S < S_lo) {
        S = S_lo;
    } else if (S > S_hi) {
        S = S_hi;
    }
}

// ---------------------------------------------------------------------------
// SysModel interface
// ---------------------------------------------------------------------------

void HysteresisRods::Reset(uint64_t CurrentSimNanos) {
    if (!this->magFieldInMsg.isLinked()) {
        this->bskLogger.bskLog(BSK_ERROR,
            "HysteresisRods: magFieldInMsg is not linked.");
    }
    if (this->Bs <= 0.0) {
        this->bskLogger.bskLog(BSK_WARNING,
            "HysteresisRods: Bs (saturation flux density) is not set.");
    }
    if (this->Br <= 0.0 || this->Br >= this->Bs) {
        this->bskLogger.bskLog(BSK_WARNING,
            "HysteresisRods: Br must satisfy 0 < Br < Bs.");
    }
    if (this->Hc <= 0.0) {
        this->bskLogger.bskLog(BSK_WARNING,
            "HysteresisRods: Hc (coercivity) is not set.");
    }
    if (this->V <= 0.0) {
        this->bskLogger.bskLog(BSK_WARNING,
            "HysteresisRods: Rod volume V is not set.");
    }
    if (this->u_B.norm() < 0.99) {
        this->bskLogger.bskLog(BSK_WARNING,
            "HysteresisRods: u_B does not appear to be a unit vector.");
    }

    // Shaping factor k = (1/Hc) tan(π Br / (2 Bs))
    this->kShape = (1.0 / this->Hc)
                   * std::tan((PI / 2.0) * (this->Br / this->Bs));

    // Seed field-derivative tracker
    this->B_N_prev.setZero();
    this->t_prev_s = CurrentSimNanos * 1.0e-9;
    this->fieldInertialDot_N.setZero();
    this->firstFieldRead = true;

    // Initialise the ODE state S from M0 (at H ≈ 0).
    // S = tan(π B / (2 Bs)) with B = μ0 (H + M0) ≈ μ0 M0.
    if (this->magState != nullptr) {
        double B_seed = MU0 * this->M0;
        const double B_cap = 0.999 * this->Bs;
        if (B_seed > B_cap) {
            B_seed = B_cap;
        } else if (B_seed < -B_cap) {
            B_seed = -B_cap;
        }
        double S0 = std::tan((PI / 2.0) * (B_seed / this->Bs));
        Eigen::MatrixXd S_init(1, 1);
        S_init(0, 0) = S0;
        this->magState->setState(S_init);
    }
}

void HysteresisRods::UpdateState(uint64_t CurrentSimNanos) {
    // Read the discrete inertial magnetic field once per task timestep
    if (this->magFieldInMsg.isWritten()) {
        this->magFieldMsgBuffer = this->magFieldInMsg();
    }

    // Inertial-field finite difference (ZOH WMM → rate once per discrete step)
    double t_now_s = CurrentSimNanos * 1.0e-9;
    double dt_s = t_now_s - this->t_prev_s;
    Eigen::Vector3d fieldInertial_N(this->magFieldMsgBuffer.magField_N);
    if (this->firstFieldRead || dt_s <= 0.0) {
        this->fieldInertialDot_N.setZero();
        this->firstFieldRead = false;
    } else {
        this->fieldInertialDot_N = (fieldInertial_N - this->B_N_prev) / dt_s;
    }
    this->B_N_prev = fieldInertial_N;
    this->t_prev_s = t_now_s;

    // Project S onto the major-loop strip at the settled attitude / field
    if (this->magState != nullptr && this->hubSigma != nullptr) {
        Eigen::Vector3d sigma_BN = this->hubSigma->getState();
        double dcm_BN_array[3][3];
        MRP2C(sigma_BN.data(), dcm_BN_array);
        Eigen::Matrix3d dcm_BN;
        for (int i = 0; i < 3; i++)
            for (int j = 0; j < 3; j++)
                dcm_BN(i, j) = dcm_BN_array[i][j];
        Eigen::Vector3d B_B = dcm_BN * fieldInertial_N;
        double H = B_B.dot(this->u_B) / MU0;

        double S = this->magState->getState()(0, 0);
        this->projectS(H, S);
        Eigen::MatrixXd S_proj(1, 1);
        S_proj(0, 0) = S;
        this->magState->setState(S_proj);
    }

    // Torque log
    CmdTorqueBodyMsgPayload torqueMsg = {};
    eigenVector3d2CArray(this->torqueOnBodyPntB_B, torqueMsg.torqueRequestBody);
    this->torqueLogOutMsg.write(&torqueMsg, this->moduleID, CurrentSimNanos);

    // FH debug state
    HysteresisDebugMsgPayload debugMsg = {};
    debugMsg.H = this->debug_H;
    debugMsg.Hdot = this->debug_Hdot;
    debugMsg.B = this->debug_B;
    debugMsg.S = this->debug_S;
    debugMsg.dBdH = this->debug_dBdH;
    debugMsg.M = this->debug_M;
    this->hysteresisDebugOutMsg.write(&debugMsg, this->moduleID, CurrentSimNanos);
}

// ---------------------------------------------------------------------------
// StateEffector pure-virtual interface
// ---------------------------------------------------------------------------

void HysteresisRods::registerStates(DynParamManager& states) {
    // Register a 1×1 state for the substituted flux variable S [-].
    this->magState = states.registerState(1, 1, "hysteresisS_" + this->ModelTag);
}

void HysteresisRods::linkInStates(DynParamManager& states) {
    this->hubSigma = states.getStateObject(this->stateNameOfSigma);
    this->hubOmega = states.getStateObject(this->stateNameOfOmega);
}

void HysteresisRods::computeDerivatives(double integTime,
                                         Eigen::Vector3d rDDot_BN_N,
                                         Eigen::Vector3d omegaDot_BN_B,
                                         Eigen::Vector3d sigma_BN) {
    // === Field kinematics =================================================

    double dcm_BN_array[3][3];
    MRP2C(sigma_BN.data(), dcm_BN_array);
    Eigen::Matrix3d dcm_BN;
    for (int i = 0; i < 3; i++)
        for (int j = 0; j < 3; j++)
            dcm_BN(i, j) = dcm_BN_array[i][j];

    Eigen::Vector3d omega_BN_B = this->hubOmega->getState();
    Eigen::Vector3d fieldInertial_N(this->magFieldMsgBuffer.magField_N);
    Eigen::Vector3d fieldInertialDot_N = this->fieldInertialDot_N;

    Eigen::Vector3d fieldBody_B = dcm_BN * fieldInertial_N;
    this->B_B_cached = fieldBody_B;

    Eigen::Vector3d fieldBodyDot_B = dcm_BN * fieldInertialDot_N
                                     - omega_BN_B.cross(fieldBody_B);

    double axialFieldH     = fieldBody_B.dot(this->u_B) / MU0;
    double axialFieldRateH = fieldBodyDot_B.dot(this->u_B) / MU0;

    // === Flatley–Henretty / Burton S-ODE ==================================

    // computeDerivatives is called once per RK4 stage (k1..k4) with a
    // sub-step state the integrator constructed. It MUST behave as a pure
    // function of that state: calling magState->setState(...) here would
    // silently overwrite the integrator's sub-step value in place, so later
    // stages build their increments on a state the integrator never asked
    // for. Any out-of-strip correction belongs in UpdateState (once per full
    // discrete step, via projectS), not here.
    //
    // No explicit "snap" is needed regardless: if S sits outside the strip,
    // the f-clamp below saturates dS/dH toward the value that pulls S back
    // in (or, if H is moving away, holds dS/dH at 0 until the strip catches
    // up to S), so the ODE is self-correcting.
    double S = this->magState->getState()(0, 0);

    double sigma;
    if (axialFieldRateH > 0.0) {
        sigma = 1.0;
    } else if (axialFieldRateH < 0.0) {
        sigma = -1.0;
    } else {
        sigma = 0.0;
    }

    // f = 1 on the active boundary, 0 on the opposite boundary
    double f = (sigma * (axialFieldH - S / this->kShape) + this->Hc)
               / (2.0 * this->Hc);
    if (f < 0.0) {
        f = 0.0;
    } else if (f > 1.0) {
        f = 1.0;
    }

    double dSdH = this->kShape * f * f;
    double Sdot = dSdH * axialFieldRateH;

    // Recover B, dB/dH, M for debug
    double B_rod = this->fluxFromS(S);
    double dBdS = (2.0 * this->Bs / PI) / (1.0 + S * S);
    double dBdH = dBdS * dSdH;
    double M = B_rod / MU0 - axialFieldH;

    this->debug_H = axialFieldH;
    this->debug_Hdot = axialFieldRateH;
    this->debug_B = B_rod;
    this->debug_S = S;
    this->debug_dBdH = dBdH;
    this->debug_M = M;

    Eigen::MatrixXd SdotMat(1, 1);
    SdotMat(0, 0) = Sdot;
    this->magState->setDerivative(SdotMat);
}

void HysteresisRods::updateEffectorMassProps(double integTime) {
    return;
}

void HysteresisRods::updateContributions(double integTime,
                                          BackSubMatrices& backSubContr,
                                          Eigen::Vector3d sigma_BN,
                                          Eigen::Vector3d omega_BN_B,
                                          Eigen::Vector3d g_N) {
    double dcm_BN_array[3][3];
    MRP2C(sigma_BN.data(), dcm_BN_array);
    Eigen::Matrix3d dcm_BN;
    for (int i = 0; i < 3; i++)
        for (int j = 0; j < 3; j++)
            dcm_BN(i, j) = dcm_BN_array[i][j];

    Eigen::Vector3d B_N(this->magFieldMsgBuffer.magField_N);
    this->B_B_cached = dcm_BN * B_N;

    double H = this->B_B_cached.dot(this->u_B) / MU0;
    double S = this->magState->getState()(0, 0);
    this->projectS(H, S);

    double M = this->magnetizationFromSB(S, H);
    if (std::isnan(M) || std::isinf(M)) {
        Eigen::MatrixXd S_reset(1, 1);
        S_reset(0, 0) = this->kShape * H;
        this->magState->setState(S_reset);
        return;
    }

    Eigen::Vector3d m_rod = (M * this->V) * this->u_B;
    // Passive dipole torque; passive damping comes from M lagging H.
    Eigen::Vector3d tau_B = m_rod.cross(this->B_B_cached);

    if (std::isnan(tau_B.norm()) || std::isinf(tau_B.norm())) {
        tau_B.setZero();
        return;
    }

    backSubContr.vecRot += tau_B;
}

void HysteresisRods::calcForceTorqueOnBody(double integTime,
                                            Eigen::Vector3d omega_BN_B) {
    this->forceOnBody_B.setZero();
    this->torqueOnBodyPntB_B.setZero();

    Eigen::Vector3d sigma_BN = this->hubSigma->getState();

    double dcm_BN_array[3][3];
    MRP2C(sigma_BN.data(), dcm_BN_array);
    Eigen::Matrix3d dcm_BN;
    for (int i = 0; i < 3; i++)
        for (int j = 0; j < 3; j++)
            dcm_BN(i, j) = dcm_BN_array[i][j];

    Eigen::Vector3d B_N(this->magFieldMsgBuffer.magField_N);
    Eigen::Vector3d B_B = dcm_BN * B_N;

    double H = B_B.dot(this->u_B) / MU0;
    double S = this->magState->getState()(0, 0);
    this->projectS(H, S);

    double M = this->magnetizationFromSB(S, H);
    if (std::isnan(M) || std::isinf(M)) {
        Eigen::MatrixXd S_reset(1, 1);
        S_reset(0, 0) = this->kShape * H;
        this->magState->setState(S_reset);
        return;
    }

    Eigen::Vector3d m_rod = (M * this->V) * this->u_B;
    this->torqueOnBodyPntB_B = m_rod.cross(B_B);

    if (std::isnan(this->torqueOnBodyPntB_B.norm())
        || std::isinf(this->torqueOnBodyPntB_B.norm())) {
        this->torqueOnBodyPntB_B.setZero();
    }
}
