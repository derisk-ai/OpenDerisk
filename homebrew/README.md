# OpenDerisk Homebrew Tap

Homebrew formula for OpenDeRisk AI-Native Risk Intelligence Systems.

## Installation

### Add the tap

```bash
brew tap derisk-ai/openderisk
```

Or install directly:

```bash
brew install derisk-ai/openderisk/openderisk
```

### Direct install (without tap)

```bash
brew install --cask https://raw.githubusercontent.com/derisk-ai/OpenDerisk/main/homebrew/openderisk.rb
```

## Usage

```bash
# Start CLI
openderisk

# Start server
openderisk-server

# Check version
openderisk --version
```

## Requirements

- macOS 11+ (Big Sur or later)
- Apple Silicon or Intel Mac
- Homebrew 3.0+

## Uninstall

```bash
brew uninstall openderisk
brew untap derisk-ai/openderisk
```

## Formula Details

This formula:
- Installs Python 3.10+ via Homebrew
- Installs uv (Python package manager)
- Sets up all Python dependencies
- Creates `openderisk` and `openderisk-server` commands
- Configures the application in `/opt/homebrew/opt/openderisk`

## Troubleshooting

### Reset installation

```bash
brew reinstall openderisk
```

### Check logs

```bash
brew services logs openderisk
```

## Documentation

- [OpenDerisk GitHub](https://github.com/derisk-ai/OpenDerisk)
- [Homebrew Documentation](https://docs.brew.sh/)
