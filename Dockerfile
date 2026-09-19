# syntax=docker/dockerfile:1.7
#
# Toolchain + Basilisk runtime. Custom C++ plugins are NOT compiled here;
# `make plugins` / `make run` / `make shell` compile them against the mounted
# repo with `pip install --no-build-isolation -e .`.
#
# Rebuild this image only when Basilisk, Python, or system packages change.

FROM ghcr.io/avslab/basilisk:v2.10.2

USER root

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        cmake \
        ninja-build \
    && rm -rf /var/lib/apt/lists/*

# pip is stripped from the upstream image. SWIG comes from PyPI so we get
# >=4.4.1 (Debian's package is too old for Basilisk 2.10). Do not pip-install
# `bsk`: the image already provides Basilisk 2.10.2.
RUN python -m ensurepip --upgrade \
    && python -m pip install --no-cache-dir \
        "bsk-sdk==2.10.2" \
        "swig>=4.4.1,<5" \
        "scikit-build-core>=0.9.3" \
        build \
        pytest

USER basilisk
WORKDIR /workspace/basilisk-simulation
