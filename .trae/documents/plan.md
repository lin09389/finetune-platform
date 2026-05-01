# 推理后端问题分析与修复计划

经过对 `server/api/` 和 `server/core/inference/` 目录的全面探索，发现了以下核心功能堵点、伪实现和严重 Bug。

## 一、当前问题诊断

### 1. 伪实现 (Pseudo-Implementations)

* **性能监控体系断层**：

  * `server/api/inference/performance.py`（旧版）或 `core/performance.py` 虽然定义了性能统计逻辑和优化建议（如 `PerformanceMetrics`、`get_recommendations`），**但在实际的推理生成（`routes.py`** **的** **`/chat`、`/generate`** **等）中根本没有调用** **`monitor.record()`** **记录真实数据**。所有的监控指标只在测试用例中被调用，导致前端面板读取的性能数据是空壳或伪实现。

### 2. 功能堵点 (Functional Blockers)

* **全局断路器和降级覆盖不全**：

  * 在 `server/api/inference/routes.py` 中，全局的 `InferenceCircuitBreaker`（支持失败自动降级到 Cloud 后端）**仅被用于非流式的** **`/generate`** **接口**。而最核心、高频使用的 `/chat`、`/chat/stream` 和 `/generate/stream` 完全处于无保护状态。

* **流式输出缺乏重试与局部断路器**：

  * 在 `OllamaResilientBackend` 中，非流式的 `chat`/`generate` 接入了 `CircuitBreaker` 和带指数退避的 `_retry_with_backoff`。但是，流式接口 `chat_stream` 和 `generate_stream` **没有应用任何重试或断路器机制**，一旦遇到网络抖动会直接抛异常断开流。

### 3. 严重 Bug (Critical Bugs)

* **HuggingFace 引擎 Chat Template 硬编码**：

  * `HuggingFaceBackend._format_chat_prompt` 方法错误地使用硬编码的 `System:`, `User:`, `Assistant:` 来拼接对话历史。现代主流模型（Qwen, Llama 3, GLM 等）都有自己专属的控制 Token，不使用 `tokenizer.apply_chat_template` 会导致模型无法正确理解角色边界，输出严重幻觉或乱码。

* **HuggingFace 流式获取逻辑隐患**：

  * `HuggingFaceBackend.generate_stream` 中使用了 `TextIteratorStreamer` 和 `queue.get`。如果队列读取抛出 `queue.Empty`，代码试图通过检查 `thread.is_alive()` 退出。但在高并发或特殊情况下这容易造成流式中断或线程资源泄露。

***

## 二、修复计划 (Proposed Changes)

### Step 1: 修复 HuggingFace 的 Chat Template 和流式 Bug

* **目标文件**: `server/api/inference/backends/huggingface.py`

* **修改动作**:

  1. 重构 `_format_chat_prompt`：如果 `tokenizer` 具备 `apply_chat_template` 属性，则优先使用 `tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)`。
  2. 修复 `generate_stream` 迭代器逻辑：移除容易死锁的 `queue.get` 方式，直接使用标准的 `async for text in asyncio.to_thread(lambda: list(streamer))` 或将 streamer 作为普通迭代器用异步生成器包裹。
  3. 优化 `generate`：摒弃效率较低且容易截取越界的 `pipeline`，改用底层的 `model.generate()`。

### Step 2: 补全流式接口的断路器和降级逻辑 (功能堵点)

* **目标文件**: `server/api/inference/routes.py`

* **修改动作**:

  1. 将 `/chat`, `/chat/stream`, `/generate/stream` 全面接入 `circuit_breaker.execute_with_protection`。
  2. 对于流式接口，封装一个支持降级到 Cloud 后端的生成器（当尝试获取首个 token 失败且断路器开启时触发回退）。

### Step 3: 为 Ollama 补充流式重试能力 (功能堵点)

* **目标文件**: `serv``er/api/i``nference/backends/ollama_resilient.py`

* **修改动作**:

  1. 将 `generate_stream` 和 `chat_stream` 的发起请求部分包裹进 `_retry_with_backoff`（仅在尚未产生任何有效 chunk 时重试）。

### Step 4: 激活真实的性能监控 (伪实现)

* **目标文件**: `server/api/inference/routes.py`

* **修改动作**:

  1. 引入 `core.performance.get_performance_monitor()`。
  2. 在各个接口请求结束时，基于 `GenerationResult` 或统计的 `duration_ms` / `tokens_generated`，构造 `PerformanceMetrics` 和 `StreamingMetrics`，调用 `monitor.record()` 写入真实指标，激活 InsightPanel 监控看板。

## 三、验证步骤 (Verification)

1. 运行 `pytest server/tests/test_inference.py` 确保非流式和流式生成未被破坏。
2. 启动服务，发送流式请求并强制断开 Ollama，验证 CircuitBreaker 是否进入 Open 状态并成功降级。
3. 访问前端或调用 `/inference/performance`，确认能拉取到真实的吞吐量（TPS）、首字延迟和历史指标。

