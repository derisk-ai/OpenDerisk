# OpenDerisk Web

Web UI for OpenDeRisk AI-Native Risk Intelligence System.

## Introduction

OpenDerisk Web is an open-source Next.js and Tailwind CSS based chat UI for AI and GPT projects. It provides a beautiful markdown rendering for various elements including tables, code blocks, headers, lists, images, and more. It also includes custom components for AI-specific scenarios such as plugin running, knowledge visualization, and chart views.

## Prerequisites

- [Node.js](https://nodejs.org/) >= 18.18
- [npm](https://npmjs.com/) >= 10
- [yarn](https://yarnpkg.com/) >= 1.22
- Supported OSes: Linux, macOS, and Windows

## Installation

```bash
# Install dependencies
npm install
# or
yarn install
```

## Configuration

```bash
cp .env.template .env
```

Edit the `NEXT_PUBLIC_API_BASE_URL` to point to your OpenDerisk server address.

## Development

```bash
# Start development server
npm run dev
# or
yarn dev
# or
pnpm dev
# or
bun dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser.

## Building for Production

```bash
cd web
yarn build
cp -r out/* ../packages/derisk-app/src/derisk_app/static/web/
```

## Adding New Vis Components

To add a new visual component:

1. Create a new file in `components/chat-content-components/VisComponents`
2. Implement the component using React and necessary libraries
3. Update the `visComponentsRender` object in `config.tsx` to include your new component

## Tech Stack

- Next.js
- Tailwind CSS
- React
- TypeScript

## Documentation

- [OpenDerisk Main Documentation](../README.md)
- [DeepWiki](https://deepwiki.com/derisk-ai/OpenDerisk)

## License

MIT