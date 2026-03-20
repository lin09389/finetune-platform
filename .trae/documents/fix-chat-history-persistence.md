# 修复计划：AI 对话页面历史记录丢失问题

## 问题分析

### 当前问题
用户在 AI 对话页面进行对话后，切换到其他页面再切换回来，对话历史消失。

### 根本原因
1. **消息状态是组件内部状态**：`messages` 和 `currentSessionId` 使用 `useState` 管理，组件卸载后状态丢失
2. **会话未自动创建**：用户开始对话时没有自动创建会话，导致消息无法保存到后端
3. **缺少会话恢复逻辑**：组件加载时没有恢复上次活跃会话

### 代码问题点
- [Chat.tsx:44](file:///c:/Users/JHJ/Desktop/finetune-platform/client/src/pages/Chat.tsx#L44)：`const [messages, setMessages] = useState<Message[]>([])` 
- [Chat.tsx:54](file:///c:/Users/JHJ/Desktop/finetune-platform/client/src/pages/Chat.tsx#L54)：`const [currentSessionId, setCurrentSessionId] = useState<string | null>(null)`
- [Chat.tsx:620-635](file:///c:/Users/JHJ/Desktop/finetune-platform/client/src/pages/Chat.tsx#L620)：只有 `currentSessionId` 存在时才保存消息

## 解决方案

### 方案：使用 Zustand 全局状态 + 自动会话管理

1. **扩展 Zustand Store**
   - 添加 `currentChatSession` 状态（包含 sessionId 和 messages）
   - 使用 persist 中间件自动持久化到 localStorage
   - 添加会话相关的 actions

2. **修改 Chat.tsx**
   - 使用全局 store 管理当前会话状态
   - 发送消息时自动创建会话（如果不存在）
   - 组件加载时恢复上次活跃会话

3. **添加会话自动保存**
   - 每次消息变化时自动保存到后端
   - 添加防抖机制避免频繁请求

## 实现步骤

### Step 1: 扩展 appStore.ts
- 添加 `currentChatSession` 状态类型
- 添加 `messages`、`currentSessionId` 到持久化配置
- 添加 `setCurrentChatSession`、`clearChatSession`、`addMessage` 等 actions

### Step 2: 修改 Chat.tsx
- 从 store 获取 `messages` 和 `currentSessionId`
- 发送消息时检查并自动创建会话
- 添加 `useEffect` 监听消息变化，自动保存到后端

### Step 3: 添加会话恢复逻辑
- 组件加载时检查是否有活跃会话
- 如果有，从后端加载完整消息历史
- 如果没有，显示空状态

### Step 4: 添加自动保存机制
- 使用防抖保存消息到后端
- 处理保存失败的情况

## 文件修改清单

| 文件 | 修改内容 |
|------|----------|
| `client/src/store/appStore.ts` | 添加聊天会话状态和 actions |
| `client/src/pages/Chat.tsx` | 使用全局状态，添加自动保存逻辑 |

## 预期效果

1. 用户在对话页面进行对话
2. 切换到其他页面
3. 切换回对话页面，历史记录完整保留
4. 刷新页面后，历史记录也能恢复
