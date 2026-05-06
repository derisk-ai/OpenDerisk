#!/bin/bash

# DeRisk Stop Script
# This script stops all DeRisk server processes

set -e

# Auto-detect DERISK_HOME
detect_derisk_home() {
    if [ -n "${DERISK_HOME:-}" ]; then
        export DERISK_HOME
        return 0
    fi
    
    local default_home="${HOME:-}/.derisk"
    if [ -d "$default_home" ]; then
        export DERISK_HOME="$default_home"
        return 0
    fi
    
    for candidate in "/opt/derisk" "/var/lib/derisk" "/tmp/derisk"; do
        if [ -d "$candidate" ]; then
            export DERISK_HOME="$candidate"
            return 0
        fi
    done
    
    return 1
}

echo ""
echo "================================"
echo "  DeRisk Server Stop"
echo "================================"
echo ""

# Try to stop using PID file first
PID_FILE=""
if detect_derisk_home; then
    PID_FILE="${DERISK_HOME}/logs/derisk.pid"
    
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE" 2>/dev/null || true)
        if [ -n "$PID" ] && ps -p "$PID" > /dev/null 2>&1; then
            echo "  Found PID file: $PID_FILE"
            echo "  Server PID: $PID"
            echo ""
            
            # Stop by PID
            echo "  Stopping server (PID: $PID)..."
            kill -TERM "$PID" 2>/dev/null || true
            
            # Wait for graceful shutdown
            wait_count=0
            max_wait=10
            
            while [ $wait_count -lt $max_wait ]; do
                if ! ps -p "$PID" > /dev/null 2>&1; then
                    echo "  ✓ Server stopped gracefully"
                    rm -f "$PID_FILE"
                    echo ""
                    echo "================================"
                    echo "  DeRisk server stopped"
                    echo "================================"
                    echo ""
                    exit 0
                fi
                
                sleep 1
                wait_count=$((wait_count + 1))
                echo "    Waiting... ($wait_count/$max_wait seconds)"
            done
            
            # Force kill if still running
            if ps -p "$PID" > /dev/null 2>&1; then
                echo ""
                echo "  Forcing shutdown (SIGKILL)..."
                kill -KILL "$PID" 2>/dev/null || true
                sleep 2
                rm -f "$PID_FILE"
            fi
            
            echo "  ✓ Server stopped"
            echo ""
            echo "================================"
            echo "  DeRisk server stopped"
            echo "================================"
            echo ""
            exit 0
        else
            echo "  PID file exists but process not found"
            echo "  Cleaning up stale PID file..."
            rm -f "$PID_FILE"
            echo ""
        fi
    fi
fi

# Fallback: find and stop all derisk processes manually
echo "  PID file not found, searching for processes..."
echo ""

processes_found=0

# Find all derisk_server.py processes
derisk_pids=$(pgrep -f "derisk_server.py" 2>/dev/null || true)

if [ -n "$derisk_pids" ]; then
    processes_found=1
    echo "  Found derisk_server.py processes:"
    
    for pid in $derisk_pids; do
        cmd=$(ps -p $pid -o command= 2>/dev/null || echo "Unknown")
        echo "    PID: $pid"
        echo "    Command: $cmd"
        echo ""
    done
    
    # Try graceful shutdown first (SIGTERM)
    echo "  Attempting graceful shutdown (SIGTERM)..."
    for pid in $derisk_pids; do
        if kill -TERM $pid 2>/dev/null; then
            echo "    Sent SIGTERM to PID $pid"
        fi
    done
    
    # Wait for processes to stop (up to 10 seconds)
    echo ""
    echo "  Waiting for processes to stop..."
    wait_count=0
    max_wait=10
    
    while [ $wait_count -lt $max_wait ]; do
        still_running=0
        for pid in $derisk_pids; do
            if ps -p $pid > /dev/null 2>&1; then
                still_running=1
                break
            fi
        done
        
        if [ $still_running -eq 0 ]; then
            echo "    All processes stopped gracefully"
            break
        fi
        
        sleep 1
        wait_count=$((wait_count + 1))
        echo "    Waiting... ($wait_count/$max_wait seconds)"
    done
    
    # Force kill if still running
    if [ $wait_count -ge $max_wait ]; then
        echo ""
        echo "  Processes still running, forcing shutdown (SIGKILL)..."
        for pid in $derisk_pids; do
            if ps -p $pid > /dev/null 2>&1; then
                kill -KILL $pid 2>/dev/null || true
                echo "    Sent SIGKILL to PID $pid"
            fi
        done
        sleep 2
    fi
fi

# Find related processes (uv run, multiprocessing, etc.)
echo ""
echo "  Checking for related processes..."

# Find uv run processes related to derisk
uv_pids=$(pgrep -f "uv run.*derisk" 2>/dev/null || true)
if [ -n "$uv_pids" ]; then
    echo "    Found uv run processes:"
    for pid in $uv_pids; do
        cmd=$(ps -p $pid -o command= 2>/dev/null || echo "Unknown")
        echo "      PID: $pid - $cmd"
        kill -TERM $pid 2>/dev/null || true
    done
fi

# Find multiprocessing resource_tracker
mp_pids=$(pgrep -f "multiprocessing.resource_tracker" 2>/dev/null || true)
if [ -n "$mp_pids" ]; then
    echo "    Found multiprocessing resource_tracker:"
    for pid in $mp_pids; do
        cmd=$(ps -p $pid -o command= 2>/dev/null || echo "Unknown")
        echo "      PID: $pid - $cmd"
        kill -TERM $pid 2>/dev/null || true
    done
fi

# Check for port 7777 usage
echo ""
echo "  Checking port 7777..."
port_pid=$(lsof -ti:7777 2>/dev/null || true)
if [ -n "$port_pid" ]; then
    echo "    Found process using port 7777:"
    for pid in $port_pid; do
        cmd=$(ps -p $pid -o command= 2>/dev/null || echo "Unknown")
        echo "      PID: $pid - $cmd"
        kill -TERM $pid 2>/dev/null || true
    done
fi

sleep 2

# Verify processes are stopped
echo ""
echo "  Verifying processes..."
remaining=$(pgrep -f "derisk_server.py" 2>/dev/null || true)

if [ -z "$remaining" ]; then
    echo "    ✓ All DeRisk processes stopped successfully"
else
    echo "    ⚠ Some processes still running:"
    for pid in $remaining; do
        cmd=$(ps -p $pid -o command= 2>/dev/null || echo "Unknown")
        echo "      PID: $pid - $cmd"
    done
fi

echo ""
echo "================================"

if [ $processes_found -eq 0 ]; then
    echo "  No DeRisk processes found"
    echo "  Server may not be running"
else
    echo "  DeRisk server stopped"
fi

echo "================================"
echo ""