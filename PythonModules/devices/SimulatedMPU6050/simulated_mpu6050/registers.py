"""
registers.py
Register map and physical constants for the InvenSense MPU-6050, transcribed
from the datasheet + register map (RM-MPU-6000A). Kept free of any modelling
logic so the numbers can be checked against the datasheet at a glance.

Everything a real driver would care about lives here: the I2C address, the
measurement/config register offsets, the full-scale range tables (LSB
sensitivity per range) and the temperature transfer function.
"""

from enum import IntEnum

# --- I2C identity -----------------------------------------------------------
I2C_ADDRESS = 0x68          # AD0 tied low (0x69 if AD0 high)
WHO_AM_I_VALUE = 0x68       # contents of the WHO_AM_I register on a real part

# --- Register addresses (subset that carries data / configures ranges) ------
REG_SMPLRT_DIV = 0x19
REG_CONFIG = 0x1A
REG_GYRO_CONFIG = 0x1B      # FS_SEL in bits 4:3
REG_ACCEL_CONFIG = 0x1C     # AFS_SEL in bits 4:3
REG_ACCEL_XOUT_H = 0x3B     # accel/temp/gyro are a contiguous 14-byte block:
REG_ACCEL_XOUT_L = 0x3C     #   0x3B..0x40  accel X/Y/Z (big-endian int16)
REG_ACCEL_YOUT_H = 0x3D     #   0x41..0x42  temperature
REG_ACCEL_YOUT_L = 0x3E     #   0x43..0x48  gyro X/Y/Z
REG_ACCEL_ZOUT_H = 0x3F
REG_ACCEL_ZOUT_L = 0x40
REG_TEMP_OUT_H = 0x41
REG_TEMP_OUT_L = 0x42
REG_GYRO_XOUT_H = 0x43
REG_GYRO_XOUT_L = 0x44
REG_GYRO_YOUT_H = 0x45
REG_GYRO_YOUT_L = 0x46
REG_GYRO_ZOUT_H = 0x47
REG_GYRO_ZOUT_L = 0x48
REG_PWR_MGMT_1 = 0x6B
REG_WHO_AM_I = 0x75

MEASUREMENT_BLOCK_START = REG_ACCEL_XOUT_H
MEASUREMENT_BLOCK_LEN = 14   # accel(6) + temp(2) + gyro(6)

REGISTER_BANK_SIZE = 0x76    # covers WHO_AM_I at 0x75

# --- 16-bit signed output range ---------------------------------------------
INT16_MIN = -32768
INT16_MAX = 32767


class GyroRange(IntEnum):
    """FS_SEL values written to GYRO_CONFIG[4:3]."""
    DPS_250 = 0
    DPS_500 = 1
    DPS_1000 = 2
    DPS_2000 = 3


class AccelRange(IntEnum):
    """AFS_SEL values written to ACCEL_CONFIG[4:3]."""
    G_2 = 0
    G_4 = 1
    G_8 = 2
    G_16 = 3


# Datasheet sensitivities. LSB counts per engineering unit; the reciprocal is
# the resolution of one count.
#   gyro : LSB per (deg/s)
#   accel: LSB per g
GYRO_SENSITIVITY_LSB_PER_DPS = {
    GyroRange.DPS_250: 131.0,
    GyroRange.DPS_500: 65.5,
    GyroRange.DPS_1000: 32.8,
    GyroRange.DPS_2000: 16.4,
}
GYRO_FULL_SCALE_DPS = {
    GyroRange.DPS_250: 250.0,
    GyroRange.DPS_500: 500.0,
    GyroRange.DPS_1000: 1000.0,
    GyroRange.DPS_2000: 2000.0,
}
ACCEL_SENSITIVITY_LSB_PER_G = {
    AccelRange.G_2: 16384.0,
    AccelRange.G_4: 8192.0,
    AccelRange.G_8: 4096.0,
    AccelRange.G_16: 2048.0,
}
ACCEL_FULL_SCALE_G = {
    AccelRange.G_2: 2.0,
    AccelRange.G_4: 4.0,
    AccelRange.G_8: 8.0,
    AccelRange.G_16: 16.0,
}

# --- Temperature transfer function (datasheet) ------------------------------
#   T[degC] = TEMP_OUT / 340 + 36.53
TEMP_SENSITIVITY_LSB_PER_DEGC = 340.0
TEMP_OFFSET_DEGC = 36.53

# --- Unit helpers -----------------------------------------------------------
STANDARD_GRAVITY_M_S2 = 9.80665   # 1 g in SI, for accel unit conversions
