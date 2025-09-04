## 👋 Introduction

[DERISK Web] is an Open source Tailwind and Next.js based chat UI for AI and GPT projects. It beautify a lot of markdown labels, such as `table`, `thead`, `th`, `td`, `code`, `h1`, `h2`, `ul`, `li`, `a`, `img`. Also it define some custom labels to adapted to AI-specific scenarios. Such as `plugin running`, `knowledge name`, `Chart view`, and so on.

## 💪🏻 Getting Started

### Prerequisites

- [Node.js](https://nodejs.org/) >= 18.18
- [npm](https://npmjs.com/) >= 10
- [yarn](https://yarnpkg.com/) >= 1.22
- Supported OSes: Linux, macOS and Windows

### Installation

```sh
# Install dependencies
npm install
yarn install
```

### Usage
```sh
cp .env.template .env
```

edit the `NEXT_PUBLIC_API_BASE_URL` to the real address

```sh
# development model
npm run dev
# or
yarn dev
# or
pnpm dev
# or
bun dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

### Add New Vis Components

To add a new visual component, follow these steps:

1. Create a new file for your component in the `components/chat-content-components/VisComponents` directory.
2. Implement the component using React and any necessary libraries.
3. Update the `visComponentsRender` object in `config.tsx` to include your new component.
