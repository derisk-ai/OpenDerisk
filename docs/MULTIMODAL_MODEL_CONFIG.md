# 多模态模型配置指南

## 功能说明

从现在开始，Agent 的模型配置支持 `is_multimodal` 字段，用于标识模型是否支持图片输入（多模态能力）。

## 配置方式

### 1. TOML 配置文件方式

在 TOML 配置文件中，可以通过以下方式配置多模态模型：

#### 方法 1：使用 `is_multimodal` 字段

```toml
[[agent.llm.provider]]
provider = "openai"
api_base = "https://api.openai.com/v1"
api_key = "${OPENAI_API_KEY:-sk-...}"

[[agent.llm.provider.model]]
name = "gpt-4-vision-preview"
temperature = 0.7
max_new_tokens = 4096
is_multimodal = true  # 多模态模型，支持图片输入

[[agent.llm.provider.model]]
name = "qwen-vl-max"
temperature = 0.7
max_new_tokens = 4096
is_multimodal = true  # 多模态模型，支持图片输入
```

#### 方法 2：使用 `supports_vision` 字段（别名）

```toml
[[agent.llm.provider.model]]
name = "glm-4v"
temperature = 0.7
max_new_tokens = 4096
supports_vision = true  # 与 is_multimodal 效果相同
```

### 2. 系统配置页面方式

在系统配置管理页面（Settings > Config），可以可视化配置多模态模型：

1. 进入 **Settings > Config** 页面
2. 在 **LLM 配置** 区域，找到 Provider 的模型列表
3. 对于每个模型，有一个 **"多模态"** 开关：
   - **支持**：该模型支持图片输入
   - **不支持**：该模型仅支持文本输入
4. 点击 **"保存 LLM 配置"** 保存更改

系统会自动将配置同步到后端和 TOML 配置文件。

### API 使用

### 查询模型是否支持多模态

```python
from derisk.agent.util.llm.model_config_cache import ModelConfigCache

# 检查特定模型是否支持多模态
if ModelConfigCache.is_multimodal("qwen-vl-max"):
    print("该模型支持图片输入")

# 获取所有支持多模态的模型列表
multimodal_models = ModelConfigCache.get_multimodal_models()
print(f"支持图片输入的模型: {multimodal_models}")
```

### 获取模型配置

```python
# 获取模型配置（包含 is_multimodal 字段）
config = ModelConfigCache.get_config("qwen-vl-max")
if config and config.get("is_multimodal"):
    # 使用多模态模型处理图片
    pass
```

## 示例配置文件

查看以下配置文件了解完整的配置示例：

- `configs/derisk-proxy-openai.toml`
- `configs/derisk-proxy-aliyun.toml`

## 默认值

如果配置中没有指定 `is_multimodal` 或 `supports_vision`，默认值为 `false`，表示该模型不支持图片输入。

## 适用场景

多模态模型适用于以下场景：

1. **图片分析**：上传图片并进行内容分析
2. **文档处理**：处理包含图片的文档
3. **图表理解**：理解并分析数据图表
4. **视觉问答**：基于图片内容的问答系统
5. **截图分析**：分析错误截图、UI界面等

## 前端可视化配置界面

### 模型配置页面位置
- **路径**: Settings > Config
- **区域**: LLM 配置 > Provider 模型列表

### 操作步骤
1. 在 Provider 卡片中，找到模型列表
2. 每个模型行包含以下字段：
   - **模型名**: 模型的名称（如 gpt-4-vision）
   - **Temperature**: 温度参数
   - **Max Tokens**: 最大 token 数
   - **多模态**: 开关按钮（支持/不支持）
   - **操作**: 删除按钮
3. 点击"多模态"开关，设置模型是否支持图片输入
4. 点击"保存 LLM 配置"按钮保存更改

### 配置验证
- 保存后，配置会自动同步到后端 `ModelConfigCache`
- 可以通过刷新模型缓存验证配置是否生效
- 在默认模型显示区域会看到"支持图片输入"标识

## 注意事项

1. 多模态模型通常比纯文本模型消耗更多资源
2. 确保模型提供商确实支持视觉能力
3. 在使用图片输入时，注意图片大小和格式限制
4. 不同模型提供商对图片输入的支持方式可能不同
5. 配置页面中的"多模态"字段会自动保存到 TOML 配置文件和 ModelConfigCache