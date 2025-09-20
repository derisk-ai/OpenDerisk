#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

# 定义颜色代码
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color
BOLD='\033[1m'

# 定义符号
STAR="✨"
ARROW="➜"
CHECK="✓"
INFO="ℹ"
WARN="⚠"

# 定义输出函数
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

# 记录脚本开始时间
START_TIME=$(date +"%Y-%m-%d %H:%M:%S")
print_header "Build Process Starting"
print_info "Script started at: $START_TIME"

SCRIPT_LOCATION=$0
cd "$(dirname "$SCRIPT_LOCATION")"
WORK_DIR=$(pwd)
WORK_DIR="$WORK_DIR/.."
TARGET_DIR="$WORK_DIR/packages/derisk-app/src/derisk_app/static/web"

print_header "Configuration"
print_info "Target directory: $TARGET_DIR"

cd $WORK_DIR/web

source_env=".env"
tmp_env=".env.copy"

print_header "Environment Setup"
print_step "Checking environment files..."
if [ -e "$source_env" ]; then
    print_info "Found .env file, creating backup..."
    cp "$source_env" "$tmp_env"
    rm -rf "$source_env"
else
    print_warning ".env file not found"
fi

print_header "Build Process"
print_step "Installing dependencies..."
yarn install

print_step "Cleaning previous build..."
rm -rf ../web/out/

print_step "Building project..."
yarn build

print_header "Static Files Processing"
print_step "Setting up temporary storage..."
temp_dir=$(mktemp -d)
if [ -f "$TARGET_DIR/swagger-ui-bundle.js" ]; then
    print_info "Backing up swagger-ui-bundle.js..."
    cp "$TARGET_DIR/swagger-ui-bundle.js" "$temp_dir/"
fi
if [ -f "$TARGET_DIR/swagger-ui.css" ]; then
    print_info "Backing up swagger-ui.css..."
    cp "$TARGET_DIR/swagger-ui.css" "$temp_dir/"
fi

print_step "Preparing target directory..."
rm -rf $TARGET_DIR
mkdir -p $TARGET_DIR

print_step "Restoring preserved files..."
if [ -f "$temp_dir/swagger-ui-bundle.js" ]; then
    print_info "Restoring swagger-ui-bundle.js..."
    cp "$temp_dir/swagger-ui-bundle.js" "$TARGET_DIR/"
fi
if [ -f "$temp_dir/swagger-ui.css" ]; then
    print_info "Restoring swagger-ui.css..."
    cp "$temp_dir/swagger-ui.css" "$TARGET_DIR/"
fi

print_step "Cleaning up..."
rm -rf "$temp_dir"

print_step "Deploying new files..."
cp -R ../web/out/* $TARGET_DIR

print_step "Finalizing environment..."
if [ -e "$tmp_env" ]; then
    cp "$tmp_env" "$source_env"
    rm -rf "$tmp_env"
fi

# 记录脚本结束时间
END_TIME=$(date +"%Y-%m-%d %H:%M:%S")
print_header "Build Complete"
print_success "Script completed at: $END_TIME"

# 计算执行时间
if command -v dateutils.ddiff >/dev/null 2>&1; then
    DURATION=$(dateutils.ddiff -f "%M minutes and %S seconds" "$START_TIME" "$END_TIME")
    print_success "Total execution time: $DURATION"
else
    print_success "Total execution time: Started at $START_TIME, ended at $END_TIME"
fi

print_header "End of Build Process"
