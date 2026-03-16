#!/bin/bash

# Release Preparation Script for Derisk Project
# This script performs the following tasks:
# 1. Build and update frontend static files
# 2. Generate MySQL DDL files (full and incremental)
# 3. Update uv.lock file

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m'
BOLD='\033[1m'

STAR="✨"
ARROW="➜"
CHECK="✓"
INFO="ℹ"
WARN="⚠"
ERROR="✗"

print_header() {
    printf "\n${BOLD}${BLUE}==================== ${STAR} ${1} ${STAR} ====================${NC}\n"
}

print_step() {
    printf "\n${YELLOW}${ARROW} [$(date +"%H:%M:%S")] ${GREEN}$1${NC}\n"
}

print_info() {
    printf "${CYAN}${INFO} $1${NC}\n"
}

print_warning() {
    printf "${YELLOW}${WARN} $1${NC}\n"
}

print_success() {
    printf "${GREEN}${CHECK} $1${NC}\n"
}

print_error() {
    printf "${RED}${ERROR} $1${NC}\n"
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

START_TIME=$(date +"%Y-%m-%d %H:%M:%S")
print_header "Release Preparation Starting"
print_info "Script started at: $START_TIME"
print_info "Project root: $PROJECT_ROOT"

cd "$PROJECT_ROOT"

print_header "Step 1: Build Frontend Static Files"
print_step "Running build_web_static.sh..."

if [ -f "$SCRIPT_DIR/build_web_static.sh" ]; then
    if bash "$SCRIPT_DIR/build_web_static.sh"; then
        print_success "Frontend static files built successfully"
    else
        print_error "Failed to build frontend static files"
        exit 1
    fi
else
    print_warning "build_web_static.sh not found, skipping frontend build"
fi

print_header "Step 2: Generate MySQL DDL Files"
print_step "Running generate_mysql_ddl.py..."

if [ -f "$SCRIPT_DIR/generate_mysql_ddl.py" ]; then
    PYTHON_CMD=$(command -v python3 2>/dev/null || command -v python 2>/dev/null)
    if [ -z "$PYTHON_CMD" ]; then
        print_error "Python not found. Please install Python 3."
        exit 1
    fi
    if "$PYTHON_CMD" "$SCRIPT_DIR/generate_mysql_ddl.py"; then
        print_success "MySQL DDL files generated successfully"
        print_info "Full DDL: assets/schema/derisk.sql"
        print_info "Incremental DDL: assets/schema/upgrade_*_to_*.sql (if any changes)"
    else
        print_error "Failed to generate MySQL DDL files"
        exit 1
    fi
else
    print_error "generate_mysql_ddl.py not found"
    exit 1
fi

print_header "Step 3: Update Dependencies with uv"
print_step "Running uv sync..."

if command -v uv &> /dev/null; then
    if uv sync --all-packages \
        --extra "base" \
        --extra "proxy_openai" \
        --extra "rag" \
        --extra "storage_chromadb" \
        --extra "derisks" \
        --extra "storage_oss2" \
        --extra "client" \
        --extra "ext_base"; then
        print_success "Dependencies synced and uv.lock updated successfully"
    else
        print_error "Failed to sync dependencies"
        exit 1
    fi
else
    print_warning "uv not found in PATH, skipping dependency update"
    print_info "Install uv: curl -LsSf https://astral.sh/uv/install.sh | sh"
fi

END_TIME=$(date +"%Y-%m-%d %H:%M:%S")
print_header "Release Preparation Complete"
print_success "Script completed at: $END_TIME"

if command -v dateutils.ddiff >/dev/null 2>&1; then
    DURATION=$(dateutils.ddiff -f "%M minutes and %S seconds" "$START_TIME" "$END_TIME")
    print_success "Total execution time: $DURATION"
else
    print_success "Total execution time: Started at $START_TIME, ended at $END_TIME"
fi

print_header "Summary"
print_info "1. Frontend static files: packages/derisk-app/src/derisk_app/static/web/"
print_info "2. Full DDL: assets/schema/derisk.sql"
print_info "3. Incremental DDL (if version changed): assets/schema/upgrade_<old>_to_<new>.sql"
print_info "4. Dependencies: uv.lock updated"

print_header "End of Release Preparation"