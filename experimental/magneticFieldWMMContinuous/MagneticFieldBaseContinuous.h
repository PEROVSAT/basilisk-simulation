#ifndef MAGNETIC_FIELD_BASE_H
#define MAGNETIC_FIELD_BASE_H

#include <Eigen/Dense>
#include <vector>
#include <string>
#include "architecture/utilities/bskLogging.h"
#include "architecture/messaging/messaging.h"
#include "architecture/msgPayloadDefC/SCStatesMsgPayload.h"
#include "architecture/msgPayloadDefC/MagneticFieldMsgPayload.h"

class MagneticFieldBase {
public:
    MagneticFieldBase();
    virtual ~MagneticFieldBase();

    void Reset(uint64_t CurrentSimNanos);
    void UpdateState(uint64_t CurrentSimNanos);

protected:
    virtual void customReset(uint64_t CurrentClock) = 0;
    virtual void evaluateMagneticFieldModel(MagneticFieldMsgPayload *msg, double currentTime) = 0;
    virtual void customSetEpochFromVariable() = 0;

public:
    ReadFunctor<SCStatesMsgPayload> scStateInMsg;          //!< spacecraft state input message
    Message<MagneticFieldMsgPayload> envOutMsg;            //!< magnetic field environment output message

    double envMinReach;                                    //!< [m] Minimum elevation for model validity
    double envMaxReach;                                    //!< [m] Maximum elevation for model validity
    double planetRadius;                                   //!< [m] Radius of the planet
    BSKLogger bskLogger;                                   //!< BSK Logging

protected:
    SCStatesMsgPayload scStateMsgBuffer;                   //!< buffer for the spacecraft state
    Eigen::Vector3d r_BP_P;                                //!< [m] position of the spacecraft relative to the planet
    Eigen::Vector3d v_BP_P;                                //!< [m/s] velocity of the spacecraft relative to the planet
};

#endif