#ifndef HYSTERESIS_DEBUG_MSG_H
#define HYSTERESIS_DEBUG_MSG_H

/*! @brief Jiles-Atherton hysteresis internal state for debug logging */
typedef struct {
    double H;          //!< [A/m] Axial field
    double Hdot;       //!< [A/m/s] Axial field rate
    double Man;        //!< [A/m] Anhysteretic magnetization
    double He;         //!< [A/m] Effective field
    double chi_irr;    //!< [-] Irreversible susceptibility
    double dMdH;       //!< [-] Total susceptibility
    double M;          // [A/m] Current Magnetization
} HysteresisDebugMsgPayload;

#endif
