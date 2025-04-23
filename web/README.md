## 💪🏻 Getting Started

### Prerequisites

- [Node.js](https://nodejs.org/) >= 16
- [npm](https://npmjs.com/) >= 8
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
edit the `API_BASE_URL` to the real address

```sh
# development model
npm run dev
yarn dev
```

## 🚀 Use In DeRisk

```sh
npm run compile
yarn compile

# copy compile file to DeRisk static file dictory
cp -rf out/* ../packages/derisk-app/src/derisk_app/static/web

```

## Usage
  [gpt-vis](https://github.com/antv/gpt-vis) for markdown support.
  [ant-design](https://github.com/ant-design/ant-design) for ui components.
  [next.js](https://github.com/vercel/next.js) for server side rendering.
  [@antv/g2](https://github.com/antvis/g2#readme) for charts.

