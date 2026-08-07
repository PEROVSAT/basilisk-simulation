"""
registers.py
Physical constants and configuration for the NSL EPS model.
"""

# Battery defaults
DEFAULT_CAPACITY_WH = 100.0
DEFAULT_INITIAL_SOC = 0.8
DEFAULT_VOLTAGE_V = 28.0
DEFAULT_MAX_CHARGE_W = 50.0
DEFAULT_MAX_DISCHARGE_W = 50.0

# Operational status thresholds (PDR Page 11)
SOC_SAFE_MAX = 0.20
SOC_LOW_MAX = 0.40
SOC_HIGH_MIN = 0.99

# Status names
STATUS_NAMES = {
    0: "SAFE",
    1: "LOW",
    2: "NOMINAL",
    3: "HIGH",
}