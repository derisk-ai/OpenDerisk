#!/bin/bash

# DeRisk Quick Start Script
# This script starts DeRisk server with zero configuration
# Automatically detects OS and adapts startup behavior
#
# Usage:
#   ./start.sh              # Start in foreground
#   ./start.sh -d           # Start in daemon mode (background)
#   ./start.sh -p 8888      # Start on port 8888
#   ./start.sh -c config.toml  # Start with config file

set -e

# Parse arguments
DAEMON_MODE=false
EXTRA_ARGS=""

while [[ $# -gt 0 ]]; do
    case $1 in
        -d|--daemon)
            DAEMON_MODE=true
            shift
            ;;
        *)
            EXTRA_ARGS="$EXTRA_ARGS $1"
            shift
            ;;
    esac
done

# Auto-detect system environment and setup DERISK_HOME
setup_derisk_env() {
    local os_type
    os_type=$(uname -s | tr '[:upper:]' '[:lower:]')

    echo "  Platform: $os_type ($(uname -m))"

    # If DERISK_HOME already set by user, use it directly
    if [ -n "${DERISK_HOME:-}" ]; then
        mkdir -p "$DERISK_HOME" 2>/dev/null || true
        echo "  Config:   $DERISK_HOME (DERISK_HOME)"
        export DERISK_HOME
        return 0
    fi

    # Try default ~/.derisk
    local default_home="${HOME:-}/.derisk"
    if [ -n "${HOME:-}" ] && mkdir -p "$default_home" 2>/dev/null; then
        echo "  Config:   $default_home"
        return 0
    fi

    # Fallback for Linux servers without writable HOME
    echo ""
    echo "  WARNING: HOME directory not writable, auto-selecting DERISK_HOME..."
    for candidate in "/opt/derisk" "/var/lib/derisk" "/tmp/derisk"; do
        if mkdir -p "$candidate" 2>/dev/null; then
            export DERISK_HOME="$candidate"
            echo "  Config:   $DERISK_HOME (auto-detected)"
            return 0
        fi
    done

    echo "  ERROR: Cannot find writable directory for config."
    echo "  Please set DERISK_HOME environment variable manually."
    echo "  Example: export DERISK_HOME=/your/path"
    exit 1
}

echo ""
echo "================================"
echo "  DeRisk Server Quick Start"
echo "================================"

# Setup environment
setup_derisk_env

echo ""

# Check if virtual environment exists
if [ -d ".venv" ]; then
    source .venv/bin/activate
    echo "  Activated virtual environment"
fi

echo ""

if [ "$DAEMON_MODE" = true ]; then
    echo "  Mode:     Daemon (background)"
    echo "  Service:  http://localhost:7777"
    echo "  Log:      logs/quickstart.log"
    echo ""
    echo "  To stop the server: derisk stop webserver"
    echo "================================"
    echo ""
    # Run in daemon mode
    derisk quickstart -d $EXTRA_ARGS
else
    echo "  Service: http://localhost:7777"
    echo ""
    echo "  After starting, you can:"
    echo "    1. Open http://localhost:7777 in your browser"
    echo "    2. Configure models through the web UI"
    echo "    3. All configurations will be saved automatically"
    echo ""
    echo "  Press Ctrl+C to stop the server"
    echo "================================"
    echo ""
    # Run the server in foreground
    derisk quickstart $EXTRA_ARGS
fi
