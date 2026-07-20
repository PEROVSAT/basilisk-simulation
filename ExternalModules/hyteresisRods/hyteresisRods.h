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

/*! @brief Hysteresis-rod StateEffector using the Flatley–Henretty model
 *         in the Burton AAS 12-169 S-substitution form (p=2, q0=0).
 *
 *  Material parameters (Bs, Br, Hc) are *effective as-installed* values that
 *  already fold in rod L/D demagnetization. The ODE state is the substituted
 *  flux variable S = tan(π B / (2 Bs)).
 */
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
    Message<CmdTorqueBodyMsgPayload> torqueLogOutMsg;
    Message<HysteresisDebugMsgPayload> hysteresisDebugOutMsg;

    // Flatley–Henretty material parameters (effective / as-installed)
    double Bs;     // [T]    Saturation flux density
    double Br;     // [T]    Remanence flux density
    double Hc;     // [A/m]  Coercivity
    double M0;     // [A/m]  Initial magnetization (seeds S at Reset)

    // Rod geometry
    Eigen::Vector3d u_B;
    double V;

    BSKLogger bskLogger;

private:
    // Cached shaping factor k = (1/Hc) tan(π Br / (2 Bs)), set in Reset
    double kShape;

    // Helpers
    double fluxFromS(double S) const;
    double magnetizationFromSB(double S, double H) const;
    void projectS(double H, double& S) const;

    // ODE state for substituted flux variable S [-]
    StateData* magState;

    // Linked spacecraft hub states
    StateData* hubSigma;
    StateData* hubOmega;

    // Cached body-frame field
    Eigen::Vector3d B_B_cached;

    // Previous N-frame field and timestamp
    Eigen::Vector3d B_N_prev;
    double t_prev_s;

    // Finite-difference inertial field rate
    Eigen::Vector3d fieldInertialDot_N;

    bool firstFieldRead;
    MagneticFieldMsgPayload magFieldMsgBuffer;

    // Cached FH debug quantities
    double debug_H;
    double debug_Hdot;
    double debug_B;
    double debug_S;
    double debug_dBdH;
    double debug_M;
};

#endif
