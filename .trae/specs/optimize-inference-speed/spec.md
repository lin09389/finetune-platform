# 推理与对话输出速度优化 Spec

## Why
当前推理服务使用 HuggingFace Transformers 的原生 `generate` 方法，AI 对话的流式输出存在延迟和卡顿问题。通过引入高性能推理引擎、优化量化策略、启用硬件加速特性，并优化前端流式渲染，可以将推理速度提升 2-10 倍，显著改善用户体验。

## What Changes
- 集成 vLLM 高性能推理引擎作为可选后端
- 添加 Flash Attention 2 支持
- 实现多种量化格式支持（GPTQ、AWQ、GGUF）
- 添加动态批处理功能
- 优化 KV Cache 管理
- **优化前端流式输出渲染**
- **实现打字机效果和渐进式显示**
- **优化 SSE 流式传输性能**
- 添加推理性能监控和自动调优
- **BREAKING**: 推理配置结构变更，需要迁移

## Impact
- Affected specs: 推理服务、模型管理、配置系统、聊天界面
- Affected code: 
  - `server/api/inference.py` - 核心推理逻辑
  - `server/core/config.py` - 配置项扩展
  - `server/core/model_cache.py` - 缓存策略优化
  - `server/core/streaming.py` - 流式传输优化
  - `client/src/pages/Chat.tsx` - 聊天界面优化
  - `client/src/components/ChatMessage.tsx` - 消息渲染优化
  - `client/src/services/api.ts` - API 调用优化
  - `server/requirements.txt` - 新增依赖

## ADDED Requirements

### Requirement: vLLM 推理引擎集成
系统应支持 vLLM 作为高性能推理后端，提供 PagedAttention 和连续批处理能力。

#### Scenario: 启用 vLLM 后端
- **WHEN** 用户配置 `INFERENCE_ENGINE=vllm` 且 GPU 支持
- **THEN** 系统使用 vLLM 引擎加载模型，启用 PagedAttention

#### Scenario: vLLM 不可用时自动降级
- **WHEN** vLLM 初始化失败或 GPU 不满足要求
- **THEN** 系统自动降级到 HuggingFace 后端并记录警告

### Requirement: Flash Attention 2 支持
系统应支持 Flash Attention 2 以加速注意力计算，减少显存占用。

#### Scenario: 自动检测并启用 Flash Attention 2
- **WHEN** GPU 架构 >= Ampere (RTX 30系列+) 且已安装 flash-attn
- **THEN** 系统自动启用 Flash Attention 2

#### Scenario: 不支持时静默降级
- **WHEN** GPU 不支持或 flash-attn 未安装
- **THEN** 使用标准注意力机制，不影响功能

### Requirement: 多量化格式支持
系统应支持多种量化格式以适应不同硬件条件。

#### Scenario: 加载 GPTQ 量化模型
- **WHEN** 模型目录包含 GPTQ 配置文件
- **THEN** 使用 auto-gptq 加载量化模型

#### Scenario: 加载 AWQ 量化模型
- **WHEN** 模型目录包含 AWQ 配置文件
- **THEN** 使用 autoawq 加载量化模型

#### Scenario: 加载 GGUF 模型
- **WHEN** 模型文件为 .gguf 格式
- **THEN** 使用 llama-cpp-python 加载模型

### Requirement: 动态批处理
系统应支持请求批处理以提高吞吐量。

#### Scenario: 批量处理并发请求
- **WHEN** 多个推理请求同时到达
- **THEN** 系统自动将请求批处理，共享 KV Cache

#### Scenario: 批处理超时保护
- **WHEN** 批处理等待时间超过配置阈值
- **THEN** 立即处理已收集的请求，不继续等待

### Requirement: KV Cache 优化
系统应优化 KV Cache 管理以减少显存占用和提高速度。

#### Scenario: 启用 PagedAttention (vLLM)
- **WHEN** 使用 vLLM 后端
- **THEN** 启用 PagedAttention，动态分配 KV Cache

#### Scenario: 启用 KV Cache 量化
- **WHEN** 配置启用 KV Cache 量化
- **THEN** 将 KV Cache 压缩为 INT8/FP8 格式

### Requirement: 推理性能监控
系统应提供推理性能监控和自动调优功能。

#### Scenario: 记录推理性能指标
- **WHEN** 每次推理完成
- **THEN** 记录 tokens/s、延迟、显存使用等指标

#### Scenario: 性能报告接口
- **WHEN** 用户请求性能报告
- **THEN** 返回详细的性能统计和建议

### Requirement: 推理配置优化
系统应提供推理配置自动优化功能。

#### Scenario: 根据硬件自动优化配置
- **WHEN** 首次加载模型
- **THEN** 根据 GPU 显存自动选择最佳配置

#### Scenario: 配置持久化
- **WHEN** 用户手动调整配置
- **THEN** 保存配置供后续使用

### Requirement: 流式输出优化
系统应优化 SSE 流式传输以减少延迟。

#### Scenario: 减少流式传输延迟
- **WHEN** 模型生成 token
- **THEN** 立即通过 SSE 推送到前端，延迟 < 10ms

#### Scenario: 批量 token 推送
- **WHEN** 生成速度极快时
- **THEN** 自动合并多个 token 为一个 SSE 事件，减少网络开销

#### Scenario: 背压控制
- **WHEN** 客户端处理速度慢于生成速度
- **THEN** 自动暂停生成，避免内存溢出

### Requirement: 前端流式渲染优化
前端应优化流式内容的渲染性能。

#### Scenario: 渐进式 Markdown 渲染
- **WHEN** 接收到流式内容
- **THEN** 实时渲染已完成的 Markdown 块，不等待完整响应

#### Scenario: 虚拟滚动优化
- **WHEN** 对话消息超过 100 条
- **THEN** 启用虚拟滚动，只渲染可见区域的消息

#### Scenario: 打字机效果
- **WHEN** AI 输出内容
- **THEN** 显示平滑的打字机效果，速度可配置

### Requirement: 消息渲染优化
消息组件应优化渲染性能。

#### Scenario: 代码块懒加载
- **WHEN** 消息包含代码块
- **THEN** 延迟加载代码高亮，不阻塞文本渲染

#### Scenario: 增量更新优化
- **WHEN** 流式内容更新
- **THEN** 只更新变化的 DOM 节点，避免全量重渲染

#### Scenario: 动画性能优化
- **WHEN** 显示打字机效果或动画
- **THEN** 使用 CSS transform 和 opacity，避免触发布局重排

### Requirement: API 调用优化
前端 API 调用应优化性能和可靠性。

#### Scenario: 连接复用
- **WHEN** 多次流式请求
- **THEN** 复用 HTTP 连接，减少握手开销

#### Scenario: 请求取消
- **WHEN** 用户停止生成或切换对话
- **THEN** 立即取消正在进行的请求

#### Scenario: 错误重试
- **WHEN** 流式连接中断
- **THEN** 自动重试，最多 3 次

## MODIFIED Requirements

### Requirement: 推理后端选择
原要求：支持 HuggingFace 和 Ollama 两种后端。

修改后：支持 HuggingFace、Ollama、vLLM、llama.cpp 四种后端，并提供统一接口。

### Requirement: 模型缓存策略
原要求：使用 LRU 缓存，最多缓存 3 个模型。

修改后：使用智能缓存策略，根据显存动态调整缓存大小，支持预热和预加载。

### Requirement: 流式输出
原要求：使用 SSE 流式传输生成内容。

修改后：使用优化的 SSE 流式传输，支持背压控制、批量推送和实时延迟监控。

## REMOVED Requirements
无移除的需求。

## 性能目标

| 优化项 | 当前性能 | 目标性能 | 提升比例 |
|--------|----------|----------|----------|
| 7B 模型推理 (tokens/s) | 15-20 | 50-80 | 3-4x |
| 首字延迟 (ms) | 500-1000 | 100-200 | 5x |
| 显存占用 (7B FP16) | 14GB | 6-8GB | 40%↓ |
| 批处理吞吐量 | N/A | 2-3x 单请求 | 新增 |
| 流式输出延迟 (ms) | 50-100 | < 10 | 5-10x |
| 前端渲染帧率 (fps) | 30-40 | 60 | 1.5x |
| 打字机效果流畅度 | 卡顿 | 丝滑 | 显著改善 |

## 技术方案

### 1. vLLM 集成
```python
class InferenceEngine(ABC):
    @abstractmethod
    async def generate(self, request: InferenceRequest) -> InferenceResponse:
        pass

class VLLMEngine(InferenceEngine):
    def __init__(self, model_path: str, config: VLLMConfig):
        from vllm import LLM, SamplingParams
        self.llm = LLM(model=model_path, **config.to_dict())
```

### 2. Flash Attention 2
```python
def get_attention_implementation():
    if is_flash_attn_2_available():
        return "flash_attention_2"
    return "eager"
```

### 3. 流式输出优化
```python
class OptimizedStreamingResponse:
    def __init__(self, max_buffer_size: int = 10):
        self.buffer = []
        self.max_buffer_size = max_buffer_size
    
    async def push_token(self, token: str):
        self.buffer.append(token)
        if len(self.buffer) >= self.max_buffer_size:
            await self.flush()
```

### 4. 前端渲染优化
```tsx
const StreamingMessage: React.FC = ({ content }) => {
  const [displayContent, setDisplayContent] = useState('')
  const [pendingContent, setPendingContent] = useState('')
  
  useEffect(() => {
    const timer = setInterval(() => {
      if (pendingContent.length > 0) {
        setDisplayContent(prev => prev + pendingContent.slice(0, 5))
        setPendingContent(prev => prev.slice(5))
      }
    }, 16)
    return () => clearInterval(timer)
  }, [pendingContent])
}
```

### 5. 虚拟滚动
```tsx
import { Virtuoso } from 'react-virtuoso'

const ChatMessages = ({ messages }) => (
  <Virtuoso
    data={messages}
    itemContent={(index, message) => (
      <ChatMessage key={message.id} {...message} />
    )}
    followOutput="smooth"
  />
)
```

## 配置项扩展

```bash
# 推理引擎配置
INFERENCE_ENGINE=huggingface  # huggingface/vllm/llamacpp/ollama

# Flash Attention
ENABLE_FLASH_ATTENTION=true

# 批处理配置
ENABLE_BATCHING=true
MAX_BATCH_SIZE=8
MAX_BATCH_WAIT_MS=50

# KV Cache 配置
KV_CACHE_DTYPE=float16  # float16/int8/fp8
ENABLE_PREFIX_CACHING=true

# vLLM 配置
VLLM_GPU_MEMORY_UTILIZATION=0.9
VLLM_MAX_MODEL_LEN=4096
VLLM_TENSOR_PARALLEL_SIZE=1

# 流式输出配置
STREAM_BUFFER_SIZE=10
STREAM_FLUSH_INTERVAL_MS=16
ENABLE_BACKPRESSURE=true

# 前端渲染配置
TYPEWRITER_SPEED=50  # 字符/秒
ENABLE_VIRTUAL_SCROLL=true
VIRTUAL_SCROLL_THRESHOLD=100

# 性能监控
ENABLE_PERF_MONITORING=true
PERF_LOG_INTERVAL=60
```

## 依赖更新

```txt
# 高性能推理
vllm>=0.3.0
flash-attn>=2.5.0

# 量化支持
auto-gptq>=0.6.0
autoawq>=0.1.7
llama-cpp-python>=0.2.20

# 性能监控
prometheus-client>=0.19.0

# 前端依赖
react-virtuoso>=4.7.0
```
