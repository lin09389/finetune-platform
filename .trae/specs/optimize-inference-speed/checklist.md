# Checklist

## 基础架构

- [x] InferenceEngine 抽象基类已定义，包含 generate、stream、load、unload 方法
- [x] HuggingFaceEngine 类已实现，功能与原有推理逻辑一致
- [x] 引擎工厂方法可根据配置创建正确的引擎实例
- [x] 引擎配置数据类已创建，包含所有必要参数

## 配置系统

- [x] config.py 已添加 INFERENCE_ENGINE 配置项
- [x] config.py 已添加 ENABLE_FLASH_ATTENTION 配置项
- [x] config.py 已添加批处理相关配置 (MAX_BATCH_SIZE, MAX_BATCH_WAIT_MS)
- [x] config.py 已添加 KV Cache 配置 (KV_CACHE_DTYPE, ENABLE_PREFIX_CACHING)
- [x] config.py 已添加 vLLM 专用配置
- [x] config.py 已添加流式输出配置 (STREAM_BUFFER_SIZE, STREAM_FLUSH_INTERVAL_MS)

## Flash Attention 2

- [x] Flash Attention 检测模块可正确检测 GPU 架构和库安装状态
- [x] 模型加载时自动选择 flash_attention_2 实现（当支持时）
- [x] 不支持时自动降级到 eager 实现，无错误抛出
- [ ] 单元测试覆盖检测和降级逻辑

## vLLM 引擎

- [x] VLLMEngine 类已实现，继承 InferenceEngine
- [x] vLLM 配置可正确转换为 vllm.LLM 参数
- [x] 流式生成使用 vLLM 的异步迭代器
- [x] vLLM 初始化失败时自动降级到 HuggingFace
- [x] PagedAttention 已启用
- [x] 前缀缓存功能已实现
- [ ] 多 LoRA 适配器支持已实现

## 量化支持

- [ ] GPTQ 模型可正确加载和推理
- [ ] AWQ 模型可正确加载和推理
- [ ] GGUF 模型可正确加载和推理
- [ ] 模型格式自动检测功能正常工作
- [ ] 量化模型显存占用符合预期

## 批处理

- [ ] DynamicBatcher 类已实现
- [ ] 并发请求可正确批处理
- [ ] 批处理超时机制正常工作
- [ ] 批处理结果正确分发给各请求

## KV Cache 优化

- [x] KV Cache 量化配置生效
- [x] 缓存分配策略已优化
- [ ] 缓存预热功能正常工作

## 流式输出优化

- [x] OptimizedStreamingResponse 类已实现
- [x] 批量 token 推送功能正常工作
- [x] 背压控制机制有效防止内存溢出
- [x] 流式延迟监控数据准确

## 前端渲染优化

- [x] StreamingMessage 组件已创建
- [x] 渐进式 Markdown 渲染正常工作
- [x] 打字机效果流畅，速度可配置
- [x] 增量更新只更新变化的 DOM 节点

## 虚拟滚动

- [x] react-virtuoso 依赖已添加
- [x] Chat.tsx 消息列表已重构
- [x] 消息超过 100 条时自动启用虚拟滚动
- [x] 滚动到底部功能平滑

## 消息渲染优化

- [x] 代码块懒加载已实现
- [x] ChatMessage 组件使用 React.memo 优化
- [x] 动画使用 transform/opacity，无布局重排

## API 调用优化

- [x] HTTP 连接复用已实现
- [x] 请求取消逻辑正确工作
- [x] 流式连接中断时自动重试

## 性能监控

- [x] 性能指标（tokens/s、延迟、显存）正确收集
- [x] 性能报告 API 返回正确数据
- [x] 自动调优建议合理有效

## 前端界面

- [ ] 推理引擎选择 UI 已添加
- [ ] 性能监控面板已添加
- [ ] 配置优化建议显示正常

## 测试

- [ ] 引擎抽象层单元测试全部通过
- [ ] vLLM 集成测试全部通过
- [ ] 批处理测试全部通过
- [ ] 性能基准测试显示明显提升
- [ ] 前端渲染性能测试全部通过

## 文档

- [ ] CLAUDE.md 推理部分已更新
- [ ] 推理优化配置说明已添加

## 性能验证

- [ ] 7B 模型推理速度达到 50+ tokens/s（使用 vLLM）
- [ ] 首字延迟降低到 200ms 以下
- [ ] 显存占用减少 30% 以上（使用量化）
- [ ] 批处理吞吐量提升 2x 以上
- [ ] 流式输出延迟降低到 10ms 以下
- [ ] 前端渲染帧率达到 60fps
- [ ] 打字机效果流畅无卡顿
