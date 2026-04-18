# 彻底解决推理“假流式”与“阻塞卡顿”问题的架构方案

## 1. 现状分析 (Current State Analysis)
在之前的排查中，我们发现了两个导致首字响应极慢的典型问题：
1. **API 默认行为被忽略**：Ollama 的 `/api/pull` 接口默认开启流式返回，在未显式传递 `"stream": False` 时，立即退出请求上下文会导致连接被强行切断，造成服务端状态异常，从而阻塞后续对话。
2. **“假流式”实现**：HuggingFace 本地后端在 `chat_stream` 中，先阻塞执行完整个 `model.generate`（耗时数秒到一分钟不等），然后才通过 `asyncio.sleep(0.01)` 将结果切词假装成流式返回。这严重破坏了异步事件循环，导致极高的首字延迟（TTFT - Time To First Token）。

这两个问题暴露出当前系统在 **异步边界隔离**、**API 契约约束** 和 **性能可观测性** 方面的缺失。

## 2. 解决目标 (Goals & Success Criteria)
彻底杜绝此类问题，确保所有推理后端都能提供**真正的流式输出**，保障极低的首字延迟，同时避免由于第三方 API 默认参数变更导致的隐蔽 BUG。

*   **首字延迟保障**：流式接口的 TTFT（Time To First Token）应严格反映模型的真实首字生成时间，不受总生成长度的影响。
*   **异步安全**：任何重 CPU 计算（如本地模型推理）或长耗时网络请求，绝不允许阻塞 FastAPI 的主异步事件循环（Event Loop）。
*   **契约测试防退化**：通过自动化测试强制校验“真流式”行为，一旦有人提交“假流式”代码（例如等待所有结果再一次性返回），测试必须阻断。

## 3. 拟定更改方案 (Proposed Changes)

### 阶段一：强制异步计算边界隔离 (Architectural Enforcement)
*   **重构本地推理流式管道**：
    规范化 HuggingFace 等本地后端的真流式标准。强制使用 `TextIteratorStreamer` + 独立后台 `Thread` 的模式。
    通过 `asyncio.to_thread` 或中间 `asyncio.Queue` 桥接同步的生成线程与异步的 FastAPI 响应流，确保模型每吐出一个 Token 就立即下发。
*   **禁止使用 `asyncio.sleep` 模拟流式**：
    审查并移除所有后端（包括可能存在的测试挡板和降级逻辑中）的“假流式”代码。

### 阶段二：API 契约严格化 (Strict API Payload Contracts)
*   **使用 Pydantic 约束第三方 API Payload**：
    不再使用裸字典（`dict`）拼接发往 Ollama 或 Cloud API 的请求。
    为 `/api/pull`、`/api/generate`、`/api/chat` 建立严格的 Pydantic Request Model，强制要求 `stream` 等关键参数必须有明确的布尔值声明，拒绝依赖第三方 API 的黑盒默认值。
*   **连接生命周期隔离**：
    将模型拉取（Pull/Load）的长连接与高频的推理（Chat/Generate）连接池隔离，避免某个拉取请求异常掐断后“毒化”整个连接池。

### 阶段三：引入 TTFT 监控与告警 (Observability)
*   **增强 `StreamingMetrics`**：
    在 `core/performance.py` 中的 `StreamingMetrics` 类加入 `first_token_latency_ms` (首字延迟) 字段。
*   **埋点记录**：
    在 `routes.py` 的 `chat_stream` 生成器中，记录从接收请求到 `yield` 第一个非空内容块之间的时间差。
    如果 TTFT 异常偏高（例如超过 3000ms），在日志中输出 `[WARNING] High TTFT detected: {X}ms, possible blocking operation or fake streaming.`。

### 阶段四：编写流式契约测试 (Contract Testing)
*   **新增针对流式的专项测试**：
    在 `server/tests/test_inference_stream_contract.py` 中，编写一个验证 TTFT 的测试用例：
    *   Mock 底层生成逻辑，使其在 0.1秒吐出第一个字，在 3秒后吐出第二个字。
    *   断言 `chat_stream` 的第一个块在 ~0.1秒到达，而不是被阻塞到 3秒后才一起到达。
    *   通过这种契约测试，彻底堵死未来被误改成“假流式”的可能性。

## 4. 验证与验收 (Verification Steps)
1. 运行所有的流式接口调用，观察日志中输出的 `TTFT` 是否在合理范围内（通常本地小模型 < 500ms，API 调用 < 1s）。
2. 执行 `pytest server/tests/test_inference_stream_contract.py`，验证新增的时间断言测试是否通过。
3. 检查 Ollama 加载大模型时的日志和连接状态，确认不会因为未传 `stream: False` 而引发“连接异常断开”或模型重复重载的问题。