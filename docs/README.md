# OpenDerisk Documentation

Documentation site for OpenDeRisk built with Docusaurus.

## Quick Start

### Prerequisites
- Clone the project first!

### Install Dependencies
```bash
yarn install
```

### Launch Development Server
```bash
yarn start
```

The default service starts on port `3000`. Visit `http://localhost:3000`

## Building for Production

```bash
yarn build
```

The built static files will be in the `build` directory.

## Documentation Structure

```
docs/
├── docs/           # Actual documentation content
│   ├── overview.md
│   ├── getting-started.md
│   └── ...
├── sidebars.js     # Sidebar configuration
├── docusaurus.config.js  # Docusaurus configuration
└── package.json
```

## Contributing

When contributing to the documentation:

1. Follow the existing markdown style
2. Add appropriate sidebar entries
3. Test the changes locally before submitting

## More Information

- [OpenDerisk Main Documentation](../README.md)
- [Docusaurus Documentation](https://docusaurus.io/)
- [DeepWiki](https://deepwiki.com/derisk-ai/OpenDerisk)