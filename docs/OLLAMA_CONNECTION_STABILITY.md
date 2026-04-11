# Ollama 连接稳定性优化 - 详细文档

## 问题背景

在使用 Ollama API 进行 AI 对话时,可能会遇到以下连接不稳定的问题:

1. **连接超时**: 请求长时间无响应
2. **连接中断**: 流式传输中途断开
3. **频繁重连**: 连接不稳定导致频繁重试
4. **资源泄漏**: 连接未正确关闭导致资源耗尽

## 解决方案架构

### 后端优化 (Python)

#### 1. 增强版 Ollama 后端

文件: `server/api/inference/backends/ollama_resilient.py`

**核心特性**:

- **连接池管理**: 持久化 aiohttp.ClientSession,复用连接
- **断路器模式**: 防止频繁重试失败的服务
- **指数退避重试**: 智能重试机制
- **健康检查**: 主动监控服务状态
- **超时优化**: 合理的超时配置

**配置参数**:

```python
config = {
    "base_url": "http://localhost:11434",
    "timeout": 60,                    # 请求超时(秒)
    "max_connections": 10,            # 最大连接数
    "keepalive_timeout": 30,          # Keep-Alive 超时(秒)
    "max_retries": 3,                 # 最大重试次数
    "retry_delay": 1.0,               # 重试延迟(秒)
    "health_check_interval": 30       # 健康检查间隔(秒)
}
```

**断路器状态**:

- `closed`: 正常状态,请求正常通过
- `open`: 失败次数达到阈值,拒绝请求
- `half_open`: 超时后尝试恢复

### 前端优化 (TypeScript/React)

#### 1. 连接管理 Hook

文件: `client/src/hooks/chat/useOllamaConnection.ts`

**功能**:

- 自动健康检查(30 秒间隔)
- 心跳检测(10 秒间隔)
- 断路器保护(5 次失败触发)
- 自动重连机制

**使用方法**:

```typescript
const { 
  status,           // 连接状态
  isConnected,      // 是否已连接
  isCircuitOpen,    // 断路器是否打开
  failureCount,     // 失败次数
  reconnect,        // 手动重连
  checkHealth       // 手动健康检查
} = useOllamaConnection({
  healthCheckInterval: 30000,
  heartbeatInterval: 10000,
  maxFailures: 5,
  recoveryTimeout: 60000,
  onStatusChange: (status) => {
    console.log('Status changed:', status)
  }
})
```

#### 2. 状态指示器组件

文件: `client/src/components/OllamaConnectionStatus.tsx`

**显示内容**:

- 连接状态图标和文字
- 断路器状态
- 失败次数
- 上次检查时间
- 刷新和重连按钮

**使用方法**:

```tsx
// 详细模式
<OllamaConnectionStatus showDetails={true} />

// 简洁模式
<OllamaConnectionStatus showDetails={false} />

// 带回调
<OllamaConnectionStatus 
  showDetails={true}
  onStatusChange={(status) => {
    if (status === 'error') {
      message.error('Ollama 连接失败')
    }
  }}
/>
```

## 集成步骤

### 1. 后端集成

后端已自动集成,只需配置环境变量:

```bash
# .env
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

### 2. 前端集成

在需要的页面导入并使用组件:

```tsx
import { OllamaConnectionStatus } from '../../components/OllamaConnectionStatus'
import { useOllamaConnection } from '../../hooks/chat/useOllamaConnection'

function ChatPage() {
  const { isConnected, reconnect } = useOllamaConnection()
  
  const handleSend = async () => {
    if (!isConnected) {
      message.warning('Ollama 未连接,正在尝试重连...')
      const success = await reconnect()
      if (!success) {
        message.error('Ollama 连接失败')
        return
      }
    }
    // 发送消息...
  }
  
  return (
    <div>
      <OllamaConnectionStatus showDetails={true} />
      <ChatInterface onSend={handleSend} />
    </div>
  )
}
```

## 性能优化建议

### 1. Ollama 服务配置

```bash
# 增加并发处理能力
export OLLAMA_NUM_PARALLEL=4
export OLLAMA_MAX_LOADED_MODELS=2

# 启动服务
ollama serve
```

### 2. 网络优化

如果 Ollama 在远程服务器,使用 Nginx 反向代理:

```nginx
upstream ollama {
    server localhost:11434;
    keepalive 32;
}

server {
    listen 80;
    
    location /api/ {
        proxy_pass http://ollama;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_buffering off;
        proxy_read_timeout 300s;
    }
}
```

### 3. 模型预加载

```python
# 在应用启动时预加载常用模型
async def preload_models():
    scheduler = get_scheduler()
    backend = await scheduler.get_backend('ollama')
    await backend.load_model('llama3')
```

## 监控和调试

### 后端日志

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# 查看连接池状态
logger.info(f"Circuit breaker state: {backend.circuit_breaker.state}")
```

### 前端调试

```typescript
// 在浏览器控制台查看连接状态
console.log('Ollama status:', useOllamaConnection().status)
```

## 常见问题

### Q1: 连接状态一直显示"未连接"

**解决**:
```bash
# 检查 Ollama 是否运行
ps aux | grep ollama
netstat -an | grep 11434

# 重启 Ollama
ollama serve
```

### Q2: 断路器频繁打开

**解决**:
```typescript
// 增加失败阈值
useOllamaConnection({
  maxFailures: 10,
  recoveryTimeout: 120000
})
```

### Q3: 流式传输中途断开

**解决**:
```bash
# 增加超时时间
OLLAMA_TIMEOUT=120
```

### Q4: 内存占用持续增长

**解决**:
```python
# 定期清理连接池
@app.on_event("shutdown")
async def shutdown():
    backend = await scheduler.get_backend('ollama')
    await backend.cleanup()
```

## 总结

通过以上优化,Ollama API 连接稳定性得到显著提升:

✅ 连接池管理 - 复用连接,减少开销
✅ 断路器模式 - 防止雪崩效应
✅ 自动重试 - 指数退避,智能重试
✅ 健康检查 - 主动监控,及时发现问题
✅ 心跳检测 - 保持连接活跃
✅ 超时优化 - 合理的超时配置
✅ 状态可视化 - 实时显示连接状态

这些改进确保了在网络波动、服务重启等场景下,系统能够自动恢复并保持稳定运行。
