# SimulatedAMU

Pure-Python model of the PEROVSAT Aerospace Measurement Unit (AMU).

**Core measurement:** given the Sun direction and a PV device normal, produces a realistic I-V curve using the single-diode model with temperature correction.

## Usage

```python
from simulated_amu import SimulatedAMU

amu = SimulatedAMU()
reading = amu.sample(sun_dir, device_normal, temp_c=25.0)
print(reading.voc, reading.isc, reading.ff)