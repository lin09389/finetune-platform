# Ollama 连接稳定性 - 快速开始

## 5 分钟快速修复指南

### 步骤 1: 更新后端配置 (1 分钟)

编辑 `.env` 文件,添加以下配置:

```bash
# Ollama 优化配置
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_TIMEOUT=60
OLLAMA_MAX_CONNECTIONS=10
OLLAMA_MAX_RETRIES=3
```

重启后端服务:

```bash
cd server
python -m uvicorn main:app --reload
```

### 步骤 2: 前端集成连接状态指示器 (3 分钟)

#### 方案 A: 在 Chat 页面顶部添加

编辑 `client/src/pages/Chat/index.tsx`:

```tsx
// 1. 导入组件
import { OllamaConnectionStatus } from '../../components/OllamaConnectionStatus'

// 2. 在页面顶部添加
function Chat() {
  return (
    <div>
      <div style={{ padding: '8px 16px', borderBottom: '1px solid #f0f0f0' }}>
        <OllamaConnectionStatus showDetails={true} />
      </div>
      <ChatInterface />
    </div>
  )
}
```

#### 方案 B: 在全局 Header 中添加

编辑 `client/src/components/HeaderBar.tsx`:

```tsx
import { OllamaConnectionStatus } from './OllamaConnectionStatus'

function HeaderBar() {
  return (
    <Header>
      <div style={{ float: 'right' }}>
        <OllamaConnectionStatus showDetails={false} />
      </div>
    </Header>
  )
}
```

### 步骤 3: 验证效果 (1 分钟)

1. 启动前端:
```bash
cd client
npm run dev
```

2. 打开浏览器访问 Chat 页面

3. 观察连接状态指示器:
   - ✅ 绿色 = 已连接
   - ⚠️ 黄色 = 未连接
   - ❌ 红色 = 连接失败

4. 测试自动重连:
   - 停止 Ollama: `pkill ollama`
   - 等待状态变为"未连接"
   - 重启 Ollama: `ollama serve`
   - 30 秒内自动恢复连接

## 完成! 🎉

现在你的 Ollama 连接已经具备:
- ✅ 自动重连机制
- ✅ 连接池管理
- ✅ 断路器保护
- ✅ 健康检查
- ✅ 心跳检测
- ✅ 可视化状态

## 故障排查

### 问题: 状态一直显示"未连接"

```bash
# 检查 Ollama 是否运行
curl http://localhost:11434/api/tags

# 如果失败,启动 Ollama
ollama serve
```

### 问题: 断路器频繁打开

增加失败阈值:

```typescript
useOllamaConnection({
  maxFailures: 10,  // 从 5 增加到 10
})
```

### 问题: 连接超时

增加超时时间:

```bash
# .env
OLLAMA_TIMEOUT=120  # 从 60 增加到 120
```
