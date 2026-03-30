#!/bin/bash

# DeRisk Quick Start Script
# This script starts DeRisk server with zero configuration

set -e

echo "🚀 Starting DeRisk Server..."
echo ""

# Check if virtual environment exists
if [ -d ".venv" ]; then
    source .venv/bin/activate
    echo "✓ Activated virtual environment"
fi

# Start the server
echo "✓ Starting with zero configuration"
echo "✓ Service will be available at: http://localhost:7777"
echo ""
echo "After starting, you can:"
echo "  1. Open http://localhost:7777 in your browser"
echo "  2. Configure models through the web UI"
echo "  3. All configurations will be saved automatically"
echo ""
echo "Press Ctrl+C to stop the server"
echo "================================"
echo ""

# Run the server
derisk quickstart "$@"