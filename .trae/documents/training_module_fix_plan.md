# 训练模块修复计划

## 1. 概述 (Summary)
针对 `server/api/training.py` 和 `server/agent/intent/train_bert.py` 中存在的多个关键业务逻辑缺陷与潜在问题，制定本修复计划。修复范围涵盖：多线程上下文中的事件循环获取（WebSocket推送失败）、数据预处理时的标签掩码（防止复读机/幻觉）、LoRA+ 学习率分配错误、检查点异步保存导致的数据竞争、断点续训未正确加载优化器状态、以及训练回调中的内存泄漏等严重问题。

## 2. 现状分析 (Current State Analysis)
根据前面的全面审查，目前代码库存在以下高优问题：
1. **WebSocket 推送失效**: `ProgressCallback` 在后台线程初始化时尝试获取 `asyncio.get_running_loop()` 会抛出 `RuntimeError`，导致前端无法接收实时进度。
2. **数据标签未掩码**: SFT 训练时直接 `labels = input_ids.copy()`，模型会学习并预测用户指令（User Prompt）部分，影响模型效果。
3. **LoRA+ 学习率分配反转**: 按照 LoRA+ 论文，应当对 B 矩阵应用较大学习率，而当前代码将放大的学习率分配给了 A 矩阵。
4. **目标模块硬编码兼容性差**: 仅硬编码了 LLaMA 架构的 Q/V/K 等模块名，若使用 Qwen 或 ChatGLM 会导致 LoRA 注入失败。
5. **异步保存检查点引发数据竞争**: 后台线程保存模型权重时，主线程可能正在进行梯度更新（`optimizer.step()`），会导致权重文件损坏或不一致。
6. **断点续训状态丢失**: `trainer.train()` 未传入 `resume_from_checkpoint`，仅恢复了模型权重，丢失了优化器动量和学习率调度器状态。
7. **回调导致内存泄漏**: `ProgressCallback` 强持有 `Trainer` 和 `Model`，形成循环引用。
8. **BERT 训练无梯度裁剪**: 全参数微调 BERT 未控制梯度，容易引发梯度爆炸。

## 3. 建议的修改 (Proposed Changes)

### 修改 1: `server/api/training.py`
*   **WebSocket 线程安全**: 
    *   **What/How**: 在 `start_training` (主异步函数) 中捕获当前的事件循环 `loop = asyncio.get_running_loop()`，并将其作为参数向下透传给 `training_thread` 和 `ProgressCallback`。
*   **数据标签正确掩码**: 
    *   **What/How**: 修改 `load_dataset` 中的 `set_labels` 逻辑。识别分词后的输入中属于用户指令（Prompt）的 token，将其对应的 `labels` 修改为 `-100`（Hugging Face 默认的 ignore_index）。
*   **修复 LoRA+ 学习率**: 
    *   **What/How**: 在 `training_thread` 中，将 `param_groups` 中的 `lora_a_params` 设置为 `base_lr`，将 `lora_b_params` 设置为 `base_lr * config.lora_plus_lr_ratio`。
*   **提升目标模块兼容性**: 
    *   **What/How**: 在 `load_model_and_tokenizer` 中，当 `target_modules == "all"` 时，直接设置 `target_modules_list = "all-linear"`（利用 PEFT 的内置特性支持所有线性层）。
*   **修复异步检查点竞争**: 
    *   **What/How**: 移除 `_save_checkpoint_async` 中使用 `ThreadPoolExecutor` 的后台执行逻辑，改为在当前线程中同步调用 `_do_save_checkpoint()` 以保证数据一致性。
*   **激活完整的断点续训**: 
    *   **What/How**: 在 `trainer.train()` 调用处，修改为 `trainer.train(resume_from_checkpoint=config.resume_from_checkpoint if config.resume_from_checkpoint else None)`。
*   **解决内存泄漏**: 
    *   **What/How**: 在 `ProgressCallback.on_train_end` 中，显式添加 `self.model = None` 和 `self.trainer = None`。

### 修改 2: `server/agent/intent/train_bert.py`
*   **添加梯度裁剪**: 
    *   **What/How**: 在 `BERTTrainer.train` 的训练循环中，在 `total_loss.backward()` 之后、`optimizer.step()` 之前，插入 `torch.nn.utils.clip_grad_norm_(self.model.parameters(), max_norm=1.0)`。

## 4. 假设与决策 (Assumptions & Decisions)
*   **假设**: 当前采用的标准 Hugging Face Trainer 内部自带保存逻辑，但因为 `ProgressCallback` 自定义了带额外状态的检查点保存，所以选择将现有的自定义异步保存逻辑降级为同步保存，牺牲一点保存时的阻塞时间来换取数据的绝对安全。
*   **决策**: 对于标签掩码（Masking），针对不同的数据格式（如 `User: ... \nAssistant: ...`），如果复杂分词对齐成本过高，可采用简化的 `DataCollatorForSeq2Seq` 或正则匹配逻辑进行 `-100` 填充。本计划将实现基础的上下文掩码策略。

## 5. 验证步骤 (Verification Steps)
1. 启动一个快速的 QLoRA 训练任务，通过前端或 WebSocket 客户端检查能否实时收到 Progress 更新（无 `RuntimeError`）。
2. 在 `load_dataset` 断点打印出某个 sample 的 `labels`，检查 User Prompt 对应的 ID 是否被正确替换为 `-100`。
3. 检查断点续训（Resume）功能，确认恢复后训练的 `global_step` 和 `loss` 是否从中断处平滑继续。
4. 运行 `train_bert.py`，确认无梯度爆炸且各项指标正常提升。
