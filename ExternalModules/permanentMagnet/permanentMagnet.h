#ifndef PERMANENT_MAGNET_H
#define PERMANENT_MAGNET_H

#include "architecture/_GeneralModuleFiles/sys_model.h"
#include "simulation/dynamics/_GeneralModuleFiles/dynamicEffector.h"
#include "simulation/dynamics/_GeneralModuleFiles/stateData.h"
#include "architecture/messaging/messaging.h"
#include "architecture/msgPayloadDefC/MagneticFieldMsgPayload.h"
#include "architecture/msgPayloadDefC/CmdTorqueBodyMsgPayload.h"
#include "architecture/utilities/bskLogging.h"
#include <Eigen/Dense>

class PermanentMagnet : public SysModel, public DynamicEffector {
public:
    PermanentMagnet();
    ~PermanentMagnet();

    void Reset(uint64_t CurrentSimNanos);
    void UpdateState(uint64_t CurrentSimNanos);

    // DynamicEffector required methods
    void linkInStates(DynParamManager& states);
    void computeStateContribution(double integTime);
    void computeForceTorque(double integTime, double timeStep);

public:
    // Inputs and Outputs
    ReadFunctor<MagneticFieldMsgPayload> magFieldInMsg;
    Message<CmdTorqueBodyMsgPayload> cmdTorqueOutMsg;

    // Configurable Python Parameters
    Eigen::Vector3d magDipole_B; // [A*m^2] Permanent dipole moment vector in Body frame
    BSKLogger bskLogger;

private:
    StateData *hubSigma; // Pointer to the continuous attitude state
    MagneticFieldMsgPayload magFieldMsgBuffer;
};

#endif
