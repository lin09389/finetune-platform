# 变更日志 (Changelog)

## [2.0.0] - 2024-01-01

### 🎉 重大更新

#### 新增功能
- ✅ **线程安全训练管理**
  - 使用 asyncio.Lock 实现异步状态管理
  - 支持并发训练任务
  - 修复竞态条件问题

- ✅ **断点续训**
  - 自动保存检查点
  - 支持从任意检查点恢复训练
  - 可配置检查点间隔

- ✅ **数据集统计分析**
  - 自动计算样本数、平均长度
  - 角色分布统计
  - 消息长度分布

- ✅ **模型导出功能**
  - ONNX 格式导出
  - 预留 GGUF 支持

#### 安全增强
- 🔒 **文件上传校验**
  - MIME 类型验证
  - 文件大小限制
  - JSON 格式验证
  - 路径遍历防护

- 🔒 **API 安全**
  - 速率限制中间件
  - 可配置 CORS
  - 请求日志记录

#### 配置管理
- ⚙️ **pydantic-settings**
  - 集中配置管理
  - 环境变量验证
  - 类型安全配置

#### 日志系统
- 📝 **结构化日志**
  - JSON 格式选项
  - 分级别日志
  - 独立日志目录

#### 测试套件
- 🧪 **完整测试覆盖**
  - pytest 后端测试
  - vitest 前端测试
  - 测试覆盖率报告

#### Docker 支持
- 🐳 **容器化部署**
  - docker-compose 配置
  - GPU 加速支持
  - 多服务编排

#### 文档
- 📖 **完善文档**
  - API 使用指南
  - Docker 部署文档
  - 代码注释

### 🔧 技术改进

#### 后端
- 重构训练 API，使用线程安全状态管理
- 添加 core 模块（config、logging、training_state、utils）
- 更新所有 API 模块使用新配置系统
- 添加全局异常处理
- 优化显存管理

#### 前端
- 添加 TypeScript 严格模式
- 新增类型定义（device、training、model、dataset、inference）
- 添加工具函数（format）
- 配置 Prettier 代码格式化
- 添加 ESLint 配置

#### 依赖更新
```
# 新增
pydantic-settings==2.1.0
pytest==7.4.3
pytest-asyncio==0.23.2
pytest-cov==4.1.0
httpx==0.26.0
python-json-logger==2.0.7
onnx==1.15.0
onnxruntime==1.16.3
python-magic==0.4.27

# 前端新增
vitest==1.1.0
@vitest/ui==1.1.0
@vitest/coverage-v8==1.1.0
@testing-library/react==14.1.2
@testing-library/jest-dom==6.1.5
eslint-config-prettier==9.1.0
prettier==3.1.1
```

### 📝 配置变更

#### 环境变量
```bash
# 新增
LOG_LEVEL=INFO
LOG_FORMAT=text
MAX_UPLOAD_SIZE=104857600
ALLOWED_FILE_TYPES=.json,.jsonl
MAX_CONCURRENT_TRAINING=1
ENABLE_CHECKPOINT=true
CHECKPOINT_INTERVAL=500

# 重命名
OLLAMA_BASE_URL (原 OLLAMA_API_URL)
```

#### API 变更
- `GET /training/progress` - 响应字段标准化
- `POST /training/start` - 支持 `resume_from_checkpoint` 参数
- `GET /training/checkpoints/{task_id}` - 新增端点
- `POST /training/resume/{task_id}/{checkpoint}` - 新增端点
- `GET /datasets/{id}/statistics` - 新增端点
- `POST /models/{id}/export/onnx` - 新增端点

### ⚠️ 破坏性变更

#### API 响应格式
```json
// 旧格式
{
  "epoch": 1,
  "status": "running"
}

// 新格式（字段名标准化）
{
  "epoch": 1,
  "status": "running",
  "elapsed_time": 120.5,
  "vram_used": 4.2
}
```

#### 配置字段
- `noUnusedLocals`: false → true
- `noUnusedParameters`: false → true

### 🐛 Bug 修复
- 修复训练过程中显存未释放问题
- 修复多任务状态冲突问题
- 修复文件上传路径安全问题

### 📦 已知问题
- GGUF 导出功能待实现
- 多 GPU 训练支持待完善

---

## [1.0.0] - 2023-12-01

### 初始版本
- 基础训练功能
- 模型下载管理
- 数据集管理
- 简单推理
- Ollama 集成
