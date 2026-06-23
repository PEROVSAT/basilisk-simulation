import numpy as np


class PassiveMagneticAttitudeControl:
    """
    Permanent Magnet Attitude Control (PMAC)

    Models a permanent magnet aligned with the spacecraft +Z axis.

    Magnetic torque:

        tau = m x B

    where:
        m = magnetic dipole moment [A*m^2]
        B = Earth magnetic field [Tesla]
    """

    def __init__(
        self,
        dipole_moment_Am2=0.1,
        magnet_axis_body=np.array([0.0, 0.0, 1.0]),
    ):
        """
        Parameters
        ----------
        dipole_moment_Am2 : float
            Magnet strength [A*m^2]

        magnet_axis_body : ndarray
            Unit vector describing magnet direction
            in spacecraft body frame.
        """

        self.dipole_moment_Am2 = dipole_moment_Am2

        axis = np.array(magnet_axis_body, dtype=float)

        self.magnet_axis_body = (
            axis / np.linalg.norm(axis)
        )

    def magnetic_moment_vector(self):
        """
        Returns magnetic dipole moment vector.

        Returns
        -------
        ndarray
            m vector [A*m^2]
        """

        return (
            self.dipole_moment_Am2
            * self.magnet_axis_body
        )

    def compute_torque(self, B_body):
        """
        Compute magnetic alignment torque.

        Parameters
        ----------
        B_body : ndarray
            Earth magnetic field vector
            in spacecraft body frame [Tesla]

        Returns
        -------
        ndarray
            Torque vector [N*m]
        """

        m = self.magnetic_moment_vector()

        tau = np.cross(
            m,
            B_body
        )

        return tau

    def alignment_angle_deg(self, B_body):
        """
        Angle between magnet axis and magnetic field.

        Useful for plotting alignment performance.
        """

        Bmag = np.linalg.norm(B_body)

        if Bmag < 1e-12:
            return 0.0

        axis = self.magnet_axis_body

        cos_theta = np.dot(
            axis,
            B_body / Bmag
        )

        cos_theta = np.clip(
            cos_theta,
            -1.0,
            1.0
        )

        return np.degrees(
            np.arccos(cos_theta)
        )