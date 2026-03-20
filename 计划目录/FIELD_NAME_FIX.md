# 字段命名修复方案

## 🐛 问题

前端发送驼峰命名（`modelId`），后端期望下划线命名（`model_id`）

## ✅ 解决方案

### 方案 1：修改前端（推荐，简单）

修改 `client/src/pages/Chat.tsx`，发送下划线格式：

```typescript
// 修改前
{
  modelId: selectedModel,
  maxTokens: 1024,
  temperature: 0.7
}

// 修改后
{
  model_id: selectedModel,
  max_tokens: 1024,
  temperature: 0.7
}
```

### 方案 2：修改后端（复杂，已尝试）

Pydantic v2 的 alias 配置不生效，需要同时定义两个字段。

## 🚀 当前状态

由于 inference.py 文件被 PowerShell 命令破坏，建议：

1. **手动恢复 inference.py** - 从备份或重新下载
2. **或者修改前端** - 发送下划线格式字段

## 📝 前端需要修改的地方

### Chat.tsx

找到所有 `streamInference` 调用，修改字段名：

```typescript
// 修改这些字段：
modelId → model_id
maxTokens → max_tokens
topP → top_p
topK → top_k
repetitionPenalty → repetition_penalty
loraAdapter → lora_adapter
```

### api.ts

修改 `streamInference` 函数签名：

```typescript
export const streamInference = async (
  config: {
    model_id: string;  // 改为下划线
    prompt: string;
    max_tokens?: number;  // 改为下划线
    temperature?: number;
    backend?: string;
  },
  ...
)
```

## 🔧 快速修复步骤

1. 在 Chat.tsx 中搜索替换：
   - `modelId` → `model_id`
   - `maxTokens` → `max_tokens`

2. 刷新前端页面

3. 测试推理功能
