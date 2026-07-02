#include "permanentMagnet.h"
#include "architecture/utilities/avsEigenSupport.h"
#include "architecture/utilities/rigidBodyKinematics.h"

PermanentMagnet::PermanentMagnet() {
    this->magDipole_B.setZero();
    this->hubSigma = nullptr;

    // Initialize DynamicEffector variables
    this->forceExternal_N.fill(0.0);
    this->forceExternal_B.fill(0.0);
    this->torqueExternalPntB_B.fill(0.0);
}

PermanentMagnet::~PermanentMagnet() {}

void PermanentMagnet::Reset(uint64_t CurrentSimNanos) {
    if (!this->magFieldInMsg.isLinked()) {
        this->bskLogger.bskLog(BSK_ERROR, "PermanentMagnet.magFieldInMsg was not linked.");
    }
}

void PermanentMagnet::UpdateState(uint64_t CurrentSimNanos) {
    // Read the environment magnetic field once per discrete step.
    // Earth's field changes slowly enough that ZOH on the N-frame vector is perfectly valid.
    if (this->magFieldInMsg.isWritten()) {
        this->magFieldMsgBuffer = this->magFieldInMsg();
    }

    // Write out the most recently calculated torque for plotting/logging
    CmdTorqueBodyMsgPayload torqueMsg = {};
    eigenVector3d2CArray(this->torqueExternalPntB_B, torqueMsg.torqueRequestBody);
    this->cmdTorqueOutMsg.write(&torqueMsg, this->moduleID, CurrentSimNanos);
}

void PermanentMagnet::linkInStates(DynParamManager& states) {
    // Grab the pointer to the spacecraft hub's attitude (Modified Rodrigues Parameters)
    this->hubSigma = states.getStateObject("hubSigma");
}

void PermanentMagnet::computeStateContribution(double integTime) {
    // The permanent magnet adds no dynamic mass or inertia to the spacecraft
    return;
}

void PermanentMagnet::computeForceTorque(double integTime, double timeStep) {
    this->torqueExternalPntB_B.fill(0.0); // Zero out previous sub-step torque

    // 1. Get the CONTINUOUS instantaneous attitude state from the ODE solver
    Eigen::Vector3d sigma_BN = this->hubSigma->getState();

    // 2. Convert MRP to Direction Cosine Matrix (DCM)
    double dcm_BN_array[3][3];
    MRP2C(sigma_BN.data(), dcm_BN_array);
    Eigen::Matrix3d dcm_BN;
    for(int i=0; i<3; i++) {
        for(int j=0; j<3; j++) {
            dcm_BN(i,j) = dcm_BN_array[i][j];
        }
    }

    // 3. Load the discrete N-frame magnetic field
    Eigen::Vector3d B_N(this->magFieldMsgBuffer.magField_N);

    // 4. Rotate B_N into the Body frame using the continuous attitude
    Eigen::Vector3d B_B = dcm_BN * B_N;

    // 5. Calculate cross product: tau_B = m_B x B_B
    Eigen::Vector3d tau_B = this->magDipole_B.cross(B_B);

    // 6. Apply to the DynamicEffector base class variable. 
    // The integrator automatically collects this.
    this->torqueExternalPntB_B = tau_B;
}
