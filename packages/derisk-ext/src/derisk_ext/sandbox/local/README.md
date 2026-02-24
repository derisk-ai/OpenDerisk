# Improved Local Sandbox Implementation

This directory contains an enhanced local sandbox implementation with proper security isolation, real browser automation, and complete feature support for the DeRisk platform.

## Overview

The improved local sandbox provides:

1. **Security Isolation**
   - macOS: Integration with `sandbox-exec` for process-level isolation
   - Linux: Resource limits via `prlimit` and path restrictions
   - Windows: Basic path isolation (enhanced sandboxing planned)

2. **Real Browser Automation**
   - Playwright integration for actual browser control
   - Support for Chromium, Firefox, and WebKit
   - Headless and headed modes
   - Screenshot, navigation, element interaction

3. **Complete Interface Compliance**
   - Full implementation of `SandboxBase` interface
   - Proper session lifecycle management
   - Resource monitoring and enforcement

4. **Configuration Support**
   - TOML configuration files
   - Programmatic configuration
   - Predefined templates (development, strict, browser)

## Architecture

```
local/
├── README.md                          # This file
├── __init__.py                        # Package exports
├── provider.py                        # Main sandbox provider entry point
├── improved_provider.py               # Improved LocalSandbox implementation
├── improved_runtime.py                # Runtime with isolation and resource limits
├── macos_sandbox.py                   # macOS sandbox-exec integration
├── playwright_browser_client.py       # Playwright browser automation
├── runtime.py                         # Original runtime (deprecated)
├── shell_client.py                    # Shell execution client
├── file_client.py                     # File operations client
└── browser_client.py                  # Original browser stub (deprecated)
```

## Usage

### Basic Usage

```python
from derisk_ext.sandbox.local import LocalSandbox

# Create a sandbox
sandbox = await LocalSandbox.create(
    user_id="test_user",
    agent="test_agent",
)

# Run code
result = await sandbox.run_code("print('Hello, World!')")

# Execute shell commands
shell_result = await sandbox.shell.exec_command(command="ls -la")

# File operations
await sandbox.file.write("test.txt", "Hello, File!")
content = await sandbox.file.read("test.txt")

# Cleanup
await sandbox.kill()
```

### Using Templates

```python
from derisk_ext.sandbox.local import (
    create_development_sandbox,
    create_strict_sandbox,
    create_browser_sandbox,
)

# Development sandbox (more permissive)
dev_sandbox = await create_development_sandbox(
    user_id="dev_user",
    agent="dev_agent",
)

# Strict sandbox (high security)
strict_sandbox = await create_strict_sandbox(
    user_id="user",
    agent="agent",
)

# Browser automation sandbox
browser_sandbox = await create_browser_sandbox(
    user_id="user",
    agent="agent",
)
```

### TOML Configuration

Create a configuration file (e.g., `sandbox.toml`):

```toml
[sandbox.local]
work_dir = "/workspace"
skill_dir = "/path/to/data/skill"  # Default: DATA_DIR/skill for local sandbox for local sandbox
default_timeout = 300
max_memory = 268435456  # 256MB
max_cpus = 1
use_sandbox_exec = true
allow_network = true
browser_type = "chromium"
browser_headless = true
max_sessions = 10
session_idle_timeout = 3600

[sandbox.local.browser_viewport]
width = 1280
height = 720
```

Use the configuration:

```python
from derisk_ext.sandbox.local import create_local_sandbox_from_toml

with open("sandbox.toml") as f:
    toml_content = f.read()

sandbox = await create_local_sandbox_from_toml(
    toml_content,
    user_id="user",
    agent="agent",
)
```

## Platform-Specific Features

### macOS

The macOS implementation uses `sandbox-exec` for process isolation:

- **Profile Generation**: Dynamic SBPL profile based on configuration
- **Path Restrictions**: Read-only and read-write path whitelisting
- **Network Control**: Allow/deny network access
- **Process Limits**: Control process forking and execution

Example profile configuration:

```python
from derisk_ext.sandbox.local import MacOSSandboxProfileConfig

config = MacOSSandboxProfileConfig(
    profile_name="strict",
    read_read_only_paths=["/usr/lib"],
    read_write_paths=["/tmp"],
    allow_network=False,
    max_memory=256 * 1024 * 1024,
)
```

### Windows

Windows support currently provides basic isolation through:
- Path restrictions to workspace directory
- Process cleanup on session termination
- Resource limits (basic)

Full Windows sandboxing using Windows Sandbox API is planned.

## Browser Automation

The Playwright browser client provides full browser control:

```python
# Initialize browser
await sandbox.browser.browser_init()

# Navigate to URL
await sandbox.browser.browser_navigate(
    "https://example.com",
    need_screenshot=True
)

# Get element tree
tree = await sandbox.browser.browser_element_tree()

# Click element
await sandbox.browser.click_element(index=0)

# Input text
await sandbox.builder.input_text(index=1, text="Hello!")

# Take screenshot
screenshot = await sandbox.browser.browser_screenshot(full_page=True)
```

## Resource Limits

### Memory Limits

```python
from derisk_ext.sandbox.local import LocalSandbox

sandbox = await LocalSandbox.create(
    user_id="user",
    agent="agent",
    local_sandbox_config={
        "max_memory": 512 * 1024 * 1024,  # 512MB
    }
)
```

### CPU Limits

```python
sandbox = await LocalSandbox.create(
    user_id="user",
    agent="agent",
    local_sandbox_config={
        "max_cpus": 2,
        "default_timeout": 600,  # 10 minutes
    }
)
```

### Network Control

```python
sandbox = await LocalSandbox.create(
    user_id="user",
    agent="agent",
    allow_internet_access=False,  # Disable network
)
```

## Security Considerations

### macOS Sandbox

The macOS sandbox provides strong but not perfect isolation:

**What's Isolated:**
- File system access (whitelist-based)
- Network access (configurable)
- Process creation (configurable)

**Limitations:**
- CPU and memory limits are advisory
- Some system resources may still be accessible

**Best Practices:**
1. Always enable `sandbox_exec` on macOS (`use_sandbox_exec: true`)
2. Use strict path restrictions
3. Disable network when not needed
4. Set reasonable timeouts

### Linux

On Linux, isolation is provided through:
- `setrlimit` for resource limits
- Path restrictions to session directory
- Process group management

**Best Practices:**
1. Use containerization (Docker/podman) for stronger isolation
2. Run as a non-root user
3. Set ulimit values appropriately

## Troubleshooting

### Playwright Not Installed

```bash
pip install playwright
playwright install
```

### sandbox-exec Not Found (macOS)

`sandbox-exec` is built into macOS. If you get "command not found":
- Verify you're on macOS
- Check system path with `which sandbox-exec`

### Permission Denied Errors

Ensure the working directory is writable by the user running the sandbox.

### Memory Limit Issues

If processes exceed memory limits:
1. Reduce memory limit in config
2. Or disable memory monitoring for debugging

## Configuration Reference

### LocalSandboxConfig

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `work_dir` | str | `/workspace` | Working directory inside sandbox |
| `skill_dir` | str | `DATA_DIR/skill` | Skills directory for local sandbox |
| `runtime_id` | str | `improved_local_runtime` | Runtime identifier |
| `default_timeout` | int | `300` | Default execution timeout (seconds) |
| `max_memory` | int | `268435456` | Memory limit (bytes, 256MB) |
| `max_cpus` | int | `1` | CPU limit |
| `use_sandbox_exec` | bool | `None` | Enable macOS sandbox-exec (None = auto) |
| `allow_network` | bool | `true` | Allow network access |
| `network_disabled` | bool | `false` | Disable network (opposite of allow_network) |
| `browser_type` | str | `chromium` | Browser type (chromium, firefox, webkit) |
| `browser_headless` | bool | `true` | Run browser headless |
| `browser_viewport` | dict | `{"width": 1280, "height": 720}` | Browser viewport size |
| `max_sessions` | int | `10` | Maximum concurrent sessions |
| `session_idle_timeout` | int | `3600` | Session idle timeout (seconds) |

## Development

### Adding New Features

1. Add feature to `ImprovedLocalSandbox` in `improved_provider.py`
2. Implement in the appropriate client (file, shell, browser)
3. Add tests
4. Update documentation

### Platform Support

To add support for a new platform:

1. Add platform detection in `get_platform()`
2. Implement platform-specific sandbox in `improved_runtime.py`
3. Add configuration options
4. Document platform-specific behaviors

## License

This implementation is part of the DeRisk project.

## Contributing

When contributing to this module:

1. Maintain backward compatibility where possible
2. Add proper error handling
3. Include docstrings for all public methods
4. Update documentation for new features
5. Add tests for new functionality