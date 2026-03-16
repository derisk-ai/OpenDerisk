# OAuth2 登录配置说明

本文档说明如何在 OpenDerisk 中配置 OAuth2 登录。

## 配置入口

进入 **设置 → 系统配置**，点击 **「OAuth2 登录」** 标签页。

## 基本流程

1. 打开「启用 OAuth2 登录」开关
2. 添加至少一个 OAuth2 提供商（GitHub 或自定义）
3. 填写 Client ID、Client Secret 等必填项
4. 点击「保存 OAuth2 配置」

关闭 OAuth2 时，系统使用原有逻辑，无需登录即可访问。

---

## GitHub 配置

### 1. 创建 GitHub OAuth App

1. 打开 [GitHub OAuth Apps 页面](https://github.com/settings/developers) → 点击 **OAuth Apps** → **New OAuth App**
   - 或直接访问：<https://github.com/settings/applications/new>
2. 填写：
   - **Application name**：任意名称（如 OpenDerisk）
   - **Homepage URL**：应用访问地址，如 `http://localhost:3000`
   - **Authorization callback URL**：`{应用地址}/api/v1/auth/oauth/callback`
     - 示例：`http://localhost:3000/api/v1/auth/oauth/callback`（本地开发）
     - 示例：`https://your-domain.com/api/v1/auth/oauth/callback`（生产环境）

### 2. 在 OpenDerisk 中填写

选择 **提供商类型** 为「GitHub」后，表单**仅显示** Client ID、Client Secret，无需填写任何 URL：

| 字段 | 说明 |
|------|------|
| 提供商类型 | 选择 `GitHub（仅需 Client ID / Secret）` |
| Client ID | GitHub OAuth App 的 Client ID |
| Client Secret | GitHub OAuth App 的 Client Secret |

### GitHub 完整示例（本地开发）

假设 OpenDerisk 运行在 `http://localhost:3000`，按以下步骤操作：

**步骤 1：在 GitHub 创建 OAuth App**

1. 打开 [GitHub Developer Settings](https://github.com/settings/developers) 或直接访问 [New OAuth App](https://github.com/settings/applications/new)
2. 若从 Developer Settings 进入，点击 **OAuth Apps** → **New OAuth App**
3. 填写表单：

   | 字段 | 填写值 |
   |------|--------|
   | Application name | `OpenDerisk Local` |
   | Homepage URL | `http://localhost:3000` |
   | Authorization callback URL | `http://localhost:3000/api/v1/auth/oauth/callback` |

4. 点击 **Register application**
5. 在应用详情页复制 **Client ID**，点击 **Generate a new client secret** 生成并复制 **Client secret**

**步骤 2：在 OpenDerisk 中配置**

1. 进入 **设置 → 系统配置 → OAuth2 登录**
2. 打开「启用 OAuth2 登录」
3. 填写提供商信息：

   | 字段 | 填写值 |
   |------|--------|
   | 提供商类型 | `GitHub（仅需 Client ID / Secret）` |
   | Client ID | 粘贴 GitHub 的 Client ID（如 `Ov23liAbCdEf123456`） |
   | Client Secret | 粘贴 GitHub 的 Client secret |

4. 点击 **保存 OAuth2 配置**

**步骤 3：验证**

1. 退出或刷新页面，应跳转到登录页
2. 点击「使用 GitHub 登录」，完成授权后跳回应用

---

## 自定义 OAuth2 配置

选择 **提供商类型** 为「自定义 OAuth2」时，表单会**额外显示**以下 URL 字段，需全部填写：

| 字段 | 说明 | 示例 |
|------|------|------|
| Authorization URL | 授权端点 | `https://example.com/oauth/authorize` |
| Token URL | 令牌端点 | `https://example.com/oauth/token` |
| Userinfo URL | 用户信息端点 | `https://example.com/oauth/userinfo` |
| Scope | 请求的权限范围 | `openid profile email` |

自定义 OAuth2 需符合标准 OAuth 2.0 流程，且 Userinfo 端点应返回包含 `id` 或 `sub` 的 JSON。

---

## 多提供商

可添加多个提供商（如 GitHub + 企业自建 OAuth2），用户登录时可选择任一提供商。点击「添加提供商」即可新增。

---

## 注意事项

- **Client Secret** 请妥善保管，不要泄露
- 回调 URL 必须与 OAuth 应用配置中的完全一致，格式为：`{应用地址}/api/v1/auth/oauth/callback`
- 本地开发时，Homepage URL 和 Callback URL 可使用 `http://localhost:端口`
