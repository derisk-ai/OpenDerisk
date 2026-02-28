# derisk-ext

Extension package for OpenDeRisk with additional tools and integrations.

## Overview

`derisk-ext` provides extended functionality for OpenDeRisk, including:

- **Sandbox**: Secure code execution environment with isolation
- **RAG**: Retrieval-Augmented Generation support
- **MCP Gateway**: Model Context Protocol gateway
- **Data Sources**: Connectors for various databases
- **Storage**: Support for vector stores (ChromaDB, Milvus, etc.)

## Features

### Local Sandbox
- Security isolation using platform-specific mechanisms (sandbox-exec on macOS, prlimit on Linux)
- Real browser automation with Playwright
- Resource limits (memory, CPU, network)

### RAG Pipeline
- Document processing (PDF, Word, Excel, PPT)
- Text chunking and embedding
- Vector storage and retrieval

### MCP Services
- MCP Gateway for managing MCP tools
- Pre-built DevOps domain MCP services
- Custom MCP tool binding

## Installation

```bash
uv sync --all-packages --frozen --extra "ext_base"
```

Additional extras:
- `rag` - RAG functionality
- `storage_chromadb` - ChromaDB storage
- `storage_milvus` - Milvus storage
- `datasource_mysql` - MySQL connector
- `mcp_gateway` - MCP gateway

## Usage

```python
from derisk_ext.sandbox.local import LocalSandbox

# Create a sandbox
sandbox = await LocalSandbox.create(user_id="user", agent="agent")

# Run code
result = await sandbox.run_code("print('Hello, World!')")
```

## Documentation

- [Local Sandbox Documentation](./src/derisk_ext/sandbox/local/README.md)
- [OpenDerisk Main Documentation](../README.md)
- [DeepWiki](https://deepwiki.com/derisk-ai/OpenDerisk)

## License

MIT