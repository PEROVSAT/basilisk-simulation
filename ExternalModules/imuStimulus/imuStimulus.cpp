#include "imuStimulus.h"

#include <cinttypes>
#include <cstdio>

namespace {

// psp_sample_imu_stimulus rejects this sequence value.
constexpr uint32_t kSequenceInvalid = 0xFFFFFFFFu;

std::vector<uint8_t> serialize(const psp_frame &frame) {
    std::vector<uint8_t> bytes(PSP_FRAME_MAX_SERIALIZED_SIZE);
    psp_writer writer;
    psp_writer_init(&writer, bytes.data(), bytes.size());
    if (psp_frame_serialize(&writer, &frame) != PSP_OK) {
        return {};
    }
    bytes.resize(psp_writer_position(&writer));
    return bytes;
}

psp_frame prefix(uint8_t destination, uint8_t source, uint64_t timeSentNs,
                 psp_frame_kind kind) {
    psp_frame frame{};
    frame.version = PSP_SIMULATION_VERSION;
    frame.destination = destination;
    frame.source = source;
    frame.time_sent = timeSentNs;
    frame.time_received = 0;  // Only the receiver records this.
    frame.kind = kind;
    return frame;
}

}  // namespace

ImuStimulus::ImuStimulus() : sample{}, nextSequence(0), stepped(false) {}

void ImuStimulus::Reset(uint64_t CurrentSimNanos) {
    if (!this->scStateInMsg.isLinked()) {
        this->bskLogger.bskLog(BSK_ERROR, "ImuStimulus.scStateInMsg was not linked.");
    }
    this->sample = psp_sample{};
    this->nextSequence = 0;
    this->stepped = false;
}

void ImuStimulus::UpdateState(uint64_t CurrentSimNanos) {
    const SCStatesMsgPayload state = this->scStateInMsg();

    // Fill the IMU arm completely from Basilisk truth.
    psp_sample_imu_stimulus imu{};
    imu.sequence = this->nextSequence;
    for (int axis = 0; axis < 3; ++axis) {
        // An accelerometer reads specific force: the non-gravitational part.
        // Basilisk derives it from the last step's accumulated delta-v, so it
        // is 0/0 = NaN until the first step; report no specific force then.
        const double accel = state.nonConservativeAccelpntB_B[axis];
        imu.accel_m_s2[axis] = this->stepped ? static_cast<float>(accel) : 0.0f;
        imu.gyro_rad_s[axis] = static_cast<float>(state.omega_BN_B[axis]);
    }
    this->stepped = true;
    // Basilisk does not model IMU temperature; the emulator uses its default.
    imu.temperature_present = 0;
    imu.temperature_c = 0.0f;

    // Store it as the sample's IMU stimulus subtype.
    this->sample.kind = PSP_SAMPLE_IMU_STIMULUS;
    this->sample.body.imu_stimulus = imu;

    this->nextSequence = this->nextSequence + 1 == kSequenceInvalid ? 0 : this->nextSequence + 1;
}

bool ImuStimulus::hasSample() const {
    return this->sample.kind == PSP_SAMPLE_IMU_STIMULUS;
}

int ImuStimulus::getKind() const {
    return static_cast<int>(this->sample.kind);
}

uint32_t ImuStimulus::getSequence() const {
    return this->sample.body.imu_stimulus.sequence;
}

double ImuStimulus::getAccel(int axis) const {
    return (axis >= 0 && axis < 3) ? this->sample.body.imu_stimulus.accel_m_s2[axis] : 0.0;
}

double ImuStimulus::getGyro(int axis) const {
    return (axis >= 0 && axis < 3) ? this->sample.body.imu_stimulus.gyro_rad_s[axis] : 0.0;
}

bool ImuStimulus::getTemperaturePresent() const {
    return this->sample.body.imu_stimulus.temperature_present != 0;
}

double ImuStimulus::getTemperature() const {
    return this->sample.body.imu_stimulus.temperature_c;
}

std::vector<uint8_t> ImuStimulus::sampleFrame(uint8_t destination, uint8_t source,
                                              uint64_t timeSentNs) const {
    if (!this->hasSample()) {
        return {};
    }
    psp_frame frame = prefix(destination, source, timeSentNs, PSP_FRAME_SAMPLE);
    frame.body.sample = this->sample;
    return serialize(frame);
}

std::vector<uint8_t> pspGetStatusFrame(uint8_t destination, uint8_t source,
                                       uint64_t timeSentNs, uint32_t requestId) {
    psp_frame frame = prefix(destination, source, timeSentNs, PSP_FRAME_COMMAND);
    frame.body.command.kind = PSP_COMMAND_GET_STATUS;
    frame.body.command.request_id = requestId;
    return serialize(frame);
}

std::string pspDescribeFrame(const uint8_t *data, size_t length) {
    psp_frame frame{};
    psp_reader reader;
    psp_reader_init(&reader, data, length);
    const psp_status decoded = psp_frame_deserialize(&reader, &frame);
    if (decoded != PSP_OK || psp_reader_finish(&reader) != PSP_OK) {
        char text[64];
        std::snprintf(text, sizeof(text), "undecodable frame (%zu bytes, status %d)",
                      length, static_cast<int>(decoded));
        return text;
    }

    char head[48];
    std::snprintf(head, sizeof(head), "src=%u dst=%u ", frame.source, frame.destination);
    char body[160];
    switch (frame.kind) {
    case PSP_FRAME_SAMPLE: {
        const psp_sample_imu_stimulus &imu = frame.body.sample.body.imu_stimulus;
        std::snprintf(body, sizeof(body),
                      "sample imu_stimulus seq=%" PRIu32 " gyro=[%.6g %.6g %.6g] rad/s",
                      imu.sequence, imu.gyro_rad_s[0], imu.gyro_rad_s[1], imu.gyro_rad_s[2]);
        break;
    }
    case PSP_FRAME_COMMAND:
        std::snprintf(body, sizeof(body), "command %s request=%" PRIu32,
                      frame.body.command.kind == PSP_COMMAND_UTC_SYNC ? "utc_sync" : "get_status",
                      frame.body.command.request_id);
        break;
    case PSP_FRAME_LOG: {
        const psp_log &log = frame.body.log;
        switch (log.kind) {
        case PSP_LOG_STATUS: {
            const psp_log_status &s = log.body.status;
            std::snprintf(body, sizeof(body),
                          "log status sample_present=%d clock_corrected=%d active_sample=%" PRIu32
                          " transactions=%" PRIu32 " rejected_samples=%" PRIu32
                          " rx_errors=%" PRIu32,
                          (s.flags & PSP_STATUS_FLAG_SAMPLE_PRESENT) ? 1 : 0,
                          (s.flags & PSP_STATUS_FLAG_CLOCK_CORRECTED) ? 1 : 0,
                          s.active_sample_sequence, s.transactions, s.rejected_samples,
                          s.rx_errors);
            break;
        }
        case PSP_LOG_RESULT:
            std::snprintf(body, sizeof(body), "log result request=%" PRIu32 " command=%u status=%u",
                          log.body.result.request_id, log.body.result.command_kind,
                          log.body.result.status);
            break;
        case PSP_LOG_I2C_TRANSACTION:
            std::snprintf(body, sizeof(body),
                          "log i2c_transaction id=%" PRIu32 " read_reg=0x%02x read_len=%u"
                          " served_sample=%" PRIu32 " flags=0x%x",
                          log.body.i2c_transaction.transaction_id,
                          log.body.i2c_transaction.read_register,
                          log.body.i2c_transaction.read_length,
                          log.body.i2c_transaction.sample_sequence,
                          log.body.i2c_transaction.flags);
            break;
        case PSP_LOG_UTC_REPORT:
            std::snprintf(body, sizeof(body), "log utc_report id=%" PRIu32,
                          log.body.utc_report.id);
            break;
        default:
            std::snprintf(body, sizeof(body), "log kind=%d", static_cast<int>(log.kind));
        }
        break;
    }
    default:
        std::snprintf(body, sizeof(body), "frame kind=%d", static_cast<int>(frame.kind));
    }
    return std::string(head) + body;
}
