# basilisk-simulation

The core Basilisk vehicle for PEROVSAT. One simulation; experiments only change run knobs and plot `sim.log`.

Docker must be running. C++ plugins (`permanentMagnet`, `hyteresisRods`) compile inside the container from the mounted repo — you do not rebuild the image to change C++ or Python.

```bash
make shell                              # interactive container (venv already on PATH)
make run SCRIPT=experiments/detumble/run.py
make run SCRIPT=experiments/power/run.py
```

`make run` / `make shell` compile plugins automatically when `ExternalModules/`, `messages/`, or the plugin build files change. `make image` is only for Basilisk / compiler / Dockerfile changes.

`./setup.sh` still opens a shell (`./setup.sh --rebuild` rebuilds the image first).
