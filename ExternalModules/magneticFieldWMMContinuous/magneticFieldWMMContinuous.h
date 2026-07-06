#ifndef MAGNETIC_FIELD_WMM_CONTINUOUS_H
#define MAGNETIC_FIELD_WMM_CONTINUOUS_H

#include "simulation/environment/_GeneralModuleFiles/magneticFieldBase.h"
#include <string>
#include <Eigen/Dense>

class MagneticFieldWMMContinuous : public MagneticFieldBaseContinuous {
public:
    MagneticFieldWMMContinuous();
    ~MagneticFieldWMMContinuous();

    void appendEpochData(std::string dateString);

protected:
    void customReset(uint64_t CurrentClock);
    void customSetEpochFromVariable();
    void evaluateMagneticFieldModel(MagneticFieldMsgPayload *msg, double currentTime);
    
    // Core WMM continuous evaluation
    void computeWmmFieldAndRate(double decimalYear, double phi, double theta, double r, 
                                Eigen::Vector3d v_BP_P, 
                                Eigen::Vector3d &B_P, Eigen::Vector3d &Bdot_P);

public:
    std::string dataPath;                                  //!< Directory path containing WMM coefficient file
    double decimalYear;                                    //!< Decimal year for secular variation evaluation

private:
    // WMM Gauss Coefficients
    double g[13][13];
    double h[13][13];
    double g_dot[13][13];
    double h_dot[13][13];

    // Legendre Polynomial caching (Value, 1st Deriv, 2nd Deriv)
    double p[13][13];
    double dp[13][13];
    double d2p[13][13]; 

    void loadWMMCoefficients(const std::string& filePath);
    void computeLegendrePolynomials(double theta);
};

#endif