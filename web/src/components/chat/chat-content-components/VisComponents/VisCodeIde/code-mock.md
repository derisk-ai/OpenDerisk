### 新 code 卡片

```d-code
{
    "uid": "a1b2c3d4e5f67891",
    "type": "incr",
    "name": "新code卡片",
    "items": [
      {
        "uid": "code1",
        "type": "incr",
        "exit_success":true,
        "name":"python测试",
        "path": "test_python.py",
        "language": "python",
        "markdown":"def fibonacci(n):\n  print(\"hello world\")",
        "console": "hello world",
        "env": "Python 3.9.7 on Linux",
        "cost": 0.58
      },
      {
        "uid":"code2",
        "type": "incr",
        "exit_success": false,
        "name": "web测试",
        "path": "test_html.html",
        "language": "html",
        "markdown":"<html>\n  <body>\n    <h3 style=\"color: red\">hello world</h3>\n  </body>\n</html>",
        "console": "这里1是执行日志和结果",
        "env": "Python 3.1s.7 on Windows",
        "cost": 10
      },
      {
        "uid":"code2",
        "type": "incr",
        "exit_success": false,
        "name": "web测试",
        "path": "2test_html.html",
        "language": "html",
        "markdown":"<html>\n  <body>\n    <h3 style=\"color: red\">hello world</h3>\n  </body>\n</html>",
        "console": "hello world1",
        "env": "Python 3.1s.7 on Windows",
        "cost": 10
      },
            {
        "uid":"code2",
        "type": "incr",
        "exit_success": false,
        "name": "web测试",
        "path": "3test_html.html",
        "language": "html",
        "markdown":"<html>\n  <body>\n    <h3 style=\"color: red\">hello world</h3>\n  </body>\n</html>",
        "console": "hello world2",
        "env": "Python 3.1s.7 on Windows",
        "cost": 10
      },
      {
        "uid":"code2",
        "type": "incr",
        "exit_success": false,
        "name": "web测试",
        "path": "4test_html.html",
        "language": "html",
        "markdown":"<html>\n  <body>\n    <h3 style=\"color: red\">hello world</h3>\n  </body>\n</html>",
        "console": "这里是执行日志和结果",
        "env": "Python 3.1s.7 on Windows",
        "cost": 10
      }
    ],
    "start_time":  "",
    "cost": 0
}
```

code
```code
code something...
```

js
```js
import React from 'react';
// import { CodePreview } from '@alipay/uni-chat';

// import Title from 'antd/es/skeleton/Title';
import { isEqual } from 'lodash';
import Code from './Code';
import { VisCodeIdeDiv } from './style';

// interface IProps extends TS.CodeIde {}

const VisCodeIde = ({ items, pureCode }: TS.CodeIde) => {
  return (
    <>
      <VisCodeIdeDiv className="vis-code-ide">
        <Code pureCode={pureCode} codeTabs={items} />
      </VisCodeIdeDiv>
    </>
  );
};

export default React.memo(VisCodeIde, isEqual); 
```


json
```json
{
  "name": "@alipay/uni-chat",
  "version": "1.1.92",
  "description": "A library project powered by bigfish-library",
  "repository": {
    "type": "git",
    "url": "https://code.alipay.com/tr-web/UniChat"
  },
  "author": "will.jc",
  "module": "dist/index.js",
  "typings": "dist/index.d.ts",
  "files": [
    "dist",
    "icons",
    "LEGAL.md",
    "assets.json"
  ],
  "scripts": {
    "build": "bigfish-lib build",
    "build:watch": "bigfish-lib build -w",
    "ci": "tnpm run lint && jest --coverage --passWithNoTests tnpm run lint && jest --coverage --passWithNoTests tnpm run lint && jest --coverage --passWithNoTests tnpm run lint && jest --coverage --passWithNoTests tnpm run lint && jest --coverage --passWithNoTests tnpm run lint && jest --coverage --passWithNoTests",
    "cov": "jest --coverage",
    "create": "bigfish-lib create",
    "deploy": "bigfish-lib deploy",
    "dev": "bigfish-lib doc dev",
    "doctor": "bigfish-lib doctor",
    "lint": "bigfish-lib lint",
    "prepare": "bigfish-lib setup && husky install",
    "prepublishOnly": "bigfish-lib prepublish",
    "pull": "bigfish-lib pull",
    "start": "sudo PORT=443 HTTPS=true tnpm run dev",
    "test": "jest"
  },
  "commitlint": {
    "extends": [
      "@commitlint/config-conventional"
    ]
  },
  "lint-staged": {
    "*.{md,json}": [
      "prettier --cache --write --no-error-on-unmatched-pattern"
    ],
    "*.{js,jsx}": [
      "bigfish-lib lint --fix --eslint-only",
      "prettier --cache --write"
    ],
    "*.{css,less}": [
      "bigfish-lib lint --fix --stylelint-only",
      "prettier --cache --write"
    ],
    "*.{ts,tsx}": [
      "bigfish-lib lint --fix --eslint-only",
      "prettier --cache --parser=typescript --write"
    ]
  },
  "dependencies": {
    "@alipay/sregpt-ui": "^1.0.16",
    "@alipay/tech-ui": "^3.14.5",
    "@alipay/vis-datafun": "^1.0.0",
    "@ant-design/cssinjs": "^1.24.0",
    "@ant-design/icons": "^5.5.1",
    "@ant-design/x": "^1.0.0-alpha.5",
    "@antv/gpt-vis": "^0.5.0",
    "@babel/runtime": "^7.18.0",
    "@fast-csv/parse": "^5.0.5",
    "@microsoft/fetch-event-source": "^2.0.1",
    "axios": "^1.7.7",
    "d3": "^7.9.0",
    "dagre": "^0.8.5",
    "dayjs": "^1.11.13",
    "eventemitter3": "^5.0.1",
    "highlight.js": "^11.11.1",
    "html2canvas": "^1.4.1",
    "html2pdf.js": "^0.10.3",
    "js-pinyin": "^0.2.7",
    "jspdf": "^3.0.1",
    "katex": "^0.16.21",
    "lodash": "^4.17.21",
    "mermaid": "^11.12.1",
    "react-error-boundary": "^6.0.0",
    "react-json-view": "^1.21.3",
    "react-markdown": "^10.1.0",
    "react-syntax-highlighter": "^15.6.1",
    "react-use": "^17.6.0",
    "reactflow": "^11.11.4",
    "rehype-highlight": "^7.0.2",
    "rehype-katex": "^7.0.1",
    "rehype-raw": "^7.0.0",
    "remark-breaks": "^4.0.0",
    "remark-gfm": "^4.0.1",
    "remark-math": "^6.0.0",
    "remark-parse": "^10.0.0",
    "remark-stringify": "^10.0.0",
    "slate": "^0.103.0",
    "slate-history": "^0.110.3",
    "slate-react": "^0.110.0",
    "styled-components": "^6.0.7",
    "unified": "^10.1.2",
    "unist-util-visit": "^5.0.0",
    "vfile": "^5.3.7"
  },
  "devDependencies": {
    "@ali/ci": "^4.26.0",
    "@alipay/bigfish-library": "^4.0.0",
    "@commitlint/cli": "^17.3.0",
    "@commitlint/config-conventional": "^17.3.0",
    "@testing-library/jest-dom": "^5.1.1",
    "@testing-library/react": "^13.0.0",
    "@types/jest": "^29.4.0",
    "@types/react": "^18.0.0",
    "@types/react-syntax-highlighter": "^15.5.7",
    "antd": "^5.0.0",
    "husky": "^8.0.0",
    "jest": "^29.4.3",
    "jest-environment-jsdom": "^29.4.3",
    "lint-staged": "^13.0.0",
    "prettier": "^2.0.0",
    "react": "^18.0.0",
    "react-dom": "^18.0.0"
  },
  "peerDependencies": {
    "antd": "^5.0.0",
    "react": ">=16.9.0",
    "react-dom": ">=16.9.0"
  },
  "optionalDependencies": {
    "node-bin-darwin-arm64": "16",
    "node-darwin-x64": "16",
    "node-linux-arm64": "16",
    "node-linux-x64": "16",
    "node-win-x64": "16",
    "node-win-x86": "16"
  },
  "engines": {
    "install-node": "16"
  },
  "publishConfig": {
    "registry": "https://registry.antgroup-inc.cn"
  },
  "ci": {
    "type": "aci"
  },
  "dumiAssets": "assets.json",
  "tnpm": {
    "mode": "npm"
  },
  "yuyanId": "180020010101325639"
}

```


css
```css
.div{
    width: 100%;
    height: 100%;
    .titleActionWrap {
        width: 100%;
        height: auto;
        display: flex;
        justify-content: space-between;
        align-items: center;
        font-size: 15px;
        font-weight: 666;
    }
}
```

html
```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <title>Flex 布局演示</title>
  <style>
    body {
      font-family: Arial, sans-serif;
      margin: 20px;
    }

    h2 {
      margin-top: 40px;
      font-size: 20px;
    }

    .box {
      border: 1px solid #ccc;
      padding: 10px;
      margin-bottom: 20px;
      background: #fafafa;
    }

    .flex-container {
      display: flex;
      border: 1px dashed #999;
      padding: 10px;
      margin-top: 10px;
      background: #fff;
    }

    .item {
      background: #4caf50;
      color: #fff;
      padding: 10px;
      margin: 5px;
      text-align: center;
      border-radius: 4px;
    }

    .item:nth-child(2) {
      background: #2196f3;
    }

    .item:nth-child(3) {
      background: #ff9800;
    }

    /* 1. 主轴方向 */
    .row         { flex-direction: row; }
    .row-reverse { flex-direction: row-reverse; }
    .column      { flex-direction: column; }
    .column-rev  { flex-direction: column-reverse; }

    /* 2. 主轴对齐方式 */
    .justify-start    { justify-content: flex-start; }
    .justify-center   { justify-content: center; }
    .justify-end      { justify-content: flex-end; }
    .justify-between  { justify-content: space-between; }
    .justify-around   { justify-content: space-around; }

    /* 3. 交叉轴对齐方式 */
    .align-start   { align-items: flex-start; }
    .align-center  { align-items: center; }
    .align-end     { align-items: flex-end; }
    .align-stretch { align-items: stretch; }

    /* 让容器有高度方便观察 align-items */
    .fixed-height {
      height: 120px;
    }

    /* 4. 子项伸缩 */
    .grow-demo .item {
      flex: 1; /* 每个子项等比例撑满 */
    }

    .grow-demo .item:nth-child(2) {
      flex: 2; /* 第二项两倍宽度 */
    }

    /* 5. 换行 */
    .wrap        { flex-wrap: wrap; }
    .nowrap      { flex-wrap: nowrap; }
    .item-wide {
      width: 120px;
    }

  </style>
</head>
<body>

  <h1>Flex 布局演示</h1>

  <!-- 1. 主轴方向 -->
  <div class="box">
    <h2>1. 主轴方向 (flex-direction)</h2>
    <p>row（默认，水平方向，从左到右）</p>
    <div class="flex-container row">
      <div class="item">1</div>
      <div class="item">2</div>
      <div class="item">3</div>
    </div>

    <p>row-reverse（从右到左）</p>
    <div class="flex-container row-reverse">
      <div class="item">1</div>
      <div class="item">2</div>
      <div class="item">3</div>
    </div>

    <p>column（垂直方向，从上到下）</p>
    <div class="flex-container column">
      <div class="item">1</div>
      <div class="item">2</div>
      <div class="item">3</div>
    </div>
  </div>

  <!-- 2. 主轴对齐 -->
  <div class="box">
    <h2>2. 主轴对齐 (justify-content)</h2>

    <p>flex-start</p>
    <div class="flex-container row justify-start">
      <div class="item">A</div>
      <div class="item">B</div>
      <div class="item">C</div>
    </div>

    <p>center</p>
    <div class="flex-container row justify-center">
      <div class="item">A</div>
      <div class="item">B</div>
      <div class="item">C</div>
    </div>

    <p>space-between</p>
    <div class="flex-container row justify-between">
      <div class="item">A</div>
      <div class="item">B</div>
      <div class="item">C</div>
    </div>

    <p>space-around</p>
    <div class="flex-container row justify-around">
      <div class="item">A</div>
      <div class="item">B</div>
      <div class="item">C</div>
    </div>
  </div>

  <!-- 3. 交叉轴对齐 -->
  <div class="box">
    <h2>3. 交叉轴对齐 (align-items)</h2>
    <p>容器固定高度，子项高度不同，观察在纵向上的对齐。</p>

    <p>flex-start</p>
    <div class="flex-container row fixed-height align-start">
      <div class="item" style="height:30px;">1</div>
      <div class="item" style="height:60px;">2</div>
      <div class="item" style="height:90px;">3</div>
    </div>

    <p>center</p>
    <div class="flex-container row fixed-height align-center">
      <div class="item" style="height:30px;">1</div>
      <div class="item" style="height:60px;">2</div>
      <div class="item" style="height:90px;">3</div>
    </div>

    <p>flex-end</p>
    <div class="flex-container row fixed-height align-end">
      <div class="item" style="height:30px;">1</div>
      <div class="item" style="height:60px;">2</div>
      <div class="item" style="height:90px;">3</div>
    </div>
  </div>

  <!-- 4. 子项伸缩 (flex) -->
  <div class="box">
    <h2>4. 子项伸缩 (flex-grow / flex)</h2>
    <p>所有子项都能伸缩填满容器，其中第二项占两份宽度。</p>
    <div class="flex-container grow-demo">
      <div class="item">1 (flex:1)</div>
      <div class="item">2 (flex:2)</div>
      <div class="item">3 (flex:1)</div>
    </div>
  </div>

  <!-- 5. 换行 (flex-wrap) -->
  <div class="box">
    <h2>5. 换行 (flex-wrap)</h2>

    <p>nowrap（不换行）</p>
    <div class="flex-container nowrap">
      <div class="item item-wide">1</div>
      <div class="item item-wide">2</div>
      <div class="item item-wide">3</div>
      <div class="item item-wide">4</div>
      <div class="item item-wide">5</div>
    </div>

    <p>wrap（自动换行）</p>
    <div class="flex-container wrap">
      <div class="item item-wide">1</div>
      <div class="item item-wide">2</div>
      <div class="item item-wide">3</div>
      <div class="item item-wide">4</div>
      <div class="item item-wide">5</div>
    </div>
  </div>
</body>
</html>
```
