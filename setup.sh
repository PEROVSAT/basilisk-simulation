#!/usr/bin/env bash
set -euo pipefail

LOCAL_IMAGE="perovsat-bsk"
CONTAINER_WORKSPACE="/workspace/basilisk-simulation"

# Resolve the directory where this script lives (the project root)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
info()    { printf '\033[1;34m[setup]\033[0m %s\n' "$*"; }
success() { printf '\033[1;32m[setup]\033[0m %s\n' "$*"; }
warn()    { printf '\033[1;33m[setup]\033[0m %s\n' "$*"; }
die()     { printf '\033[1;31m[setup]\033[0m %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Detect OS
# ---------------------------------------------------------------------------
detect_os() {
  case "$(uname -s)" in
    Darwin) echo "macos" ;;
    Linux)  echo "linux" ;;
    *)      die "Unsupported operating system: $(uname -s)" ;;
  esac
}

# ---------------------------------------------------------------------------
# Docker installation
# ---------------------------------------------------------------------------
install_docker_macos() {
  if ! command -v brew &>/dev/null; then
    die "Homebrew is not installed. Install it from https://brew.sh and re-run this script."
  fi

  info "Installing Docker via Homebrew..."
  brew install --cask docker

  info "Launching Docker Desktop..."
  open -a Docker

  info "Waiting for Docker daemon to become ready..."
  local attempts=0
  until docker info &>/dev/null 2>&1; do
    attempts=$((attempts + 1))
    if [[ $attempts -ge 30 ]]; then
      die "Docker daemon did not start within 60 seconds. Please start Docker Desktop manually and re-run."
    fi
    sleep 2
  done
  success "Docker is running."
}

install_docker_linux() {
  if ! command -v apt-get &>/dev/null; then
    die "apt-get not found. This script supports Debian/Ubuntu-based Linux only."
  fi

  info "Installing Docker via apt..."
  sudo apt-get update -y
  sudo apt-get install -y ca-certificates curl gnupg lsb-release

  # Add Docker's official GPG key and repository
  sudo install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/$(. /etc/os-release && echo "$ID")/gpg \
    | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  sudo chmod a+r /etc/apt/keyrings/docker.gpg

  echo \
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/$(. /etc/os-release && echo "$ID") \
$(lsb_release -cs) stable" \
    | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null

  sudo apt-get update -y
  sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

  # Allow current user to run Docker without sudo
  if ! groups "$USER" | grep -qw docker; then
    sudo usermod -aG docker "$USER"
    warn "Added $USER to the 'docker' group. You may need to log out and back in for this to take effect."
  fi

  sudo systemctl enable --now docker
  success "Docker installed and started."
}

# ---------------------------------------------------------------------------
# Ensure Docker is installed
# ---------------------------------------------------------------------------
ensure_docker() {
  if command -v docker &>/dev/null && docker info &>/dev/null 2>&1; then
    success "Docker is already installed and running."
    return
  fi

  local os
  os="$(detect_os)"
  info "Docker not found or not running. Installing for platform: $os"

  case "$os" in
    macos) install_docker_macos ;;
    linux) install_docker_linux ;;
  esac
}

# ---------------------------------------------------------------------------
# Build image
# ---------------------------------------------------------------------------
# Builds the custom Docker image (plugin-builder + Basilisk runtime).
# Skips the build if the image already exists; pass --rebuild to force it.
build_image() {
  local force_rebuild="${1:-}"

  if [[ -z "$force_rebuild" ]] && docker image inspect "$LOCAL_IMAGE" &>/dev/null 2>&1; then
    success "Image '$LOCAL_IMAGE' already exists. Skipping build (run with --rebuild to force)."
    return
  fi

  info "Building image '$LOCAL_IMAGE' from Dockerfile..."
  info "  Stage 1 compiles the permanentMagnet plugin (bsk-sdk, first run takes a few minutes)."
  info "  Stage 2 layers the plugin onto the Basilisk runtime image."
  docker build -t "$LOCAL_IMAGE" "$SCRIPT_DIR"
  success "Image built successfully."
}

# ---------------------------------------------------------------------------
# Run container
# ---------------------------------------------------------------------------
run_container() {
  info "Starting Basilisk container..."
  info "  Local project : $SCRIPT_DIR"
  info "  Container path: $CONTAINER_WORKSPACE"

  docker run -it \
    --rm \
    -v "${SCRIPT_DIR}:${CONTAINER_WORKSPACE}" \
    -w "$CONTAINER_WORKSPACE" \
    "$LOCAL_IMAGE" \
    /bin/bash
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
  local rebuild_flag=""
  for arg in "$@"; do
    [[ "$arg" == "--rebuild" ]] && rebuild_flag="yes"
  done

  ensure_docker
  build_image "$rebuild_flag"
  run_container
}

main "$@"
