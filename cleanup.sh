#!/bin/bash
# cleanup.sh -- PEROVSAT repo reorganization
set -e

cd "$(dirname "$0")"
echo "Cleaning up PEROVSAT repository..."

# ---- New directory structure ----
mkdir -p PythonModules/sim
mkdir -p PythonModules/hardware
mkdir -p experiments/detumble/output
mkdir -p experiments/power_states/output
mkdir -p experiments/device_test/output
mkdir -p experiments/dampening_test/output
mkdir -p configs/hysteresis
mkdir -p docs
mkdir -p tools

# ---- Move existing files ----
[ -f PythonModules/hysteresisFactory.py ] && mv PythonModules/hysteresisFactory.py PythonModules/hardware/
[ -f PythonModules/issOrbit.py ] && mv PythonModules/issOrbit.py PythonModules/sim/
[ -f PythonModules/solarSystemFactory.py ] && mv PythonModules/solarSystemFactory.py PythonModules/sim/

# Merge power files
[ -f PythonModules/power_management.py ] && rm PythonModules/power_management.py
[ -f PythonModules/sim_state.py ] && rm PythonModules/sim_state.py
[ -f PythonModules/power_system.py ] && rm PythonModules/power_system.py

# Move configs
[ -d hysteresis_configs ] && mv hysteresis_configs/* configs/hysteresis/ 2>/dev/null || true
[ -d hysteresis_configs ] && rmdir hysteresis_configs 2>/dev/null || true

# Move experiments
[ -f sims/detumble_experiment.py ] && mv sims/detumble_experiment.py experiments/detumble/run.py
[ -f sims/graph_power_states.py ] && mv sims/graph_power_states.py experiments/power_states/run.py
[ -f sims/device_test_experiment.py ] && mv sims/device_test_experiment.py experiments/device_test/run.py
[ -f sims/dampening_test.py ] && mv sims/dampening_test.py experiments/dampening_test/run.py

# Delete unused
rm -f sims/wmm_pointing.py
rm -f sims/plotting_utils.py
rm -f sims/base.py
rm -f sims/fakeDampening.py

# Delete generated files scattered around
rm -f *.png *.npz *.bin
rm -rf sims/_VizFiles
find . -name "*.png" -not -path "./experiments/*" -not -path "./docs/*" -delete 2>/dev/null || true
find . -name "*.npz" -not -path "./experiments/*" -delete 2>/dev/null || true

# Touch .gitkeep
touch experiments/*/output/.gitkeep

# Remove old sims dir if empty
rmdir sims 2>/dev/null || true

echo "Directory structure reorganized."
echo "Now paste in the new source files."