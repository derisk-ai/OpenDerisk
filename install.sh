#!/bin/bash
set -e

# OpenDerisk Installer Script
# Supports: Linux (x64, arm64), macOS (x64, arm64)
# Usage: curl -fsSL https://raw.githubusercontent.com/derisk-ai/OpenDerisk/main/install.sh | bash

set -u

BIN_DIR="${BIN_DIR:-$HOME/.local/bin}"
CONFIG_DIR="${CONFIG_DIR:-$HOME/.openderisk/configs}"
REPO_URL="https://github.com/derisk-ai/OpenDerisk.git"
VERSION="${VERSION:-latest}"
DEFAULT_CONFIG="derisk-proxy-aliyun.toml"

# Colors - define first to avoid macOS system 'log' command conflict
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions - must be defined before any usage
log() {
    echo -e "${BLUE}[OpenDerisk]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[Warning]${NC} $1"
}

error() {
    echo -e "${RED}[Error]${NC} $1" >&2
    exit 1
}

success() {
    echo -e "${GREEN}[Success]${NC} $1"
}

# Detect local mode: if running from within the project directory, skip clone
LOCAL_MODE=false
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -f "$SCRIPT_DIR/pyproject.toml" ] && grep -q "OpenDerisk\|openderisk\|derisk" "$SCRIPT_DIR/pyproject.toml" 2>/dev/null; then
    LOCAL_MODE=true
    INSTALL_DIR="${INSTALL_DIR:-$SCRIPT_DIR}"
    log "Detected local source at $INSTALL_DIR, skipping git clone."
else
    INSTALL_DIR="${INSTALL_DIR:-$(pwd)/OpenDerisk}"
fi

# Detect OS and architecture
detect_platform() {
    local os
    local arch
    
    os=$(uname -s | tr '[:upper:]' '[:lower:]')
    arch=$(uname -m)
    
    case "$os" in
        linux)
            os="linux"
            ;;
        darwin)
            os="macos"
            ;;
        *)
            error "Unsupported operating system: $os"
            ;;
    esac
    
    case "$arch" in
        x86_64|amd64)
            arch="x64"
            ;;
        aarch64|arm64)
            arch="arm64"
            ;;
        *)
            error "Unsupported architecture: $arch"
            ;;
    esac
    
    echo "${os}-${arch}"
}

# Check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Auto-detect system environment and setup DERISK_HOME
setup_derisk_env() {
    local os_type
    os_type=$(uname -s | tr '[:upper:]' '[:lower:]')

    log "Platform: $os_type ($(uname -m))"

    # If DERISK_HOME already set by user, use it directly
    if [ -n "${DERISK_HOME:-}" ]; then
        mkdir -p "$DERISK_HOME" 2>/dev/null || true
        log "Config directory: $DERISK_HOME (DERISK_HOME)"
        export DERISK_HOME
        return 0
    fi

    # Try default ~/.derisk
    local default_home="${HOME:-}/.derisk"
    if [ -n "${HOME:-}" ] && mkdir -p "$default_home" 2>/dev/null; then
        log "Config directory: $default_home"
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

# Install uv if not present
install_uv() {
    if command_exists uv; then
        log "uv is already installed: $(uv --version)"
        return 0
    fi
    
    log "Installing uv (Python package manager)..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    
    # Add to PATH for current session
    export PATH="$HOME/.local/bin:$PATH"
    
    if ! command_exists uv; then
        error "Failed to install uv. Please install manually: https://github.com/astral-sh/uv"
    fi
    
    success "uv installed successfully: $(uv --version)"
}

# Install Python 3.10+ if needed
ensure_python() {
    local python_version
    
    if command_exists python3; then
        python_version=$(python3 --version 2>&1 | cut -d' ' -f2 | cut -d'.' -f1,2)
        log "Found Python $python_version"
        
        # Check if version is >= 3.10
        if printf '%s\n' "3.10" "$python_version" | sort -V -C; then
            success "Python version is compatible (>= 3.10)"
            return 0
        fi
    fi
    
    log "Installing Python 3.10+ via uv..."
    uv python install 3.10
    success "Python 3.10 installed"
}

# Clone or update repository (skipped in local mode)
clone_repo() {
    if [ "$LOCAL_MODE" = true ]; then
        log "Local mode: using source at $INSTALL_DIR (skipping git clone)"
        return 0
    fi

    if [ -d "$INSTALL_DIR/.git" ]; then
        log "OpenDerisk already exists at $INSTALL_DIR"
        log "Updating to latest version..."
        cd "$INSTALL_DIR"
        git pull origin main
    else
        log "Cloning OpenDerisk repository..."
        mkdir -p "$(dirname "$INSTALL_DIR")"
        git clone --depth 1 "$REPO_URL" "$INSTALL_DIR"
        success "Repository cloned to $INSTALL_DIR"
    fi
}

# Install OpenDerisk dependencies
install_dependencies() {
    log "Installing OpenDerisk dependencies..."
    cd "$INSTALL_DIR"
    
    uv sync --all-packages --frozen \
        --extra "base" \
        --extra "proxy_openai" \
        --extra "rag" \
        --extra "storage_chromadb" \
        --extra "derisks" \
        --extra "storage_oss2" \
        --extra "client" \
        --extra "ext_base"
    
    success "Dependencies installed successfully"
}

# Initialize default configuration
init_config() {
    local src_config="$INSTALL_DIR/configs/$DEFAULT_CONFIG"
    local dest_config="$CONFIG_DIR/$DEFAULT_CONFIG"

    mkdir -p "$CONFIG_DIR"

    if [ -f "$dest_config" ]; then
        log "Configuration file already exists: $dest_config (skipping)"
        return 0
    fi

    if [ -f "$src_config" ]; then
        cp "$src_config" "$dest_config"
        success "Default configuration initialized: $dest_config"
        warn "Please edit $dest_config and set your API keys before starting the server."
    else
        warn "Template config not found at $src_config, skipping config initialization."
    fi
}

# Create wrapper scripts
create_wrappers() {
    log "Creating wrapper scripts..."
    
    mkdir -p "$BIN_DIR"
    
    # Create main openderisk command
    local derisk_home_line=""
    if [ -n "${DERISK_HOME:-}" ]; then
        derisk_home_line="export DERISK_HOME=\"$DERISK_HOME\""
    fi

    cat > "$BIN_DIR/openderisk" << EOF
#!/bin/bash
# OpenDerisk Launcher
$derisk_home_line
cd "$INSTALL_DIR" || exit 1
exec uv run derisk "\$@"
EOF
    
    chmod +x "$BIN_DIR/openderisk"
    
    # Create openderisk-server command
    cat > "$BIN_DIR/openderisk-server" << EOF
#!/bin/bash
# OpenDerisk Server Launcher
$derisk_home_line
DEFAULT_CONFIG="$CONFIG_DIR/$DEFAULT_CONFIG"

cd "$INSTALL_DIR" || exit 1

# If no arguments provided and default config exists, use it
if [ \$# -eq 0 ] && [ -f "\$DEFAULT_CONFIG" ]; then
    exec uv run derisk start webserver -c "\$DEFAULT_CONFIG"
else
    exec uv run derisk start webserver "\$@"
fi
EOF
    
    chmod +x "$BIN_DIR/openderisk-server"
    
    success "Wrapper scripts created in $BIN_DIR"
}

# Add to shell config
add_to_path() {
    local shell_config=""
    
    case "$SHELL" in
        */bash)
            shell_config="$HOME/.bashrc"
            [ -f "$HOME/.bash_profile" ] && shell_config="$HOME/.bash_profile"
            ;;
        */zsh)
            shell_config="$HOME/.zshrc"
            ;;
        */fish)
            shell_config="$HOME/.config/fish/config.fish"
            ;;
    esac
    
    if [ -n "$shell_config" ] && [ -f "$shell_config" ]; then
        if ! grep -q "$BIN_DIR" "$shell_config" 2>/dev/null; then
            log "Adding $BIN_DIR to PATH in $shell_config"
            echo "export PATH=\"$BIN_DIR:\$PATH\"" >> "$shell_config"
        fi
        # Persist DERISK_HOME if it was auto-detected
        if [ -n "${DERISK_HOME:-}" ] && ! grep -q "DERISK_HOME" "$shell_config" 2>/dev/null; then
            log "Adding DERISK_HOME=$DERISK_HOME to $shell_config"
            echo "export DERISK_HOME=\"$DERISK_HOME\"" >> "$shell_config"
        fi
        warn "Please restart your shell or run: source $shell_config"
    fi
}

# Print usage
print_usage() {
    cat << EOF
OpenDerisk Installer

Usage:
  Remote mode (clone from GitHub):
    curl -fsSL https://raw.githubusercontent.com/derisk-ai/OpenDerisk/main/install.sh | bash

  Local mode (run from project directory, skips git clone):
    cd /path/to/OpenDerisk && bash install.sh

Environment Variables:
  INSTALL_DIR    Installation directory (default: \$(pwd)/OpenDerisk)
  BIN_DIR        Binary directory (default: $HOME/.local/bin)
  CONFIG_DIR     Configuration directory (default: $HOME/.openderisk/configs)
  VERSION        Version to install (default: latest)

Options:
  --help         Show this help message
  --version      Show version information

After Installation:
  1. Edit config and set your API keys
  2. openderisk-server    Start OpenDerisk Server (uses default config)
  3. openderisk           Start OpenDerisk CLI

For more information, visit: https://github.com/derisk-ai/OpenDerisk
EOF
}

# Print version
print_version() {
    echo "OpenDerisk Installer v0.1.0"
}

# Main installation
main() {
    # Parse arguments
    for arg in "$@"; do
        case "$arg" in
            --help|-h)
                print_usage
                exit 0
                ;;
            --version|-v)
                print_version
                exit 0
                ;;
        esac
    done
    
    log "Starting OpenDerisk installation..."
    log "Platform: $(detect_platform)"
    if [ "$LOCAL_MODE" = true ]; then
        log "Mode: local (using existing source)"
    else
        log "Mode: remote (cloning from GitHub)"
    fi
    log "Install directory: $INSTALL_DIR"
    log "Config directory: $CONFIG_DIR"
    log "Binary directory: $BIN_DIR"
    
    # Auto-detect system and setup config directory
    setup_derisk_env

    # Installation steps
    install_uv
    ensure_python
    clone_repo
    install_dependencies
    init_config
    create_wrappers
    add_to_path
    
    success "OpenDerisk installed successfully!"
    echo ""
    echo "=========================================="
    echo "  Quick Start (zero configuration):"
    echo "=========================================="
    echo "  openderisk quickstart"
    echo "  # Then open http://localhost:7777 to configure models and settings in the web UI."
    echo ""
    echo "  Options:"
    echo "    openderisk quickstart -p 8888        # Use custom port"
    echo "    openderisk quickstart -h 127.0.0.1   # Use custom host"
    echo ""
    echo "=========================================="
    echo "  Config-based Start:"
    echo "=========================================="
    echo "  1. Edit config: $CONFIG_DIR/$DEFAULT_CONFIG"
    echo "     Set your API keys (e.g., DASHSCOPE_API_KEY)"
    echo "  2. Start server:"
    echo "     openderisk-server                              # Use default config"
    echo "     openderisk-server -c /path/to/config.toml      # Use custom config"
    echo "  3. Open browser: http://localhost:7777"
    echo ""
    echo "Available config templates in: $INSTALL_DIR/configs/"
    echo "  - derisk-proxy-aliyun.toml    (Aliyun/DashScope)"
    echo "  - derisk-proxy-openai.toml    (OpenAI compatible)"
    echo ""
    echo "Documentation: https://github.com/derisk-ai/OpenDerisk"
}

main "$@"
