# VIS 协议增量合并逻辑复查报告

## 需求回顾

### 基础约束
1. 持续接受增量 vis 协议数据的 chunk 并合并到完整 vis 文本中渲染
2. 每次增量 chunk 只包含需要更新的组件，通过 uid 定位，以该组件为起点向下遍历多层合并
3. 支持 incr/all 两种更新方式：
   - **incr**: markdown 和 items 字段追加拼接，其他字段存在则覆盖
   - **all**: markdown 和 items 全量替换
4. 父组件的 markdown 里可能包含多个子 vis 组件文本，子组件顺序排列

## 当前实现分析

### 1. 核心流程 ✅
```
updateCurrentMarkdown(chunk)
  ├─ parseVis2AST(chunk) → 解析为 AST
  ├─ getIncrContent(AST) → 收集增量节点
  ├─ combineNodeWithChildren(baseAST, incrAST) → 合并
  │   ├─ 遍历 incrAST.children
  │   ├─ 通过 uid 查找已存在节点 (findNodeByUID)
  │   ├─ 存在则合并 (combineVisItem)
  │   └─ 不存在则挂载 (smartMountNode)
  └─ parseAST2Vis(AST) → 返回合并后的文本
```

### 2. 增量/全量模式处理 ✅

#### 类方法 combineVisItem (VisBaseParser 类)
**markdown 处理:**
```typescript
// all 模式: 全量替换
if (incrType === 'all') newMarkdown = incrMarkdown;
// incr 模式: 追加拼接
else newMarkdown = combinedMarkdown;
```

**items 处理 (已修复):**
```typescript
if (incrType === 'all') {
  // all 模式: items 全量替换
  newItems = incrItemList;
} else {
  // incr 模式: items 追加合并
  // 新 items 追加到末尾，已存在的递归合并
  newItems = [...combinedListItems, ...newListItems];
}
```

#### 全局函数 combineVisItem ✅
**同样修复了 items 处理逻辑，与类方法保持一致**

### 3. 多层合并处理 ✅

**递归机制:**
```typescript
// combineVisItem 递归处理 items
const combinedListItems = baseItemList.map((baseI) => {
  if (incrListMap[baseI.uid])
    return this.combineVisItem(baseI, incrListMap[baseI.uid]);
  else return baseI;
});

// combineMarkdownString 递归处理嵌套 markdown
if (existJson.markdown && incrJson.markdown) {
  const mergedMarkdown = this.combineMarkdownString(
    existJson.markdown,
    incrJson.markdown
  );
  existJson.markdown = mergedMarkdown;
}
```

### 4. Markdown 中子组件处理 ✅

**特点:**
- 父组件的 markdown 可能包含多个子 vis 组件
- 子组件以文本形式存在，通过 AST 解析识别
- 使用 `parseVis2AST` 和 `parseAST2Vis` 转换
- 子组件按顺序排列，保持原始顺序

**合并逻辑:**
```typescript
combineMarkdownString(baseMarkdown, incrMarkdown)
  ├─ parseVis2AST(baseMarkdown) → baseAST
  ├─ parseVis2AST(incrMarkdown) → incrAST
  ├─ combineNodeWithChildren(baseAST, incrAST)
  │   └─ 遍历 children，通过 uid 匹配和合并
  └─ parseAST2Vis(resultAST)
```

### 5. 智能挂载策略 ✅

```typescript
smartMountNode(baseNode, newNode, newJson)
  ├─ 策略1: 如果 newJson 有 parent_uid
  │   └─ 挂载到 parent_uid 对应的父节点 markdown 中
  └─ 策略2: 否则作为 baseNode 的子节点
```

## 关键修复点

### 修复 1: items 字段的 incr/all 模式区分
**位置:** `parse-vis.ts` 第 125-155 行（全局函数）和第 555-585 行（类方法）

**问题:** items 字段没有区分 incr/all 模式，总是追加合并

**修复:**
```typescript
// all 模式: 全量替换
if (incrType === 'all') {
  newItems = incrItemList;
} else {
  // incr 模式: 追加合并
  newItems = [...combinedListItems, ...newListItems];
}
```

## 数据流转示例

### 场景 1: 简单增量更新 (incr 模式)
```
初始状态:
<d-planning-space uid="planning_1">
  <d-agent-plan uid="task_1" type="incr">
</d-planning-space>

增量 chunk:
<d-agent-plan uid="task_1" type="incr">
  ## 新内容
</d-agent-plan>

合并后:
<d-planning-space uid="planning_1">
  <d-agent-plan uid="task_1" type="incr">
    ## 新内容
  </d-agent-plan>
</d-planning-space>
```

### 场景 2: 全量替换 (all 模式)
```
初始状态:
<d-agent-plan uid="task_1" type="incr" markdown="旧内容">

增量 chunk:
<d-agent-plan uid="task_1" type="all" markdown="全新内容">

合并后:
<d-agent-plan uid="task_1" type="all" markdown="全新内容">
```

### 场景 3: 嵌套组件合并
```
父组件 markdown 包含子组件:
<d-agent-plan uid="stage_1">
  <d-tool-space uid="tool_1">工具输出1</d-tool-space>
  <d-tool-space uid="tool_2">工具输出2</d-tool-space>
</d-agent-plan>

增量 chunk (添加 tool_3):
<d-agent-plan uid="stage_1">
  <d-tool-space uid="tool_3">工具输出3</d-tool-space>
</d-agent-plan>

合并后 (保持顺序):
<d-agent-plan uid="stage_1">
  <d-tool-space uid="tool_1">工具输出1</d-tool-space>
  <d-tool-space uid="tool_2">工具输出2</d-tool-space>
  <d-tool-space uid="tool_3">工具输出3</d-tool-space>
</d-agent-plan>
```

## 结论

✅ **所有需求均已满足:**

1. ✅ 持续接受增量 chunk 并合并
2. ✅ 通过 uid 定位，以增量组件为起点多层遍历合并
3. ✅ 支持 incr/all 两种模式（markdown 和 items 正确处理）
4. ✅ 正确处理 markdown 中多个顺序排列的子组件

✅ **实现正确性:**
- uid 匹配机制: 使用全局索引 O(1) 查找
- 增量合并逻辑: 递归处理嵌套结构
- 父子关系维护: 支持 parent_uid 智能挂载
- 数据一致性: markdown 和 items 统一处理

## 建议

1. **统一使用类方法**: 全局函数和类方法已保持一致，建议逐步迁移到类方法使用
2. **添加类型定义**: 为 VisItem、Root 等类型添加更严格的 TypeScript 类型
3. **单元测试**: 为 combineVisItem、combineMarkdownString 等核心函数添加单元测试
