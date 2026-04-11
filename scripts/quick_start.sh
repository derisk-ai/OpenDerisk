#!/bin/bash
#
# OpenDerisk Quick Start Script
# One command to download, install, and start OpenDerisk
#
# Usage:
#   # Quick experience (download and run)
#   curl -fsSL https://raw.githubusercontent.com/yhjun1026/OpenDerisk/main/scripts/quick_start.sh | bash
#
#   # Development mode (run in existing project)
#   ./scripts/quick_start.sh
#
# Environment Variables:
#   OPENDERISK_REPO    - Repository URL (default: https://github.com/yhjun1026/OpenDerisk.git)
#   OPENDERISK_DIR     - Installation directory (default: ~/.openderisk for download mode)
#   OPENDERISK_PORT    - Server port (default: 7777)
#   OPENDERISK_BRANCH  - Branch to clone (default: main)
#   SKIP_FRONTEND      - Skip frontend build (default: false)
#

set -e

# Configuration
REPO_URL="${OPENDERISK_REPO:-https://github.com/yhjun1026/OpenDerisk.git}"
DEFAULT_PORT="${OPENDERISK_PORT:-7777}"
DEFAULT_BRANCH="${OPENDERISK_BRANCH:-main}"
INSTALL_DIR="${OPENDERISK_DIR:-$HOME/openderisk}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# Logging functions
log() { echo -e "${BLUE}[OpenDerisk]${NC} $1"; }
info() { echo -e "${CYAN}[Info]${NC} $1"; }
warn() { echo -e "${YELLOW}[Warning]${NC} $1"; }
error() { echo -e "${RED}[Error]${NC} $1" >&2; exit 1; }
success() { echo -e "${GREEN}[Success]${NC} $1"; }

# Auto-detect system environment and setup DERISK_HOME
setup_derisk_env() {
    local os_type
    os_type=$(uname -s | tr '[:upper:]' '[:lower:]')

    info "Platform: $os_type ($(uname -m))"

    # If DERISK_HOME already set by user, use it directly
    if [ -n "${DERISK_HOME:-}" ]; then
        mkdir -p "$DERISK_HOME" 2>/dev/null || true
        info "Config directory: $DERISK_HOME (DERISK_HOME)"
        export DERISK_HOME
        return 0
    fi

    # Try default ~/.derisk
    local default_home="${HOME:-}/.derisk"
    if [ -n "${HOME:-}" ] && mkdir -p "$default_home" 2>/dev/null; then
        info "Config directory: $default_home"
        return 0
    fi

    # Fallback for Linux servers without writable HOME
    warn "HOME directory not writable, auto-selecting DERISK_HOME..."
    for candidate in "/opt/derisk" "/var/lib/derisk" "/tmp/derisk"; do
        if mkdir -p "$candidate" 2>/dev/null; then
            export DERISK_HOME="$candidate"
            success "Using DERISK_HOME=$DERISK_HOME (auto-detected)"
            return 0
        fi
    done

    error "Cannot find writable directory for config. Set DERISK_HOME manually."
}

# Detect if running in project directory
is_project_dir() {
    [ -f "pyproject.toml" ] && [ -d "packages" ] && [ -f "install.sh" ]
}

# Check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Install uv package manager
install_uv() {
    if command_exists uv; then
        log "uv already installed: $(uv --version)"
        return 0
    fi

    log "Installing uv (Python package manager)..."
    curl -LsSf https://astral.sh/uv/install.sh | sh

    # Add to PATH
    export PATH="$HOME/.local/bin:$PATH"

    if ! command_exists uv; then
        error "Failed to install uv"
    fi

    success "uv installed: $(uv --version)"
}

# Ensure Python 3.10+
ensure_python() {
    if command_exists python3; then
        version=$(python3 --version 2>&1 | cut -d' ' -f2 | cut -d'.' -f1,2)
        if [ "$version" -ge 10 ] 2>/dev/null || printf '%s\n' "3.10" "$version" | sort -V -C; then
            log "Python $version found (compatible)"
            return 0
        fi
    fi

    log "Installing Python 3.10+ via uv..."
    uv python install 3.10
    success "Python 3.10+ installed"
}

# Clone repository (for download mode)
clone_repo() {
    if [ -d "$INSTALL_DIR/.git" ]; then
        log "Repository exists at $INSTALL_DIR, updating..."
        cd "$INSTALL_DIR"
        git pull origin "$DEFAULT_BRANCH"
    else
        log "Cloning OpenDerisk from $REPO_URL..."
        rm -rf "$INSTALL_DIR"
        git clone --depth 1 --branch "$DEFAULT_BRANCH" "$REPO_URL" "$INSTALL_DIR"
        success "Repository cloned to $INSTALL_DIR"
    fi
    cd "$INSTALL_DIR"
}

# Install dependencies
install_deps() {
    log "Installing dependencies..."

    uv sync --all-packages --frozen \
        --extra "base" \
        --extra "proxy_openai" \
        --extra "rag" \
        --extra "storage_chromadb" \
        --extra "derisks" \
        --extra "client" \
        --extra "ext_base"

    success "Dependencies installed"
}

# Build frontend (optional)
build_frontend() {
    if [ "${SKIP_FRONTEND:-false}" = "true" ]; then
        warn "Skipping frontend build (SKIP_FRONTEND=true)"
        return 0
    fi

    if [ -d "web" ]; then
        log "Building frontend..."
        cd web

        if ! command_exists npm; then
            warn "npm not found, skipping frontend build"
            cd ..
            return 0
        fi

        npm install --legacy-peer-deps 2>/dev/null || npm install
        npm run build 2>/dev/null || warn "Frontend build failed, using dev mode"

        cd ..
        success "Frontend built"
    fi
}

# Start server
start_server() {
    local port="${1:-$DEFAULT_PORT}"

    log "Starting OpenDerisk server on port $port..."
    echo ""
    echo "========================================"
    echo "  OpenDerisk is starting..."
    echo "  Port: $port"
    echo "  URL:  http://localhost:$port"
    echo "========================================"
    echo ""
    echo "Press Ctrl+C to stop the server"
    echo ""

    # Start with quickstart command
    uv run derisk quickstart -p "$port"
}

# Print usage
print_usage() {
    cat << EOF
OpenDerisk Quick Start - One command to download, install, and start

Usage:
  # Quick experience (download, install, start)
  curl -fsSL https://raw.githubusercontent.com/yhjun1026/OpenDerisk/main/scripts/quick_start.sh | bash

  # Run in existing project directory (development mode)
  ./scripts/quick_start.sh

  # Custom port
  OPENDERISK_PORT=8888 ./scripts/quick_start.sh

  # Skip frontend build
  SKIP_FRONTEND=true ./scripts/quick_start.sh

Environment Variables:
  OPENDERISK_REPO    Repository URL (default: https://github.com/yhjun1026/OpenDerisk.git)
  OPENDERISK_DIR     Installation directory (default: ~/openderisk)
  OPENDERISK_PORT    Server port (default: 7777)
  OPENDERISK_BRANCH  Branch to clone (default: main)
  SKIP_FRONTEND      Skip frontend build (default: false)

Options:
  --help, -h     Show this help message
  --port PORT    Specify server port
  --no-frontend  Skip frontend build

Examples:
  # Quick start on port 8888
  curl -fsSL .../quick_start.sh | bash -s -- --port 8888

  # Development mode with custom port
  ./scripts/quick_start.sh --port 8888
EOF
}

# Parse arguments
parse_args() {
    PORT="$DEFAULT_PORT"

    while [ $# -gt 0 ]; do
        case "$1" in
            --help|-h)
                print_usage
                exit 0
                ;;
            --port|-p)
                PORT="$2"
                shift 2
                ;;
            --no-frontend)
                SKIP_FRONTEND="true"
                shift
                ;;
            *)
                warn "Unknown option: $1"
                shift
                ;;
        esac
    done
}

# Main entry point
main() {
    parse_args "$@"

    echo ""
    echo "╔════════════════════════════════════════╗"
    echo "║     OpenDerisk Quick Start Script      ║"
    echo "╚════════════════════════════════════════╝"
    echo ""

    # Check if running in project directory
    if is_project_dir; then
        log "Running in development mode (current directory)"
        info "Project directory: $(pwd)"
    else
        log "Running in download mode"
        info "Will clone to: $INSTALL_DIR"
        clone_repo
    fi

    # Auto-detect system and setup config directory
    setup_derisk_env

    # Ensure dependencies for both modes
    install_uv
    ensure_python

    # Install project dependencies
    install_deps
    build_frontend

    # Start server
    start_server "$PORT"
}

main "$@"