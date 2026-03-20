# 模型中心改造计划：使用魔搭社区下载模型

## 概述

将模型中心的模型下载源从 HuggingFace 改为魔搭社区（ModelScope），提供更稳定、更快速的国内下载体验。

## 当前架构分析

### 后端文件
- `server/api/models.py` - 基础模型管理 API（使用 `huggingface_hub.snapshot_download`）
- `server/api/model_center.py` - 模型中心 API（支持 HF 镜像源和 ModelScope 导入）
- `server/core/config.py` - 配置管理（支持 HF_MIRROR 配置）

### 前端文件
- `client/src/pages/ModelHub.tsx` - 模型中心页面（搜索和下载 HuggingFace 模型）
- `client/src/pages/ModelManager.tsx` - 模型管理页面（支持下载和导入 ModelScope 模型）
- `client/src/services/api.ts` - API 服务

### 当前问题
1. 主要使用 HuggingFace 作为下载源，国内访问不稳定
2. ModelScope 仅作为导入功能，不是主要下载源
3. 搜索功能依赖 HuggingFace API

## 实施计划

### 第一阶段：后端改造

#### 1.1 添加 ModelScope SDK 依赖
**文件**: `server/requirements.txt`
- 添加 `modelscope` 包依赖

#### 1.2 更新配置文件
**文件**: `server/core/config.py`
- 添加 ModelScope 相关配置项
- 设置默认下载源为 ModelScope
- 保留 HuggingFace 作为备用源选项

#### 1.3 重构模型中心 API
**文件**: `server/api/model_center.py`

主要修改：
- **搜索功能**: 使用 ModelScope API 搜索模型
- **下载功能**: 使用 `modelscope.snapshot_download` 替代 `huggingface_hub.snapshot_download`
- **推荐模型**: 更新为 ModelScope 格式的模型 ID
- **网络状态检查**: 添加 ModelScope 连接状态检测

新增功能：
- `POST /model-center/search-modelscope` - 搜索 ModelScope 模型
- `POST /model-center/download-modelscope` - 从 ModelScope 下载模型
- `GET /model-center/modelscope-models` - 获取 ModelScope 热门模型列表

#### 1.4 更新基础模型管理 API
**文件**: `server/api/models.py`
- 更新下载逻辑支持 ModelScope
- 保持向后兼容性

### 第二阶段：前端改造

#### 2.1 更新模型中心页面
**文件**: `client/src/pages/ModelHub.tsx`
- 更新标题为"搜索魔搭社区模型"
- 更新搜索提示为 ModelScope 格式
- 更新推荐模型列表（使用 ModelScope 模型 ID）
- 添加数据源切换选项（ModelScope / HuggingFace）

#### 2.2 更新模型管理页面
**文件**: `client/src/pages/ModelManager.tsx`
- 更新热门模型列表为 ModelScope 格式
- 更新下载弹窗显示
- 移除单独的"导入 ModelScope 模型"功能（已整合到主下载流程）

#### 2.3 更新 API 服务
**文件**: `client/src/services/api.ts`
- 添加 ModelScope 搜索 API
- 添加 ModelScope 下载 API
- 更新推荐模型获取 API

### 第三阶段：测试与文档

#### 3.1 测试
- 测试 ModelScope 模型搜索
- 测试 ModelScope 模型下载
- 测试下载进度显示
- 测试本地模型管理

#### 3.2 更新文档
- 更新 CLAUDE.md 中的模型下载说明
- 更新 .env 配置说明

## 详细实施步骤

### Step 1: 更新 requirements.txt
```txt
# 添加 ModelScope SDK
modelscope>=1.10.0
```

### Step 2: 更新 core/config.py
```python
# 添加 ModelScope 配置
model_source: Literal["modelscope", "huggingface"] = Field(
    default="modelscope",
    description="模型下载源：modelscope/huggingface"
)
modelscope_cache_dir: Optional[Path] = Field(
    default=None,
    description="ModelScope 缓存目录"
)
```

### Step 3: 重构 model_center.py
主要改动：
1. 导入 ModelScope SDK
2. 实现 ModelScope 搜索功能
3. 实现 ModelScope 下载功能
4. 更新推荐模型列表

### Step 4: 更新前端页面
1. 更新 ModelHub.tsx 的搜索和显示逻辑
2. 更新 ModelManager.tsx 的模型列表
3. 更新 api.ts 的 API 调用

## ModelScope 模型 ID 格式

ModelScope 使用以下格式的模型 ID：
- `Qwen/Qwen2.5-0.5B-Instruct`
- `THUDM/chatglm3-6b`
- `damo/nlp_structbert_chinese-base`

与 HuggingFace 格式兼容，但部分模型名称可能略有不同。

## API 变更

### 新增端点
| 端点 | 方法 | 描述 |
|------|------|------|
| `/model-center/search-modelscope` | POST | 搜索 ModelScope 模型 |
| `/model-center/download-modelscope` | POST | 从 ModelScope 下载模型 |
| `/model-center/modelscope-trending` | GET | 获取 ModelScope 热门模型 |

### 修改端点
| 端点 | 变更 |
|------|------|
| `/model-center/search` | 默认使用 ModelScope API |
| `/model-center/download` | 默认使用 ModelScope SDK |
| `/model-center/suggestions` | 返回 ModelScope 格式的推荐模型 |

## 风险与缓解

### 风险 1: ModelScope SDK 兼容性
- **缓解**: 保留 HuggingFace 作为备用下载源

### 风险 2: 模型格式差异
- **缓解**: 下载后自动检测并转换格式

### 风险 3: 用户习惯
- **缓解**: 提供数据源切换选项

## 预期效果

1. **下载速度提升**: 国内用户下载速度显著提升
2. **稳定性提升**: 减少因网络问题导致的下载失败
3. **用户体验优化**: 统一的模型下载流程
4. **向后兼容**: 保留 HuggingFace 作为备用选项

## 文件修改清单

| 文件 | 操作 | 优先级 |
|------|------|--------|
| `server/requirements.txt` | 修改 | 高 |
| `server/core/config.py` | 修改 | 高 |
| `server/api/model_center.py` | 重构 | 高 |
| `server/api/models.py` | 修改 | 中 |
| `client/src/pages/ModelHub.tsx` | 修改 | 高 |
| `client/src/pages/ModelManager.tsx` | 修改 | 中 |
| `client/src/services/api.ts` | 修改 | 高 |
