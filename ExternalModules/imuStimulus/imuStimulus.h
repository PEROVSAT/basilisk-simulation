#ifndef IMU_STIMULUS_H
#define IMU_STIMULUS_H

#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

#include "architecture/_GeneralModuleFiles/sys_model.h"
#include "architecture/messaging/messaging.h"
#include "architecture/msgPayloadDefC/SCStatesMsgPayload.h"
#include "architecture/utilities/bskLogging.h"

#include "simulation/frame/frame.h"

/*! Fills a perovsat-protocol IMU stimulus sample from spacecraft truth.
 *
 * Each tick it reads the spacecraft state, fills a psp_sample_imu_stimulus
 * (gyro = omega_BN_B, accel = non-conservative specific force), and stores it
 * in a psp_sample as the PSP_SAMPLE_IMU_STIMULUS arm. Read-only: nothing feeds
 * back into the dynamics. Add it after the spacecraft so it sees this tick's
 * propagated state.
 */
class ImuStimulus : public SysModel {
public:
    ImuStimulus();

    void Reset(uint64_t CurrentSimNanos);
    void UpdateState(uint64_t CurrentSimNanos);

    /*! True once UpdateState has filled a sample. */
    bool hasSample() const;
    /*! psp_sample_kind of the stored sample (0 before the first tick). */
    int getKind() const;
    uint32_t getSequence() const;
    /*! [m/s^2] Body-frame specific force, as stored (float32). */
    double getAccel(int axis) const;
    /*! [rad/s] Body-frame angular rate, as stored (float32). */
    double getGyro(int axis) const;
    bool getTemperaturePresent() const;
    double getTemperature() const;

    /*! The stored sample as a serialized Sample frame. Empty before the
     *  first tick or if the codec rejects it. */
    std::vector<uint8_t> sampleFrame(uint8_t destination, uint8_t source,
                                     uint64_t timeSentNs) const;

    ReadFunctor<SCStatesMsgPayload> scStateInMsg;  //!< Spacecraft truth state
    BSKLogger bskLogger;

private:
    psp_sample sample;
    uint32_t nextSequence;
    bool stepped;  //!< False until the first tick after Reset
};

/*! A serialized Command/GetStatus frame. */
std::vector<uint8_t> pspGetStatusFrame(uint8_t destination, uint8_t source,
                                       uint64_t timeSentNs, uint32_t requestId);

/*! Decode a frame with the protocol codec and describe it on one line, or
 *  explain why it does not decode. */
std::string pspDescribeFrame(const uint8_t *data, size_t length);

#endif
