# derisk-client

Python client library for OpenDeRisk.

## Overview

`derisk-client` provides a Python SDK for interacting with OpenDeRisk services. It allows developers to integrate OpenDeRisk's AI-SRE capabilities into their own applications.

## Features

- **REST API Client**: Easy-to-use Python client for OpenDeRisk services
- **Async Support**: Full async/await support
- **Type Hints**: Comprehensive type annotations for IDE support

## Installation

```bash
pip install derisk-client
```

## Usage

```python
from derisk_client import OpenDeriskClient

# Create a client
client = OpenDeriskClient(base_url="http://localhost:7777")

# Use the client
result = await client.analyze_issue(...)
```

## Documentation

- [OpenDerisk Main Documentation](../README.md)
- [GitHub Repository](https://github.com/derisk-ai/OpenDerisk)

## License

MIT