# 本地模型推理后端升级推荐与实施计划

根据 Finetune Platform 2.0 的现状约束（**Windows 操作系统、4GB+ 消费级显卡、LoRA/QLoRA 微调支持、FastAPI 异步架构**），目前的推理后端存在以下体验瓶颈：
*   **HuggingFace 引擎**：虽然动态加载 LoRA 方便，但使用 `transformers` + `bitsandbytes` 4-bit 进行逐 Token 生成的效率极低，TTFT（首字延迟）和 TPS（每秒生成 Token 数）在 4GB 显卡上表现糟糕。
*   **Ollama 引擎**：虽然速度快、省显存，但作为一个外部 HTTP Daemon 服务，每次验证微调模型都需要复杂的格式转换（合并权重 -> 转换为 GGUF -> 编写 Modelfile -> ollama create），流程摩擦极大。
*   **vLLM 引擎**：虽然吞吐量极高，但 KV Cache 显存开销极大（4GB 显卡几乎必定 OOM），且原生 Windows 支持不够稳定。

基于以上痛点，为了**极大提高本地模型的推理体验**，我强烈推荐引入 **`llama-cpp-python`** 作为核心本地推理引擎。

---

## 一、核心推荐：`llama-cpp-python` 原生引擎

### 为什么它是最佳选择？
1.  **极致的显存控制 (VRAM Efficiency)**：
    完美契合项目 4GB 显存的底线要求。它支持将神经网络层在 CPU 和 GPU 之间动态分配（通过 `n_gpu_layers` 参数）。即使显存不足以装下整个模型，也不会像 PyTorch/vLLM 那样直接崩溃 (OOM)，而是平滑回退到 CPU 推理。
2.  **原生 Windows 与 CUDA 加速**：
    提供预编译的带有 cuBLAS (CUDA) 加速的 Python Wheel 包，Windows 下无需复杂的编译环境即可获得接近原生的极致生成速度。
3.  **运行时动态 LoRA 挂载 (Killer Feature)**：
    这是最关键的一点！`llama.cpp` 原生支持在加载基础 GGUF 模型的同时，通过指定 `lora_path` 动态挂载额外转换的 LoRA 适配器。无需耗时的合并模型步骤，完美契合微调平台“训练完立即验证”的刚需。
4.  **FastAPI 进程内真异步流式输出**：
    不同于 Ollama 的外部 HTTP 调用，`llama-cpp-python` 直接在当前应用进程中运行，配合异步生成器可以做到极低延迟的真流式输出，同时方便在引擎注销时直接释放内存。

---

## 二、实施计划 (Implementation Plan)

### Step 1: 环境依赖补充
*   **目标文件**: `server/requirements.txt` 和 安装脚本
*   **动作**: 引入 `llama-cpp-python` 依赖，并附带针对 Windows CUDA 环境的安装说明（例如使用特定的 `--extra-index-url` 获取预编译包）。

### Step 2: 核心引擎实现
*   **目标文件**: 新建 `server/core/inference/llama_cpp_engine.py`
*   **动作**:
    1.  实现 `BaseInferenceEngine` 接口。
    2.  在 `load_model` 方法中，实例化 `Llama(model_path=..., n_gpu_layers=-1, ...)`。
    3.  如果传入了 `lora_path`，在初始化时通过 `lora_base` 和 `lora_path` 参数挂载微调适配器。
    4.  在 `chat_stream` 中，封装 `llama.create_chat_completion(..., stream=True)` 为异步生成器，输出标准化的流式 Chunk。

### Step 3: 引擎工厂注册
*   **目标文件**: `server/core/inference/engine_factory.py` 和 `server/api/inference/scheduler.py`
*   **动作**:
    1.  在 `register_default_engines()` 中导入并注册：`InferenceEngineFactory.register("llama-cpp", LlamaCppEngine)`。
    2.  更新 API 层的后端类型枚举（`BackendType`），将其暴露给前端界面。

### Step 4: （可选扩展）快速 LoRA-to-GGUF 转换辅助
*   **说明**: 因为 `llama-cpp-python` 依赖 GGUF 格式，为了配合 PyTorch 的微调输出，可以在 `server/api/models.py` 中补充一个调用 `llama.cpp` 官方 `convert-lora-to-ggml.py` 的快捷命令或接口，实现“微调完成 -> 一键转 GGUF -> 立即推理验证”的丝滑闭环。

---

## 三、验证方式 (Verification)
1.  **环境验证**：在 Windows 4GB 显存设备上，成功通过 `pip install llama-cpp-python --extra-index-url ...` 安装带 GPU 加速的依赖。
2.  **加载验证**：使用 `LlamaCppEngine` 成功加载一个 7B/8B 级别的 Q4_K_M GGUF 模型，显存占用应稳定在 4GB 左右。
3.  **流式推理验证**：通过前端选择 `llama-cpp` 后端发送 Chat 请求，验证流式输出的流畅度、首字延迟 (TTFT) 是否显著优于现有的 `HuggingFaceEngine`。