"""
registers.py
Physical constants for the AMU model.
"""

# Solar constant (W/m²)
SOLAR_CONSTANT = 1361.0

# Default PV device parameters (calibrated to perovskite cell)
VOC_REF = 1.2          # Reference Voc at 25°C, 1 sun [V]
ISC_REF = 0.001        # Reference Isc at 25°C, 1 sun [A]
N_DIODE = 1.5          # Ideality factor
RS = 0.1               # Series resistance [Ω]
RSH = 1000.0           # Shunt resistance [Ω]
TEMP_COEFF_VOC = 0.003 # Voc temperature coefficient [1/K]
TEMP_COEFF_ISC = 0.0005  # Isc temperature coefficient [1/K]
EG_EV = 1.6            # Bandgap energy [eV]

# IV curve points
IV_CURVE_POINTS = 40