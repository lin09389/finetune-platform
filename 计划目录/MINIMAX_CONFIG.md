# MiniMax 配置指南

## 新增配置项

现在支持以下三个配置项：

| 配置项 | 必填 | 说明 |
|--------|------|------|
| **Group ID** | 可选 | 你的 MiniMax 用户/组织 ID |
| **Base URL** | 可选 | 自定义 API 端点（默认：`https://api.minimax.chat/v1`） |
| **API Key** | 必填 | 你的 MiniMax API Key |

## 配置方式

### 方式 1：前端 UI 配置（推荐）

1. 打开应用，点击右上角 **☁️ 云端** 按钮
2. 在配置页面填写：
   - **Group ID**（可选）
   - **Base URL**（可选，留空使用默认值）
   - **API Key**（必填）
3. 点击 **保存配置**

### 方式 2：直接调用 API

```bash
POST http://127.0.0.1:8000/cloud/api-keys
Content-Type: application/json

{
  "provider": "minimax-coding",
  "group_id": "your_group_id",
  "base_url": "https://api.minimax.chat/v1",
  "api_key": "your_api_key",
  "name": "my-minimax-key"
}
```

## 聊天调用

```bash
POST http://127.0.0.1:8000/cloud/chat/stream
Content-Type: application/json

{
  "provider": "minimax-coding",
  "key_id": "key_xxxxx",  // 使用加密存储的 Key ID
  "group_id": "your_group_id",  // 可选，会覆盖存储的值
  "base_url": "https://api.minimax.chat/v1",  // 可选
  "model": "mini max2.5",
  "messages": [{"role": "user", "content": "你好"}],
  "stream": true
}
```

## 兼容性说明

- **旧格式兼容**：API Key 仍支持 `group_id:api_key` 格式
- **优先级**：调用时传入的参数 > 存储的配置
- **加密存储**：所有敏感数据都会加密存储到 `.vault` 文件

## 常见问题

### Q: Group ID 是什么？
A: Group ID 是 MiniMax 的用户/组织标识符，某些账户类型需要。如果你不知道，可以留空。

### Q: 什么时候需要自定义 Base URL？
A: 通常不需要。只有当你使用代理、私有部署或特殊网络环境时才需要修改。

### Q: 如何切换不同的 API Key？
A: 可以创建多个 Key，每个都有独立的 `key_id`，调用时指定即可。
