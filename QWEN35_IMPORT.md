# Qwen3.5 2B 模型导入指南

## 概述

本项目现已支持从魔搭社区（ModelScope）导入已下载的 Qwen3.5 2B 模型。

## 前置条件

1. **已完成模型下载**：从魔搭社区下载 Qwen3.5 2B 模型
   - 下载路径：`C:\Users\<用户名>\.cache\modelscope\hub\models\Qwen\Qwen3.5-2B`
   - 模型大小：约 4GB

2. **后端服务运行中**：确保 `python server/main.py` 已启动

3. **前端应用运行中**：确保 `npm run dev` 已启动

## 使用方法

### 方法一：前端界面导入（推荐）

1. 打开浏览器访问 `http://localhost:5173`
2. 进入 **模型管理** 页面
3. 点击 **导入 ModelScope 模型** 按钮
4. 在弹出窗口中：
   - **模型名称**：默认为 `Qwen3.5-2B`（可自定义）
   - **ModelScope 路径**：可选，不填则使用默认路径
5. 点击 **开始导入**
6. 等待导入完成，成功后即可在模型列表中看到 Qwen3.5-2B

### 方法二：API 调用

```bash
# 使用默认路径
curl -X POST http://127.0.0.1:8000/model-center/import-modelscope \
  -H "Content-Type: application/json" \
  -d '{"model_name": "Qwen3.5-2B"}'

# 使用自定义路径
curl -X POST http://127.0.0.1:8000/model-center/import-modelscope \
  -H "Content-Type: application/json" \
  -d '{
    "model_name": "Qwen3.5-2B",
    "modelscope_path": "C:\\Users\\<用户名>\\.cache\\modelscope\\hub\\models\\Qwen\\Qwen3.5-2B"
  }'
```

### 方法三：Python 脚本

```python
import requests

response = requests.post(
    'http://127.0.0.1:8000/model-center/import-modelscope',
    json={
        'model_name': 'Qwen3.5-2B',
        'modelscope_path': None  # None 表示使用默认路径
    }
)

print(response.json())
```

## API 端点说明

### POST `/model-center/import-modelscope`

**请求参数：**

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| model_name | string | 否 | 模型名称，默认 `Qwen3.5-2B` |
| modelscope_path | string | 否 | ModelScope 缓存路径，不填使用默认路径 |

**响应示例：**

```json
{
  "message": "导入成功",
  "model_id": "Qwen3.5-2B",
  "path": "C:\\Users\\JHJ\\Desktop\\finetune-platform\\server\\models\\Qwen3.5-2B",
  "size": 4294967296,
  "source": "modelscope"
}
```

## 故障排查

### 1. 路径不存在错误

**错误信息：**
```
ModelScope 模型路径不存在：C:\Users\<用户名>\.cache\modelscope\hub\models\Qwen\Qwen3.5-2B
```

**解决方案：**
- 确认模型已从魔搭社区下载完成
- 检查备用路径：`C:\Users\<用户名>\.modelscope\hub\models\Qwen\Qwen3.5-2B`
- 使用自定义路径参数指定实际下载位置

### 2. 模型名称已存在

**错误信息：**
```
模型名称已存在：Qwen3.5-2B
```

**解决方案：**
- 使用不同的模型名称，如 `Qwen3.5-2B-v1`
- 或删除已有模型：`DELETE /model-center/local/Qwen3.5-2B`

### 3. 目录中未找到模型文件

**错误信息：**
```
目录中未找到模型文件（需要 .safetensors/.bin/.gguf 或 config.json）
```

**解决方案：**
- 确认 ModelScope 下载目录包含完整的模型文件
- 检查是否包含 `config.json` 或 `.safetensors`/`.bin` 文件

## 模型规格

| 参数 | 值 |
|------|-----|
| 模型名称 | Qwen3.5 2B |
| 参数量 | 2B |
| 文件大小 | ~4GB |
| 推荐显存 | 8GB+ (INT4 量化) |
| 适用场景 | 中文对话、代码生成、轻量级任务 |

## 导入后使用

导入完成后，Qwen3.5-2B 将出现在：

1. **模型管理列表** - 可查看、删除
2. **推理服务** - 可用于文本生成
3. **微调训练** - 可作为基础模型进行 LoRA/QLoRA 微调
4. **对话界面** - 可作为聊天模型使用

## 技术实现

### 后端

- **文件**: `server/api/model_center.py`
- **新增端点**: `POST /model-center/import-modelscope`
- **功能**:
  - 自动检测 ModelScope 默认缓存路径
  - 支持自定义路径
  - 复制模型文件到项目目录
  - 创建模型元数据文件

### 前端

- **文件**: `client/src/pages/ModelManager.tsx`
- **新增组件**: ModelScope 导入对话框
- **功能**:
  - 可视化导入界面
  - 默认路径提示
  - 自定义路径支持
  - 导入进度显示

## 相关文件

- 后端 API: `server/api/model_center.py`
- 前端页面：`client/src/pages/ModelManager.tsx`
- API 服务：`client/src/services/api.ts`
- 配置：`server/core/config.py`

## 更新日志

**2026-03-09**
- ✅ 添加 Qwen3.5 2B 到推荐模型列表
- ✅ 实现 ModelScope 导入 API
- ✅ 前端集成导入界面
- ✅ 支持默认路径和自定义路径
- ✅ 完整的错误处理和验证
