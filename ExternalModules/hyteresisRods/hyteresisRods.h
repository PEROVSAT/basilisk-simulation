#ifndef HYSTERESIS_RODS_H
#define HYSTERESIS_RODS_H

#include "architecture/_GeneralModuleFiles/sys_model.h"
#include "simulation/dynamics/_GeneralModuleFiles/stateEffector.h"
#include "simulation/dynamics/_GeneralModuleFiles/stateData.h"
#include "architecture/messaging/messaging.h"
#include "architecture/msgPayloadDefC/MagneticFieldMsgPayload.h"
#include "architecture/msgPayloadDefC/CmdTorqueBodyMsgPayload.h"
#include "HysteresisDebugMsgPayload.h"
#include "architecture/utilities/bskLogging.h"
#include <Eigen/Dense>
#include <string>

class HysteresisRods : public SysModel, public StateEffector {
public:
    HysteresisRods();
    ~HysteresisRods();

    void Reset(uint64_t CurrentSimNanos);
    void UpdateState(uint64_t CurrentSimNanos);

    // StateEffector pure-virtual overrides
    void registerStates(DynParamManager& states) override;
    void linkInStates(DynParamManager& states) override;
    void computeDerivatives(double integTime,
                            Eigen::Vector3d rDDot_BN_N,
                            Eigen::Vector3d omegaDot_BN_B,
                            Eigen::Vector3d sigma_BN) override;

    // StateEffector optional overrides
    void updateEffectorMassProps(double integTime) override;
    void updateContributions(double integTime,
                             BackSubMatrices& backSubContr,
                             Eigen::Vector3d sigma_BN,
                             Eigen::Vector3d omega_BN_B,
                             Eigen::Vector3d g_N) override;
    void calcForceTorqueOnBody(double integTime,
                               Eigen::Vector3d omega_BN_B) override;

public:
    // Message interfaces
    ReadFunctor<MagneticFieldMsgPayload> magFieldInMsg;
    Message<CmdTorqueBodyMsgPayload> torqueLogOutMsg;       // Logging/plotting only
    Message<HysteresisDebugMsgPayload> hysteresisDebugOutMsg;

    // Jiles-Atherton material parameters
    double Ms;     // [A/m]  Saturation magnetization
    double a;      // [A/m]  Shape parameter
    double alpha;  // [-]    Interdomain coupling coefficient (Material)
    double k;      // [A/m]  Coercivity
    double c;      // [-]    Reversibility
    double M0;     // [A/m]  Initial magnetization

    // Rod geometry
    Eigen::Vector3d u_B; 
    double V;            
    double Nd;     // [-]    Demagnetization factor (Geometry)

    // Numerical smoothing (set from Python; tunable)
    double deltaSmoothing;  // [A/m/s] width of the tanh() used to smooth sgn(Hdot).
                            //         Smaller => sharper switch (more physical, but
                            //         more solver chatter). Larger => gentler switch.

    BSKLogger bskLogger;

private:
    // ODE state for magnetization, owned and integrated by Basilisk
    StateData* magState;

    // Linked spacecraft hub states (set in linkInStates)
    StateData* hubSigma;  // MRP attitude sigma_BN
    StateData* hubOmega;  // Angular velocity omega_BN_B

    // Cached body-frame field, computed in updateContributions and reused
    // in computeDerivatives (both are called within the same integrator sub-step)
    Eigen::Vector3d B_B_cached;

    // Previous N-frame field and timestamp for computing dB_N/dt numerically
    Eigen::Vector3d B_N_prev;
    double t_prev_s;

    // Finite-difference inertial field rate dot{B}_N, updated once per discrete
    // step in UpdateState and consumed inside computeDerivatives sub-steps.
    Eigen::Vector3d fieldInertialDot_N;

    // True until the first field sample is captured, so we don't emit a spurious
    // dot{B}_N spike on the first step (when B_N_prev is still zero-seeded).
    bool firstFieldRead;

    // Most-recently read discrete field message
    MagneticFieldMsgPayload magFieldMsgBuffer;

    // Cached JA debug quantities (updated in computeDerivatives, logged in UpdateState)
    double debug_H;
    double debug_Hdot;
    double debug_Man;
    double debug_He;
    double debug_chi_irr;
    double debug_dMdH;
    double debug_M;
};

#endif
