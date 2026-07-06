# syntax=docker/dockerfile:1.7
#
# Multi-stage build for PEROVSAT Basilisk simulation.
#
# Stage 1 (plugin-builder): compiles the perovsat_plugins wheel using bsk-sdk.
#   Uses a standard Python slim image so we have access to apt build tools.
#   bsk-sdk vendors the Basilisk headers, so no BSK source checkout is needed.
#
# Stage 2 (runtime): takes the pre-built Basilisk runtime image and layers the
#   compiled plugin wheel on top.  The final image is what setup.sh runs.

# ── Stage 1: compile perovsat_plugins ────────────────────────────────────────
FROM python:3.13-slim AS plugin-builder

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        cmake \
        ninja-build \
    && rm -rf /var/lib/apt/lists/*

# Install build tooling.  swig is fetched from PyPI to guarantee >=4.4.1
# (the Debian bookworm package ships 4.1.x which is too old for BSK 2.10).
RUN pip install --no-cache-dir \
        "bsk==2.10.2" \
        "bsk-sdk==2.10.2" \
        "swig>=4.4.1,<5" \
        "scikit-build-core>=0.9.3" \
        build \
        "numpy>=1.24"

WORKDIR /src
COPY pyproject.toml CMakeLists.txt ./
COPY python/ python/
COPY ExternalModules/ ExternalModules/
COPY messages/ messages/

RUN python -m build --wheel --no-isolation --outdir /wheels

# ── Stage 2: Basilisk runtime + perovsat plugin ───────────────────────────────
FROM ghcr.io/avslab/basilisk:latest

# Restore pip (removed upstream as a size optimisation), install the plugin
# wheel and any runtime Python dependencies.  pip is kept so new packages
# can be added here and rebuilt with ./setup.sh --rebuild.
USER root
COPY --from=plugin-builder /wheels/*.whl /tmp/
RUN python -m ensurepip --upgrade \
    && python -m pip install --no-cache-dir \
        /tmp/*.whl \
        pytest \
    && rm /tmp/*.whl

USER basilisk
WORKDIR /workspace/basilisk-simulation
