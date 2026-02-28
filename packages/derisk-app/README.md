# derisk-app

Main application package for OpenDeRisk.

## Overview

`derisk-app` is the main application package that provides the OpenDeRisk server and web interface. It integrates all the core components and extensions to provide a complete AI-SRE solution.

## Features

- **Web Server**: FastAPI-based REST API server
- **Web UI**: Next.js based chat interface
- **Static Assets**: Pre-built web assets for deployment

## Installation

```bash
uv sync --all-packages --frozen
```

## Quick Start

1. Configure the API_KEY in your config file (e.g., `derisk-proxy-aliyun.toml`)
2. Run the server:
```bash
uv run python packages/derisk-app/src/derisk_app/derisk_server.py --config configs/derisk-proxy-aliyun.toml
```
3. Access the web UI at http://localhost:7777

## Project Structure

```
packages/derisk-app/
├── src/derisk_app/
│   ├── static/web/     # Pre-built web assets
│   ├── derisk_server.py  # Main server entry
│   └── ...
└── pyproject.toml
```

## Documentation

- [OpenDerisk Main Documentation](../README.md)
- [DeepWiki](https://deepwiki.com/derisk-ai/OpenDerisk)

## License

MIT