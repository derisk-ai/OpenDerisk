# derisk-core

Core package for OpenDeRisk AI-Native Risk Intelligence System.

## Overview

`derisk-core` is the foundational package that contains core modules and utilities used across all OpenDeRisk packages and services. It provides the fundamental infrastructure for building AI-driven SRE (Site Reliability Engineering) applications.

## Features

- **Multi-Agent Architecture**: Framework for building collaborative AI agents (SRE-Agent, Code-Agent, ReportAgent, Vis-Agent, Data-Agent)
- **ReAct Master Agent**: Advanced reasoning agent with doom loop detection, session compaction, and output truncation
- **Model Proxy**: Support for multiple LLM providers (OpenAI, Anthropic, Azure, etc.)
- **AWEL Operators**: Rich set of operators for building AI workflows
- **Data Processing**: Tools for processing logs, traces, and metrics

## Installation

```bash
# From source
uv sync --all-packages --frozen
```

## Dependencies

Key dependencies include:
- `aiohttp` - Async HTTP client
- `pydantic` - Data validation
- `SQLAlchemy` - Database ORM
- `duckdb` - Embedded analytical database
- `uvicorn` - ASGI server

Optional dependencies:
- `agent` - Agent-related functionality
- `framework` - Full framework features
- `hf` - HuggingFace integration
- `code` - Code execution support

## Usage

```python
from derisk import ...

# Build your AI-SRE application
```

## Documentation

- [OpenDerisk Documents](https://deepwiki.com/derisk-ai/OpenDerisk)
- [GitHub Repository](https://github.com/derisk-ai/OpenDerisk)

## License

MIT