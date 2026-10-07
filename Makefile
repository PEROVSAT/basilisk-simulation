# PEROVSAT Basilisk workflow
#
#   make shell                              # interactive container
#   make run SCRIPT=experiments/foo/run.py  # run any experiment
#   make plugins                            # recompile C++ if sources changed
#   make image                              # rebuild the Docker toolchain image
#
# Adding an experiment does not require Makefile changes.

IMAGE               ?= perovsat-bsk
CONTAINER_WORKSPACE ?= /workspace/basilisk-simulation
ROOT                := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
VENV                := .venv
PLUGINS_STAMP       := $(VENV)/.plugins-stamp
IMAGE_STAMP         := .build/image.id

# -it only when stdin is a TTY so `make run` works from scripts/CI.
TTY_FLAGS := $(shell [ -t 0 ] && echo -it)

# Repo root covers both experiments.* and perovsat.* — no sys.path hacks in Python.
PYTHONPATH_VAL := $(CONTAINER_WORKSPACE)

DOCKER_RUN = docker run --rm $(TTY_FLAGS) \
	-v "$(ROOT):$(CONTAINER_WORKSPACE)" \
	-w "$(CONTAINER_WORKSPACE)" \
	-e "PATH=$(CONTAINER_WORKSPACE)/$(VENV)/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" \
	-e "PYTHONPATH=$(PYTHONPATH_VAL)" \
	-e PYTHONUNBUFFERED=1 \
	$(IMAGE)

PLUGIN_SRCS := pyproject.toml CMakeLists.txt
PLUGIN_SRCS += $(shell find ExternalModules messages python -type f 2>/dev/null)

.DEFAULT_GOAL := help

.PHONY: help docker-check require-image image plugins plugins-force run shell smoke clean image-clean

help:
	@echo "PEROVSAT Basilisk"
	@echo
	@echo "  make shell                              Drop into a container shell (venv on PATH)"
	@echo "  make run SCRIPT=experiments/foo/run.py  Run a Python script in the container"
	@echo "  make plugins                            Compile C++ plugins if sources changed"
	@echo "  make smoke                              Import compiled plugins"
	@echo "  make image                              Rebuild the Docker toolchain image"
	@echo "  make clean                              Remove local plugin/venv build artifacts"
	@echo "  make image-clean                        Remove the local Docker image"
	@echo
	@echo "Optional: ARGS='--flag' is appended to the Python command for 'run'."

docker-check:
	@command -v docker >/dev/null 2>&1 || { \
		echo "Docker is not installed. Install Docker Desktop and retry."; exit 1; }
	@docker info >/dev/null 2>&1 || { \
		echo "Docker is installed but not running. Start Docker Desktop and retry."; exit 1; }

require-image: docker-check $(IMAGE_STAMP)
	@docker image inspect $(IMAGE) >/dev/null 2>&1 || $(MAKE) image

$(IMAGE_STAMP): Dockerfile | docker-check
	@mkdir -p .build
	docker build -t $(IMAGE) "$(ROOT)"
	@docker image inspect --format '{{.Id}}' $(IMAGE) > $@

image: docker-check
	@mkdir -p .build
	docker build -t $(IMAGE) "$(ROOT)"
	@docker image inspect --format '{{.Id}}' $(IMAGE) > $(IMAGE_STAMP)

$(VENV)/bin/python: $(IMAGE_STAMP)
	$(DOCKER_RUN) /usr/local/bin/python -m venv --system-site-packages --copies $(VENV)
	@rm -f $(PLUGINS_STAMP)

$(PLUGINS_STAMP): $(PLUGIN_SRCS) $(IMAGE_STAMP) $(VENV)/bin/python
	$(DOCKER_RUN) pip install --no-build-isolation -e .
	@touch $@

plugins: require-image $(PLUGINS_STAMP)

plugins-force: require-image | $(VENV)/bin/python
	$(DOCKER_RUN) pip install --no-build-isolation -e .
	@touch $(PLUGINS_STAMP)

run: plugins
ifndef SCRIPT
	$(error SCRIPT= is required, e.g. make run SCRIPT=experiments/detumble/run.py)
endif
	$(DOCKER_RUN) python $(SCRIPT) $(ARGS)

shell: plugins
	docker run --rm -it \
		-v "$(ROOT):$(CONTAINER_WORKSPACE)" \
		-w "$(CONTAINER_WORKSPACE)" \
		-e "PATH=$(CONTAINER_WORKSPACE)/$(VENV)/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" \
		-e "PYTHONPATH=$(PYTHONPATH_VAL)" \
		-e PYTHONUNBUFFERED=1 \
		$(IMAGE) \
		/bin/bash

smoke: plugins
	$(DOCKER_RUN) python -c "from perovsat_plugins.permanentMagnet import PermanentMagnet; from perovsat_plugins.hyteresisRods import HysteresisRods; print('plugins ok')"

clean:
	rm -rf $(VENV) build dist _skbuild .pytest_cache src/*.egg-info perovsat_plugins.egg-info

image-clean: clean
	-docker image rm $(IMAGE)
	rm -f $(IMAGE_STAMP)
