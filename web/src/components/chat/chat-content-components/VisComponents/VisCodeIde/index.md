---
group:
  order: 1
  title: VIS卡片
---

# VisCodeIde

## 基础用法

````jsx
import React from 'react';
import { Space } from 'antd';
import { VisCodeIde } from '@alipay/uni-chat';

export default () => {
  return (
    <div
      style={{
        width: '100%',
        background: '#e7ecf8',
        borderRadius: '16px',
        padding: '16px',
      }}
    >
      <Space direction="vertical" style={{ width: '100%' }}>
        <VisCodeIde
          codeTabs={[
            {
              uid: 'code1',
              type: 'incr',
              exit_success: true,
              name: 'python测试',
              path: 'test_python.py',
              language: 'python',
              markdown: 'def fibonacci(n):\n  print("hello world")',
              console: '```python\nprint("hello world") \n```\n',
              env: 'Python 3.9.7 on Linux',
              cost: 0.58,
            },
            {
              uid: 'code2',
              type: 'incr',
              exit_success: false,
              name: 'web测试',
              path: 'test_html.html',
              language: 'html',
              markdown:
                '<html>\n  <body>\n    <h3 color="color: red">hello world</h3>\n  </body>\n</html>',
              console: '这里1是执行日志和结果',
              env: 'Python 3.1s.7 on Windows',
              cost: 10,
            },
            {
              uid: 'code2',
              type: 'incr',
              exit_success: false,
              name: 'web测试',
              path: '2test_html.html',
              language: 'html',
              markdown:
                '<html>\n  <body>\n    <h3 color="color: red">hello world</h3>\n  </body>\n</html>',
              console: 'hello world1',
              env: 'Python 3.1s.7 on Windows',
              cost: 10,
            },
            {
              uid: 'code2',
              type: 'incr',
              exit_success: false,
              name: 'web测试',
              path: '3test_html.html',
              language: 'html',
              markdown:
                '<html>\n  <body>\n    <h3 color="color: red">hello world</h3>\n  </body>\n</html>',
              console: 'hello world2',
              env: 'Python 3.1s.7 on Windows',
              cost: 10,
            },
            {
              uid: 'code2',
              type: 'incr',
              exit_success: false,
              name: 'web测试',
              path: '4test_html.html',
              language: 'html',
              markdown:
                '<html>\n  <body>\n    <h3 color="color: red">hello world</h3>\n  </body>\n</html>',
              console: '这里是执行日志和结果',
              env: 'Python 3.1s.7 on Windows',
              cost: 10,
            },
          ]}
        />
      </Space>
    </div>
  );
};
````

```ts
// DataIProps
{
  markdown: string;
  [key: string]: any;
}
```

## API

| 字段名称    | 字段类型                  | 字段描述 | 默认值 |
| ----------- | ------------------------- | -------- | ------ |
| data_source | <Badge>DataIProps</Badge> | 数据源   | -      |
