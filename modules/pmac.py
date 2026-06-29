import numpy as np

from Basilisk.architecture import messaging, sysModel
from Basilisk.simulation import extForceTorque, magneticFieldWMM
from Basilisk.utilities import RigidBodyKinematics as rbk
from Basilisk.utilities.supportDataTools.dataFetcher import DataFile, get_path

R_EARTH = 6378137.0  # WGS-84 mean Earth radius [m]


def _ecef_to_geodetic(r_ecef):
    """
    Convert ECEF position [m] to (lat_deg, lon_deg, alt_m).
    Uses iterative Bowring method -- accurate to < 1 mm.
    """
    x, y, z = r_ecef
    lon = np.degrees(np.arctan2(y, x))
    p = np.sqrt(x**2 + y**2)
    lat = np.degrees(np.arctan2(z, p * (1 - 0.00669437999014)))
    for _ in range(5):
        N = R_EARTH / np.sqrt(1 - 0.00669437999014 * np.sin(np.radians(lat))**2)
        lat = np.degrees(np.arctan2(z + 0.00669437999014 * N * np.sin(np.radians(lat)), p))
    N = R_EARTH / np.sqrt(1 - 0.00669437999014 * np.sin(np.radians(lat))**2)
    alt = p / np.cos(np.radians(lat)) - N
    return lat, lon, alt


def _unit(v):
    """Return unit vector, or zero vector if v is near zero."""
    n = np.linalg.norm(v)
    return v / n if n > 1e-30 else v


def compute_hysteresis_damping(volume_m3, remanence_T, coercivity_Am,
                                omega_orbit_rads):
    """
    Compute the hysteresis damping coefficient C_hyst [N*m*s/rad].

    Derived from energy dissipated per B-H cycle:
        E_loss = V * 4 * Br * Hc   (area of rectangular B-H loop approximation)

    Converted to a viscous damping torque by dividing by one orbital cycle
    (2*pi / omega_orbit), giving units of N*m / (rad/s):
        C_hyst = (V * 4 * Br * Hc) / (2*pi / omega_orbit)
               = V * 4 * Br * Hc * omega_orbit / (2*pi)

    The resulting torque applied each step is:
        tau_hyst = -C_hyst * omega_body

    Parameters
    ----------
    volume_m3 : float
        Total hysteresis rod volume [m^3].
    remanence_T : float
        Rod remanence Br [T].
    coercivity_Am : float
        Rod coercivity Hc [A/m].
    omega_orbit_rads : float
        Orbital angular velocity [rad/s], used to normalize energy per cycle.

    Returns
    -------
    C_hyst : float
        Damping coefficient [N*m*s/rad].
    """
    E_loss_per_cycle = volume_m3 * 4.0 * remanence_T * coercivity_Am
    C_hyst = E_loss_per_cycle * omega_orbit_rads / (2.0 * np.pi)
    return C_hyst


class PMACLogger:
    """
    Records per-step PMAC data during simulation for post-run printing.

    Stores:
        times_s       : simulation time [s]
        lat_deg       : geodetic latitude [deg]
        lon_deg       : geodetic longitude [deg]
        alt_km        : altitude [km]
        B_dir_N       : Earth B-field unit vector (inertial frame)
        magnet_dir_N  : satellite magnet axis unit vector (inertial frame)
        torque_B      : total applied torque in body frame [N*m]
        tau_mag_B     : magnet alignment torque component [N*m]
        tau_hyst_B    : hysteresis damping torque component [N*m]
        omega_B       : body angular velocity [rad/s]
        theta_deg     : angle between magnet axis and B-field [deg]
    """

    def __init__(self):
        self.times_s = []
        self.lat_deg = []
        self.lon_deg = []
        self.alt_km = []
        self.B_dir_N = []
        self.magnet_dir_N = []
        self.torque_B = []
        self.tau_mag_B = []
        self.tau_hyst_B = []
        self.omega_B = []
        self.theta_deg = []

    def record(self, t_ns, r_N, B_N, sigma_BN, omega_BN_B,
               magnet_axis_body, tau_mag_B, tau_hyst_B):
        lat, lon, alt = _ecef_to_geodetic(r_N)
        BN = rbk.MRP2C(sigma_BN)
        NB = BN.T
        magnet_dir_N = NB @ magnet_axis_body
        B_dir = _unit(np.array(B_N))
        mag_dir = _unit(magnet_dir_N)
        theta = np.degrees(np.arccos(np.clip(np.dot(B_dir, mag_dir), -1.0, 1.0)))

        self.times_s.append(t_ns * 1e-9)
        self.lat_deg.append(lat)
        self.lon_deg.append(lon)
        self.alt_km.append(alt / 1000.0)
        self.B_dir_N.append(B_dir)
        self.magnet_dir_N.append(mag_dir)
        self.tau_mag_B.append(np.array(tau_mag_B))
        self.tau_hyst_B.append(np.array(tau_hyst_B))
        self.torque_B.append(np.array(tau_mag_B) + np.array(tau_hyst_B))
        self.omega_B.append(np.array(omega_BN_B))
        self.theta_deg.append(theta)

    def print_log(self, every_n=10):
        """
        Print a formatted table of logged values.

        Parameters
        ----------
        every_n : int
            Print every Nth recorded step to keep output readable.
        """
        sep = "=" * 140
        header = (
            "\n{}\n"
            " {:>8}  {:>7}  {:>8}  {:>7}  "
            "{:^28}  {:^28}  {:^28}  {:>10}  {:>12}\n"
            "{}"
        ).format(
            sep,
            "T [s]", "Lat", "Lon", "Alt km",
            "B-field dir (inertial)",
            "Magnet dir (inertial)",
            "Total Torque [N*m]",
            "|omega|",
            "theta [deg]",
            sep,
        )
        print(header)

        indices = range(0, len(self.times_s), every_n)
        for i in indices:
            B = self.B_dir_N[i]
            M = self.magnet_dir_N[i]
            tau = self.torque_B[i]
            omega_mag = np.linalg.norm(self.omega_B[i])
            theta = self.theta_deg[i]
            print(
                " {:>8.1f}  {:>+7.2f}  {:>+8.2f}  {:>7.1f}"
                "  [{:+.3f} {:+.3f} {:+.3f}]"
                "  [{:+.3f} {:+.3f} {:+.3f}]"
                "  [{:+.2e} {:+.2e} {:+.2e}]"
                "  {:>10.4f}"
                "  {:>10.1f}".format(
                    self.times_s[i],
                    self.lat_deg[i],
                    self.lon_deg[i],
                    self.alt_km[i],
                    B[0], B[1], B[2],
                    M[0], M[1], M[2],
                    tau[0], tau[1], tau[2],
                    omega_mag,
                    theta,
                )
            )
        print(sep)
        print("  theta = angle between magnet axis and Earth B-field (goal: 0 deg)")
        print("  |omega| = total body angular velocity magnitude [rad/s] (goal: ~0)\n")

    def print_torque_breakdown(self, every_n=10):
        """Print magnet vs hysteresis torque contributions separately."""
        sep = "=" * 100
        print("\n" + sep)
        print(" {:>8}  {:^35}  {:^35}  {:>10}".format(
            "T [s]", "Tau_magnet [N*m]", "Tau_hyst [N*m]", "|omega|"))
        print(sep)
        for i in range(0, len(self.times_s), every_n):
            tm = self.tau_mag_B[i]
            th = self.tau_hyst_B[i]
            omega_mag = np.linalg.norm(self.omega_B[i])
            print(
                " {:>8.1f}"
                "  [{:+.2e} {:+.2e} {:+.2e}]"
                "  [{:+.2e} {:+.2e} {:+.2e}]"
                "  {:>10.4f}".format(
                    self.times_s[i],
                    tm[0], tm[1], tm[2],
                    th[0], th[1], th[2],
                    omega_mag,
                )
            )
        print(sep + "\n")


class PMAC:
    """
    Passive Magnetic Attitude Control module for PEROVSAT.

    Models both the permanent magnet (alignment torque) and hysteresis rods
    (damping torque). Together they produce passive detumbling and attitude
    stabilization aligned with Earth's magnetic field.

    Torques applied each step:
        tau_magnet = m_B x B_B            (alignment)
        tau_hyst   = -C_hyst * omega_B    (damping)
        tau_total  = tau_magnet + tau_hyst

    Parameters
    ----------
    scSim : SimBaseClass
    simTaskName : str
    scObject : Spacecraft
    dipole_moment_Am2 : float
        Permanent magnet strength [A*m^2]. Default 0.15.
    magnet_axis_body : array-like
        Body-frame unit vector for magnet alignment. Default Z-axis.
    hyst_volume_m3 : float
        Total hysteresis rod volume [m^3]. Default 5e-7.
    hyst_remanence_T : float
        Rod remanence Br [T]. Default 0.25.
    hyst_coercivity_Am : float
        Rod coercivity Hc [A/m]. Default 80.
    use_hysteresis : bool
        Enable hysteresis damping. Default True.
    """

    def __init__(
        self,
        scSim,
        simTaskName,
        scObject,
        dipole_moment_Am2=0.15,
        magnet_axis_body=np.array([0.0, 0.0, 1.0]),
        hyst_volume_m3=5e-7,
        hyst_remanence_T=0.25,
        hyst_coercivity_Am=80.0,
        use_hysteresis=True,
    ):
        self.scSim = scSim
        self.scObject = scObject
        self.dipole_moment = dipole_moment_Am2
        self.axis = magnet_axis_body / np.linalg.norm(magnet_axis_body)
        self.use_hysteresis = use_hysteresis
        self.logger = PMACLogger()

        # Orbital parameters for C_hyst calculation (ISS orbit)
        mu_earth = 3.986004418e14          # [m^3/s^2]
        a_iss = (R_EARTH + 420e3)          # semi-major axis [m]
        omega_orbit = np.sqrt(mu_earth / a_iss**3)   # [rad/s]

        if use_hysteresis:
            C_hyst = compute_hysteresis_damping(
                hyst_volume_m3, hyst_remanence_T, hyst_coercivity_Am, omega_orbit
            )
        else:
            C_hyst = 0.0

        self.controller = PMACController(
            self.dipole_moment, self.axis, C_hyst, self.logger
        )
        scSim.AddModelToTask(simTaskName, self.controller)

        self._setup_wmm(simTaskName)
        self._setup_torque_effector(simTaskName)

        self.controller.scStateInMsg.subscribeTo(self.scObject.scStateOutMsg)

        print("PMAC initialized")
        print("  Dipole:      {} A*m^2  axis: {}".format(dipole_moment_Am2, self.axis))
        if use_hysteresis:
            print("  Hysteresis:  V={:.2e} m^3  Br={} T  Hc={} A/m  C_hyst={:.4e} N*m*s/rad".format(
                hyst_volume_m3, hyst_remanence_T, hyst_coercivity_Am, C_hyst))
        else:
            print("  Hysteresis:  disabled")

    def _setup_wmm(self, simTaskName):
        self.magModule = magneticFieldWMM.MagneticFieldWMM()
        self.magModule.ModelTag = "PMAC_WMM"
        self.magModule.configureWMMFile(str(get_path(DataFile.MagneticFieldData.WMM)))
        self.magModule.addSpacecraftToModel(self.scObject.scStateOutMsg)
        self.scSim.AddModelToTask(simTaskName, self.magModule)

        self.magLog = self.magModule.envOutMsgs[0].recorder()
        self.scSim.AddModelToTask(simTaskName, self.magLog)

        self.controller.magFieldInMsg.subscribeTo(self.magModule.envOutMsgs[0])
        print("WMM initialized")

    def _setup_torque_effector(self, simTaskName):
        self.extFTObject = extForceTorque.ExtForceTorque()
        self.extFTObject.ModelTag = "PMAC_Torque"
        self.scObject.addDynamicEffector(self.extFTObject)
        self.scSim.AddModelToTask(simTaskName, self.extFTObject)
        self.extFTObject.cmdTorqueInMsg.subscribeTo(self.controller.cmdTorqueOutMsg)
        print("ExtForceTorque initialized")

    def print_log(self, every_n=10):
        self.logger.print_log(every_n=every_n)

    def print_torque_breakdown(self, every_n=10):
        self.logger.print_torque_breakdown(every_n=every_n)

    def print_field_sample(self):
        try:
            B_N = np.array(self.magLog.magField_N[-1])
            scLog = self.scObject.scStateOutMsg.read()
            sigma_BN = np.array(scLog.sigma_BN)
            omega_B = np.array(scLog.omega_BN_B)

            BN = rbk.MRP2C(sigma_BN)
            B_B = BN @ B_N
            m_B = self.dipole_moment * self.axis
            tau_mag = np.cross(m_B, B_B)
            tau_hyst = -self.controller.C_hyst * omega_B
            tau_total = tau_mag + tau_hyst

            print("PMAC final state:")
            print("  B-field inertial [T]:", B_N)
            print("  B-field body     [T]:", B_B)
            print("  Tau_magnet [N*m]:    ", tau_mag)
            print("  Tau_hyst   [N*m]:    ", tau_hyst)
            print("  Tau_total  [N*m]:    ", tau_total)
            print("  |Tau_total|:         ", np.linalg.norm(tau_total), "N*m")
        except Exception as e:
            print("PMAC diagnostic error:", e)


class PMACController(sysModel.SysModel):
    """
    Basilisk SysModel computing total PMAC torque each step:
        tau_magnet = m_B x B_B     (permanent magnet alignment)
        tau_hyst   = -C_hyst * w   (hysteresis rod damping)
        tau_total  = tau_magnet + tau_hyst
    """

    def __init__(self, dipole_moment, axis, C_hyst, logger):
        super(PMACController, self).__init__()
        self.dipole_moment = dipole_moment
        self.axis = axis
        self.C_hyst = C_hyst
        self.logger = logger
        self.magFieldInMsg = messaging.MagneticFieldMsgReader()
        self.scStateInMsg = messaging.SCStatesMsgReader()
        self.cmdTorqueOutMsg = messaging.CmdTorqueBodyMsg()

    def Reset(self, CurrentSimNanos):
        pass

    def UpdateState(self, CurrentSimNanos):
        magBuffer = self.magFieldInMsg()
        scBuffer = self.scStateInMsg()

        B_N = np.array(magBuffer.magField_N)
        sigma_BN = np.array(scBuffer.sigma_BN)
        omega_B = np.array(scBuffer.omega_BN_B)
        r_N = np.array(scBuffer.r_BN_N)

        # Rotate B-field into body frame
        BN = rbk.MRP2C(sigma_BN)
        B_B = BN @ B_N

        # Permanent magnet alignment torque: tau_mag = m_B x B_B
        m_B = self.dipole_moment * self.axis
        tau_mag_B = np.cross(m_B, B_B)

        # Hysteresis damping torque: tau_hyst = -C_hyst * omega
        tau_hyst_B = -self.C_hyst * omega_B

        tau_total_B = tau_mag_B + tau_hyst_B

        self.logger.record(
            CurrentSimNanos, r_N, B_N, sigma_BN, omega_B,
            self.axis, tau_mag_B, tau_hyst_B
        )

        payload = messaging.CmdTorqueBodyMsgPayload()
        payload.torqueRequestBody = tau_total_B.tolist()
        self.cmdTorqueOutMsg.write(payload, CurrentSimNanos, self.moduleID)
