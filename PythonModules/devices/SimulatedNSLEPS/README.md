# SimulatedNSLEPS

Pure-Python model of the NSL Electrical Power System (EPS).

**Core measurement:** tracks battery state of charge (SOC), energy, voltage, and operational status (SAFE/LOW/NOMINAL/HIGH) based on net power input.

## Usage

```python
from simulated_nsl_eps import SimulatedNSLEPS

eps = SimulatedNSLEPS(capacity_wh=100.0, initial_soc=0.8)
reading = eps.step(net_power_w=5.0, sim_time_s=60.0)

print(f"SOC: {reading.soc*100:.1f}%")
print(f"Status: {reading.status}")