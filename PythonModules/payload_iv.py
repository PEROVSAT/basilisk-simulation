"""
payload_iv.py
PEROVSAT perovskite payload: per-device I-V sweeps measured by the AMUs.

This models the SCIENCE payload, not bus power. Per the PDR circuit design,
each PV device's output is either swept by an AMU (the I-V measurement) or
dumped into a 470 ohm resistor - it never charges the battery. So this module
is independent of the bus solar array in power_system.py; it only reuses the
same orbital irradiance/eclipse geometry (supplied by the caller, e.g.
sims/base.py, which already computes the body-frame Sun direction, the eclipse
shadow factor and the 1/r^2 distance factor each step).

What it does each step:
  * maintains a first-order sun/eclipse thermal model per payload face (the RTD
    temperature that shifts each cell's Voc),
  * accumulates cumulative solar exposure per face (an FSW data product),
  * triggers an AMU I-V sweep on a device when its face sees the Sun above a
    threshold angle and is not eclipsed (FSW: "Sun_angle > thresh -> Sweep AMUs"),
  * generates the full single-diode I-V curve, reduces it to Voc/Isc/Pmax/FF,
    and accounts the stored bytes against the PDR Data Budget.

Physics: single-diode model
    I(V) = Iph - I0[exp((V+I*Rs)/(n*Vt)) - 1] - (V+I*Rs)/Rsh,  Vt = kT/q
with Iph ~ irradiance and temperature, and I0 ~ T^3 exp(-Eg/kT).

Defaults are calibrated to the PDR's measured sweep ("Cell 2 pixel A",
Voc = 1.0594 V) and are PROVISIONAL - the sweep only spans 1.059 -> 0.87 V and
never reaches Isc, so Isc/Jsc is extrapolated. Update jph_ref / n / Rs / Rsh
from a full ground sweep (to 0 V) and the real cell geometry when available.
"""

import numpy as np
import matplotlib.pyplot as plt


# ----------------------------------------------------------------------
# Constants
# ----------------------------------------------------------------------

Q = 1.602176634e-19      # elementary charge [C]
K_B = 1.380649e-23       # Boltzmann constant [J/K]
T_REF_K = 298.15         # reference temperature (25 C) [K]
G_REF = 1361.0           # reference irradiance, 1 sun AM0 [W/m^2]

# PDR measured sweep, "Cell 2 pixel A" (p.312) - for calibration / validation.
PDR_SWEEP_V = np.array([
    1.0594236, 1.0287896, 1.0217844, 1.0152050, 1.0085174, 1.0014459,
    0.9943691, 0.9869357, 0.9793397, 0.9713917, 0.9630628, 0.9545413,
    0.9456745, 0.9362741, 0.9267040, 0.9165850, 0.9059129, 0.8946930,
    0.8829513, 0.8705001])
PDR_SWEEP_I = np.array([
    0.0000031, 0.0005688, 0.0006056, 0.0006756, 0.0007015, 0.0007417,
    0.0007790, 0.0008480, 0.0008559, 0.0009059, 0.0009268, 0.0009733,
    0.0010074, 0.0010470, 0.0010970, 0.0011124, 0.0011298, 0.0011582,
    0.0011931, 0.0012275])
PDR_VOC = 1.0594236

# Data Budget (PDR p.524-557): bytes per stored curve.
BYTES_CURVE_WORST = 27   # 24 B unoptimized fit + 2 B sun sensor + 1 B temp
BYTES_CURVE_BEST = 11    # 8 B minimal points + 2 B sun + 1 B temp


# ----------------------------------------------------------------------
# Single-diode I-V core
# ----------------------------------------------------------------------

def _solve_current(V, iph, i0, n, rs, rsh, Vt):
    """Newton solve of the implicit single-diode equation for I at voltage V."""
    nVt = n * Vt
    I = iph
    for _ in range(60):
        arg = np.clip((V + I * rs) / nVt, -60.0, 60.0)
        e = np.exp(arg)
        f = iph - i0 * (e - 1.0) - (V + I * rs) / rsh - I
        df = -i0 * e * (rs / nVt) - rs / rsh - 1.0
        dI = f / df
        I -= dI
        if abs(dI) < 1e-15:
            break
    return I


def _open_circuit_voltage(iph, i0, n, rs, rsh, Vt):
    """Voltage at which I(V) = 0, by bracketed bisection."""
    nVt = n * Vt
    guess = nVt * np.log(max(iph / i0 + 1.0, 1.0 + 1e-12))
    lo, hi = 0.0, max(guess * 1.5, 1e-3)
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if _solve_current(mid, iph, i0, n, rs, rsh, Vt) > 0.0:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def single_diode_curve(iph, i0, n, rs, rsh, T_k, num=40, v_min=0.0):
    """Return (V, I, Voc) for a sweep from v_min to Voc. v_min > 0 models the
    AMU's real voltage-limited sweep (the PDR sweep stops at ~0.82*Voc and
    never reaches Isc)."""
    Vt = K_B * T_k / Q
    voc = _open_circuit_voltage(iph, i0, n, rs, rsh, Vt)
    V = np.linspace(max(0.0, min(v_min, voc)), voc, num)
    I = np.array([_solve_current(v, iph, i0, n, rs, rsh, Vt) for v in V])
    return V, np.clip(I, 0.0, None), voc


# ----------------------------------------------------------------------
# A single PV device (perovskite cell or non-perovskite reference)
# ----------------------------------------------------------------------

class PVDevice:
    """
    One measured device. Parameters are intensive current densities so that
    Isc scales with area while Voc does not (physically correct).

    jph_ref, n, rs, rsh : single-diode parameters fit to the PDR "pixel A"
              sweep (least-squares over the 20 measured points, RMS 0.037 mA;
              jph_ref = 12 A/m^2 over an assumed 1 cm^2 pixel, n = 2.2). These
              are PROVISIONAL: the sweep only spans 1.059 -> 0.87 V and never
              reaches Isc, and n is high because the measured knee is soft, so
              re-fit from a full ground sweep (to 0 V) and the real cell area.
    """

    def __init__(self, name, face, face_normal, area_m2,
                 jph_ref=12.0, voc_ref=PDR_VOC, n=2.2, rs=0.0, rsh=1.0e6,
                 alpha_isc=5.0e-4, eg_ev=1.6, is_reference=False):
        self.name = name
        self.face = face
        self.normal = np.array(face_normal, dtype=float) / np.linalg.norm(face_normal)
        self.area = area_m2
        self.n = n
        self.rs = rs
        self.rsh = rsh
        self.alpha_isc = alpha_isc            # Isc temperature coefficient [1/K]
        self.eg_ev = eg_ev                    # bandgap [eV]
        self.voc_ref = voc_ref
        self.is_reference = is_reference

        # Extensive reference currents (area-scaled).
        self.iph_ref = jph_ref * area_m2
        Vt_ref = K_B * T_REF_K / Q
        self.i0_ref = self.iph_ref / (np.exp(voc_ref / (n * Vt_ref)) - 1.0)

    def _iph_i0(self, G, T_k):
        """Photocurrent and saturation current at irradiance G and temp T_k."""
        iph = self.iph_ref * (G / G_REF) * (1.0 + self.alpha_isc * (T_k - T_REF_K))
        i0 = (self.i0_ref * (T_k / T_REF_K) ** 3 *
              np.exp((self.eg_ev * Q / K_B) * (1.0 / T_REF_K - 1.0 / T_k)))
        return max(iph, 0.0), i0

    def curve(self, G, T_c, num=40, v_min=0.0):
        """I-V sweep at irradiance G [W/m^2] and device temperature T_c [C],
        from v_min to Voc (v_min=0 -> full curve)."""
        T_k = T_c + 273.15
        iph, i0 = self._iph_i0(G, T_k)
        if iph <= 0.0:                        # dark / eclipsed -> no curve
            return np.array([0.0]), np.array([0.0]), 0.0
        return single_diode_curve(iph, i0, self.n, self.rs, self.rsh, T_k, num, v_min)

    def summary(self, G, T_c, num=60):
        """Reduce a sweep to Voc, Isc, Pmax, Vmp, Imp, fill factor."""
        V, I, voc = self.curve(G, T_c, num)
        if voc <= 0.0:
            return dict(voc=0.0, isc=0.0, pmax=0.0, vmp=0.0, imp=0.0, ff=0.0)
        P = V * I
        k = int(np.argmax(P))
        isc = float(I[0])
        ff = float(P[k] / (voc * isc)) if voc * isc > 0.0 else 0.0
        return dict(voc=float(voc), isc=isc, pmax=float(P[k]),
                    vmp=float(V[k]), imp=float(I[k]), ff=ff)


# ----------------------------------------------------------------------
# The payload: device catalog + thermal model + sweep scheduler + budget
# ----------------------------------------------------------------------

class Payload:
    """
    PEROVSAT AMU payload. Step it once per task tick with the same Sun
    geometry the power system gets.

    payload_faces : {face_label: outward_normal} - which faces carry PV.
                    Default matches the PDR (perovskites on two payload faces);
                    the sun-sensor faces '+Z' and '-X' are used as a stand-in.
    """

    # Device geometry from the PDR (p.96-98): per face, two 1"x1" and two
    # 45x35 mm perovskite devices, plus a non-perovskite reference cell.
    AREA_1IN = 0.0254 * 0.0254        # 1" x 1"  [m^2]
    AREA_45X35 = 0.045 * 0.035        # 45 x 35 mm [m^2]

    def __init__(self, payload_faces=None,
                 sweep_threshold_deg=60.0, sweep_min_interval_s=300.0,
                 bytes_per_curve=BYTES_CURVE_WORST, curve_points=20,
                 sweep_duration_s=0.62, sweep_vmin_frac=0.82, sweep_sample_dt_ms=10.5,
                 T_eq_sun_c=60.0, T_eq_eclipse_c=-20.0, tau_thermal_s=600.0):
        if payload_faces is None:
            payload_faces = {'+Z': (0, 0, 1), '-X': (-1, 0, 0)}
        self.payload_faces = payload_faces
        self.sweep_cos_thresh = np.cos(np.radians(sweep_threshold_deg))
        self.sweep_min_interval_s = sweep_min_interval_s
        self.bytes_per_curve = bytes_per_curve
        self.curve_points = curve_points
        # Sweep timing/range from the PDR "pixel A" table: the AMU is busy
        # ~0.62 s per sweep (92 -> 714 ms) and measures Voc down to only
        # ~0.82*Voc (0.87 V), never reaching Isc -- Isc is fit/extrapolated.
        self.sweep_duration_s = sweep_duration_s
        self.sweep_vmin_frac = sweep_vmin_frac
        self.sweep_sample_dt_ms = sweep_sample_dt_ms

        # Thermal model parameters (first order toward an irradiance-scaled eq.)
        self.T_eq_sun_c = T_eq_sun_c
        self.T_eq_eclipse_c = T_eq_eclipse_c
        self.tau_thermal_s = tau_thermal_s

        # Build the device catalog.
        self.devices = []
        for face, normal in payload_faces.items():
            for k in range(2):
                self.devices.append(PVDevice(
                    f'{face}_perov_1in_{k+1}', face, normal, self.AREA_1IN))
            for k in range(2):
                self.devices.append(PVDevice(
                    f'{face}_perov_45x35_{k+1}', face, normal, self.AREA_45X35))
            # One non-perovskite reference cell per face (silicon-like).
            self.devices.append(PVDevice(
                f'{face}_ref_1', face, normal, self.AREA_1IN,
                jph_ref=250.0, voc_ref=0.60, n=1.2, eg_ev=1.12, is_reference=True))

        # State
        self.time_s = 0.0
        self.face_temp_c = {f: 25.0 for f in payload_faces}
        self.cumulative_exposure_j_m2 = {f: 0.0 for f in payload_faces}
        self.last_sweep_s = {d.name: -1e18 for d in self.devices}
        self.total_curves = 0
        self.total_bytes = 0
        self.total_sweep_time_s = 0.0     # cumulative AMU-active time (all devices)
        self.records = []      # each completed sweep (device, t, T, angle, V, I, summary)
        self.history = []      # per-step telemetry

    # ------------------------------------------------------------------
    def step(self, dt_s, sun_direction_body=(0, 0, 1), shadow_factor=1.0,
             sun_distance_factor=1.0):
        """Advance thermal state, exposure, and trigger due sweeps."""
        sun = np.asarray(sun_direction_body, dtype=float)
        norm = np.linalg.norm(sun)
        if norm > 0:
            sun = sun / norm

        # Per-face thermal + exposure update.
        for face, normal in self.payload_faces.items():
            cos_f = max(0.0, float(np.dot(np.array(normal, float) /
                                          np.linalg.norm(normal), sun)))
            g_face = G_REF * cos_f * shadow_factor * sun_distance_factor
            # First-order temperature toward an irradiance-scaled equilibrium.
            t_eq = self.T_eq_eclipse_c + (self.T_eq_sun_c - self.T_eq_eclipse_c) * (g_face / G_REF)
            T = self.face_temp_c[face]
            self.face_temp_c[face] = T + (t_eq - T) * (dt_s / self.tau_thermal_s)
            self.cumulative_exposure_j_m2[face] += g_face * dt_s

        self.time_s += dt_s

        # Sweep scheduler (FSW: sweep when face sees Sun above threshold).
        n_sweeping = 0
        sunlit = shadow_factor > 0.5
        for dev in self.devices:
            cos_inc = float(np.dot(dev.normal, sun))
            due = (self.time_s - self.last_sweep_s[dev.name]) >= self.sweep_min_interval_s
            if sunlit and cos_inc >= self.sweep_cos_thresh and due:
                self._sweep(dev, cos_inc, shadow_factor, sun_distance_factor)
                self.last_sweep_s[dev.name] = self.time_s
                n_sweeping += 1

        self.history.append({
            'time_s': self.time_s,
            'total_curves': self.total_curves,
            'total_bytes': self.total_bytes,
            'sweeping_now': n_sweeping,
            'temps_c': dict(self.face_temp_c),
        })

    # ------------------------------------------------------------------
    def _sweep(self, dev, cos_inc, shadow_factor, sun_distance_factor):
        """Perform one AMU I-V sweep on a device and store the record + bytes.

        The stored points span the AMU's real measured range (Voc down to
        sweep_vmin_frac*Voc), time-tagged over sweep_duration_s. The summary
        (Voc/Isc/Pmax/FF) comes from the fitted FULL curve -- i.e. what the
        on-board IV-curve fit reports, since Isc is below the measured range.
        """
        G = G_REF * max(0.0, cos_inc) * shadow_factor * sun_distance_factor
        T_c = self.face_temp_c[dev.face]
        summ = dev.summary(G, T_c)                      # fitted full-curve metrics
        vmin = self.sweep_vmin_frac * summ['voc']
        V, I, _ = dev.curve(G, T_c, self.curve_points, v_min=vmin)   # measured range
        V, I = V[::-1], I[::-1]          # order as the AMU sweeps: Voc (t=0) -> vmin
        t_ms = np.arange(len(V)) * self.sweep_sample_dt_ms
        self.total_curves += 1
        self.total_bytes += self.bytes_per_curve
        self.total_sweep_time_s += self.sweep_duration_s
        self.records.append({
            'device': dev.name, 'face': dev.face, 'time_s': self.time_s,
            'temp_c': T_c, 'sun_angle_deg': float(np.degrees(np.arccos(np.clip(cos_inc, -1, 1)))),
            'irradiance_w_m2': G, 'duration_s': self.sweep_duration_s,
            't_ms': t_ms, 'V': V, 'I': I, 'summary': summ,
            'is_reference': dev.is_reference,
        })

    # ------------------------------------------------------------------
    def curves_per_day(self):
        if self.time_s <= 0:
            return 0.0
        return self.total_curves / (self.time_s / 86400.0)

    def print_sample_sweep(self, prefer_perovskite=True):
        """Print one representative sweep as an AMU Time / Voltage / Current
        table -- the same columns as the PDR ground-test data. Picks the
        highest-power sweep recorded (a perovskite device by default)."""
        recs = [r for r in self.records if r['summary']['pmax'] > 0]
        if prefer_perovskite:
            recs = [r for r in recs if not r['is_reference']] or recs
        if not recs:
            print("\n[payload] No I-V sweep recorded "
                  "(no device saw the Sun above threshold while sunlit).\n")
            return
        r = max(recs, key=lambda x: x['summary']['pmax'])
        s = r['summary']
        print("\n" + "=" * 60)
        print("PEROVSAT PAYLOAD - SAMPLE I-V SWEEP DATA")
        print(f"Device: {r['device']}   t={r['time_s']:.1f} s   "
              f"G={r['irradiance_w_m2']:.0f} W/m^2   T={r['temp_c']:+.1f} C")
        print(f"Fit: Voc={s['voc']:.4f} V  Isc={s['isc']*1e3:.4f} mA  "
              f"Pmax={s['pmax']*1e3:.4f} mW  FF={s['ff']:.3f}   "
              f"(measured Voc..{self.sweep_vmin_frac:.2f}*Voc)")
        print("=" * 60)
        print(f"{'AMU Time(ms)':>12} {'Voltage (V)':>13} {'Current (A)':>13}")
        for t, v, i in zip(r['t_ms'], r['V'], r['I']):
            print(f"{t:12.1f} {v:13.7f} {i:13.7f}")
        print("=" * 60)

    def print_summary(self):
        print("\n" + "=" * 60)
        print("PEROVSAT PAYLOAD (I-V SWEEP) SUMMARY")
        print("=" * 60)
        print(f"Sim time: {self.time_s / 3600.0:.2f} h   Devices: {len(self.devices)} "
              f"({sum(not d.is_reference for d in self.devices)} perovskite + "
              f"{sum(d.is_reference for d in self.devices)} reference)")
        print(f"Total sweeps (curves): {self.total_curves}")
        print(f"Rate: {self.curves_per_day():.0f} curves/day, "
              f"{self.total_bytes / max(self.time_s / 86400.0, 1e-9) / 1024:.1f} KB/day "
              f"(@ {self.bytes_per_curve} B/curve)")
        print("  PDR Data Budget: ~87 curves/day (worst) .. ~268/day (best)")
        amu_duty = (self.total_sweep_time_s / (len(self.devices) * self.time_s)
                    if self.time_s > 0 else 0.0)
        print(f"Sweep timing: {self.sweep_duration_s*1e3:.0f} ms/sweep, "
              f"measured range Voc..{self.sweep_vmin_frac:.2f}*Voc (Isc extrapolated)")
        print(f"Effective AMU active duty: {amu_duty*100:.2f}%  (PDR budget assumes <5%)")
        for face in self.payload_faces:
            print(f"  Face {face}: T = {self.face_temp_c[face]:+.1f} C, "
                  f"cumulative exposure = {self.cumulative_exposure_j_m2[face] / 1000.0:.1f} kJ/m^2")
        if self.records:
            r = self.records[-1]
            s = r['summary']
            print(f"\nLast sweep: {r['device']}  (T={r['temp_c']:+.1f} C, "
                  f"sun angle={r['sun_angle_deg']:.0f} deg, G={r['irradiance_w_m2']:.0f} W/m^2)")
            print(f"  Voc={s['voc']:.4f} V  Isc={s['isc']*1e3:.3f} mA  "
                  f"Pmax={s['pmax']*1e3:.3f} mW  FF={s['ff']:.3f}")
        print("=" * 60 + "\n")

    # ------------------------------------------------------------------
    def plot(self, filename='iv_curves.png', show=False):
        """I-V and P-V of a representative sunlit perovskite sweep, with the
        model validated against the PDR measured sweep."""
        fig, axes = plt.subplots(1, 3, figsize=(18, 5))

        # (1) Validation: model at reference condition vs PDR measured points.
        cal = PVDevice('calib_pixel', '+Z', (0, 0, 1), area_m2=1.0e-4)  # ~1 cm^2 pixel
        Vm, Im, vocm = cal.curve(G_REF, 25.0, num=200)
        rms = self._pdr_rms(cal)
        axes[0].plot(Vm, Im * 1e3, '-', color='tab:blue',
                     label=f'Single-diode model\n(RMS {rms*1e3:.3f} mA)')
        axes[0].plot(PDR_SWEEP_V, PDR_SWEEP_I * 1e3, 'o', color='tab:red',
                     ms=4, label='PDR measured (pixel A)')
        axes[0].set_xlabel('Voltage (V)'); axes[0].set_ylabel('Current (mA)')
        axes[0].set_title('Model vs PDR sweep (calibration)')
        axes[0].legend(); axes[0].grid(True, alpha=0.3)

        # Pick a real perovskite sweep from the run (max power) for (2)/(3).
        perov = [r for r in self.records if not r['is_reference'] and r['summary']['pmax'] > 0]
        if perov:
            r = max(perov, key=lambda x: x['summary']['pmax'])
            V, I, s = r['V'], r['I'], r['summary']
            dev = next(d for d in self.devices if d.name == r['device'])
            Vfull, Ifull, _ = dev.curve(r['irradiance_w_m2'], r['temp_c'], num=120)
            title = f"{r['device']}  (G={r['irradiance_w_m2']:.0f} W/m^2, T={r['temp_c']:+.0f} C)"
        else:
            # No sweep occurred - synthesize one at nominal condition.
            dev = self.devices[0]
            V, I, _ = dev.curve(G_REF, 25.0, num=self.curve_points,
                                v_min=self.sweep_vmin_frac * dev.voc_ref)
            Vfull, Ifull, _ = dev.curve(G_REF, 25.0, num=120)
            s = dev.summary(G_REF, 25.0)
            title = f"{dev.name}  (nominal, no in-sim sweep)"

        axes[1].plot(Vfull, Ifull * 1e3, '--', color='gray', alpha=0.7, label='fitted full curve')
        axes[1].plot(V, I * 1e3, '-', color='tab:green', label='AMU measured range')
        axes[1].plot(s['vmp'], s['imp'] * 1e3, 'ko', label='MPP (fit)')
        axes[1].set_xlabel('Voltage (V)'); axes[1].set_ylabel('Current (mA)')
        axes[1].set_title('I-V curve: ' + title, fontsize=9)
        axes[1].legend(fontsize=8); axes[1].grid(True, alpha=0.3)

        axes[2].plot(V, V * I * 1e3, '-', color='tab:purple')
        axes[2].plot(s['vmp'], s['pmax'] * 1e3, 'ko',
                     label=f"Pmax={s['pmax']*1e3:.2f} mW\nFF={s['ff']:.3f}")
        axes[2].set_xlabel('Voltage (V)'); axes[2].set_ylabel('Power (mW)')
        axes[2].set_title('P-V curve', fontsize=9)
        axes[2].legend(); axes[2].grid(True, alpha=0.3)

        plt.tight_layout()
        plt.savefig(filename, dpi=150)
        if show:
            plt.show()
        plt.close()

    @staticmethod
    def _pdr_rms(cal_device):
        """RMS current error of the model vs the PDR measured sweep [A]."""
        Vt = K_B * T_REF_K / Q
        iph, i0 = cal_device._iph_i0(G_REF, T_REF_K)
        model_I = np.array([_solve_current(v, iph, i0, cal_device.n,
                                           cal_device.rs, cal_device.rsh, Vt)
                            for v in PDR_SWEEP_V])
        return float(np.sqrt(np.mean((model_I - PDR_SWEEP_I) ** 2)))


# ----------------------------------------------------------------------
# Standalone check: validate calibration and exercise a synthetic orbit
# ----------------------------------------------------------------------

if __name__ == "__main__":
    import math
    from power_system import eclipse_shadow_factor, sun_distance_factor, R_EARTH_M, AU_M

    cal = PVDevice('calib_pixel', '+Z', (0, 0, 1), area_m2=1.0e-4)
    print(f"Calibration RMS vs PDR sweep: {Payload._pdr_rms(cal)*1e3:.4f} mA")
    print(f"Model Voc at (1 sun, 25 C):   {cal.summary(G_REF, 25.0)['voc']:.4f} V  "
          f"(PDR {PDR_VOC:.4f} V)")

    pl = Payload()
    R = R_EARTH_M + 420e3
    r_sun = np.array([AU_M, 0.0, 0.0])
    period = 2 * math.pi * math.sqrt(R ** 3 / 3.986e14)
    dt = 5.0
    for i in range(int(3 * period / dt)):
        nu = 2 * math.pi * (i * dt) / period
        r_sc = np.array([R * math.cos(nu), R * math.sin(nu), 0.0])
        # tumble the body so payload faces sweep through the Sun line
        spin = 2 * math.pi * (i * dt) / 200.0
        sun_N = (r_sun - r_sc); sun_N /= np.linalg.norm(sun_N)
        c, sN = math.cos(spin), math.sin(spin)
        sun_body = np.array([c * sun_N[0] + sN * sun_N[1],
                             -sN * sun_N[0] + c * sun_N[1], sun_N[2]])
        pl.step(dt, sun_direction_body=sun_body,
                shadow_factor=eclipse_shadow_factor(r_sc, r_sun),
                sun_distance_factor=sun_distance_factor(r_sun - r_sc))
    pl.print_sample_sweep()
    pl.print_summary()
    pl.plot('payload_iv_example.png')
