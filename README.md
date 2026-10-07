# basilisk-simulation

The core Basilisk vehicle for PEROVSAT. One simulation; experiments only change run knobs and plot `sim.log`.

Vehicle numbers live in `perovsat/config.py`. Docker must be running. C++ plugins compile inside the container from the mounted repo.

```bash
make shell                              # interactive container (venv + PYTHONPATH)
make run SCRIPT=experiments/detumble/run.py
make run SCRIPT=experiments/power/run.py
```

`make run` / `make shell` compile plugins when C++ sources change. `make image` is only for Basilisk / compiler / Dockerfile changes.

`./setup.sh` still opens a shell (`./setup.sh --rebuild` rebuilds the image first).
