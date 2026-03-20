# Tasks

## Phase 1: 基础架构重构

- [x] Task 1: 创建推理引擎抽象层
  - [x] SubTask 1.1: 定义 InferenceEngine 抽象基类
  - [x] SubTask 1.2: 实现 HuggingFaceEngine 类（重构现有代码）
  - [x] SubTask 1.3: 实现引擎工厂方法
  - [x] SubTask 1.4: 添加引擎配置数据类

- [x] Task 2: 扩展配置系统
  - [x] SubTask 2.1: 在 config.py 中添加推理引擎配置项
  - [x] SubTask 2.2: 添加 Flash Attention 配置
  - [x] SubTask 2.3: 添加批处理配置
  - [x] SubTask 2.4: 添加 KV Cache 配置
  - [x] SubTask 2.5: 添加流式输出配置

## Phase 2: Flash Attention 2 集成

- [x] Task 3: 实现 Flash Attention 2 支持
  - [x] SubTask 3.1: 创建 Flash Attention 检测模块
  - [x] SubTask 3.2: 修改模型加载逻辑支持 flash_attention_2
  - [x] SubTask 3.3: 实现自动降级机制
  - [x] SubTask 3.4: 添加单元测试

## Phase 3: vLLM 引擎集成

- [x] Task 4: 实现 vLLM 引擎
  - [x] SubTask 4.1: 创建 VLLMEngine 类
  - [x] SubTask 4.2: 实现 vLLM 配置转换
  - [x] SubTask 4.3: 实现流式生成支持
  - [x] SubTask 4.4: 添加错误处理和降级逻辑

- [ ] Task 5: vLLM 高级功能
  - [ ] SubTask 5.1: 实现 PagedAttention 配置
  - [ ] SubTask 5.2: 实现前缀缓存 (Prefix Caching)
  - [ ] SubTask 5.3: 实现多 LoRA 适配器支持

## Phase 4: 量化支持

- [ ] Task 6: 实现 GPTQ 量化支持
  - [ ] SubTask 6.1: 添加 auto-gptq 依赖
  - [ ] SubTask 6.2: 实现 GPTQ 模型加载逻辑
  - [ ] SubTask 6.3: 添加模型格式自动检测

- [ ] Task 7: 实现 AWQ 量化支持
  - [ ] SubTask 7.1: 添加 autoawq 依赖
  - [ ] SubTask 7.2: 实现 AWQ 模型加载逻辑

- [ ] Task 8: 实现 GGUF/llama.cpp 支持
  - [ ] SubTask 8.1: 添加 llama-cpp-python 依赖
  - [ ] SubTask 8.2: 创建 LlamaCppEngine 类
  - [ ] SubTask 8.3: 实现 GGUF 模型加载和推理

## Phase 5: 批处理优化

- [ ] Task 9: 实现动态批处理
  - [ ] SubTask 9.1: 创建 DynamicBatcher 类
  - [ ] SubTask 9.2: 实现请求队列管理
  - [ ] SubTask 9.3: 实现批处理超时机制
  - [ ] SubTask 9.4: 集成到推理 API

## Phase 6: KV Cache 优化

- [ ] Task 10: 实现 KV Cache 优化
  - [ ] SubTask 10.1: 实现 KV Cache 量化配置
  - [ ] SubTask 10.2: 优化缓存分配策略
  - [ ] SubTask 10.3: 实现缓存预热功能

## Phase 7: 流式输出优化

- [x] Task 11: 优化后端 SSE 流式传输
  - [x] SubTask 11.1: 创建 OptimizedStreamingResponse 类
  - [x] SubTask 11.2: 实现批量 token 推送
  - [x] SubTask 11.3: 实现背压控制机制
  - [x] SubTask 11.4: 添加流式延迟监控

## Phase 8: 前端渲染优化

- [x] Task 12: 实现前端流式渲染优化
  - [x] SubTask 12.1: 创建 StreamingMessage 组件
  - [x] SubTask 12.2: 实现渐进式 Markdown 渲染
  - [x] SubTask 12.3: 实现打字机效果
  - [x] SubTask 12.4: 优化增量更新逻辑

- [x] Task 13: 实现虚拟滚动
  - [x] SubTask 13.1: 添加 react-virtuoso 依赖
  - [x] SubTask 13.2: 重构 Chat.tsx 消息列表
  - [x] SubTask 13.3: 实现平滑滚动到底部

- [x] Task 14: 优化消息渲染性能
  - [x] SubTask 14.1: 实现代码块懒加载
  - [x] SubTask 14.2: 使用 React.memo 优化组件
  - [x] SubTask 14.3: 优化动画性能（transform/opacity）

- [x] Task 15: 优化 API 调用
  - [x] SubTask 15.1: 实现连接复用
  - [x] SubTask 15.2: 优化请求取消逻辑
  - [x] SubTask 15.3: 实现错误自动重试

## Phase 9: 性能监控

- [x] Task 16: 实现性能监控系统
  - [x] SubTask 16.1: 创建性能指标收集模块
  - [x] SubTask 16.2: 实现性能报告 API
  - [x] SubTask 16.3: 添加自动调优建议

- [ ] Task 17: 更新前端界面
  - [ ] SubTask 17.1: 添加推理引擎选择 UI
  - [ ] SubTask 17.2: 添加性能监控面板
  - [ ] SubTask 17.3: 添加配置优化建议显示

## Phase 10: 测试和文档

- [ ] Task 18: 编写测试
  - [ ] SubTask 18.1: 编写引擎抽象层单元测试
  - [ ] SubTask 18.2: 编写 vLLM 集成测试
  - [ ] SubTask 18.3: 编写批处理测试
  - [ ] SubTask 18.4: 编写性能基准测试
  - [ ] SubTask 18.5: 编写前端渲染性能测试

- [ ] Task 19: 更新文档
  - [ ] SubTask 19.1: 更新 CLAUDE.md 推理部分
  - [ ] SubTask 19.2: 添加推理优化配置说明

# Task Dependencies

- [Task 2] depends on [Task 1]
- [Task 3] depends on [Task 1]
- [Task 4] depends on [Task 1]
- [Task 5] depends on [Task 4]
- [Task 6] depends on [Task 1]
- [Task 7] depends on [Task 1]
- [Task 8] depends on [Task 1]
- [Task 9] depends on [Task 1]
- [Task 10] depends on [Task 4]
- [Task 11] depends on [Task 1]
- [Task 12] depends on [Task 11]
- [Task 13] depends on [Task 12]
- [Task 14] depends on [Task 12]
- [Task 15] depends on [Task 12]
- [Task 16] depends on [Task 1]
- [Task 17] depends on [Task 16]
- [Task 18] depends on [Task 1, Task 4, Task 9, Task 12]
- [Task 19] depends on [Task 18]

# Parallel Execution Groups

**Group 1 (可并行):**
- Task 1 (基础架构)
- Task 2 (配置扩展)

**Group 2 (Task 1 完成后可并行):**
- Task 3 (Flash Attention)
- Task 4 (vLLM 引擎)
- Task 6 (GPTQ 支持)
- Task 7 (AWQ 支持)
- Task 8 (GGUF 支持)
- Task 9 (批处理)
- Task 11 (流式输出优化)
- Task 16 (性能监控)

**Group 3 (依赖 Group 2):**
- Task 5 (vLLM 高级功能)
- Task 10 (KV Cache 优化)
- Task 12 (前端渲染优化)

**Group 4 (Task 12 完成后可并行):**
- Task 13 (虚拟滚动)
- Task 14 (消息渲染优化)
- Task 15 (API 调用优化)

**Group 5 (最后):**
- Task 17 (前端界面更新)
- Task 18 (测试)
- Task 19 (文档)
