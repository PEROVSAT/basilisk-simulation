#ifndef HYSTERESIS_DEBUG_MSG_H
#define HYSTERESIS_DEBUG_MSG_H

/*! @brief Flatley–Henretty hysteresis internal state for debug logging */
typedef struct {
    double H;          //!< [A/m]   Axial applied field
    double Hdot;       //!< [A/m/s] Axial field rate
    double B;          //!< [T]     Induced flux density along rod
    double S;          //!< [-]     Burton substituted state tan(π B / 2 Bs)
    double dBdH;       //!< [T/(A/m)] Local differential permeability
    double M;          //!< [A/m]   Magnetization (B/μ0 − H)
} HysteresisDebugMsgPayload;

#endif
