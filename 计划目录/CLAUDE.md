# LocalAI Studio - 开发指南

## 项目背景

基于现有 `finetune-platform` 项目开发**本地 AI 推理平台**（LocalAI Studio）

### 核心目标
- 本地运行开源大模型（Llama、Qwen、Mistral 等）
- 数据私有、无需联网
- MVP 核心功能：模型管理、模型对话、RAG 知识库、API 服务

### 技术栈
- **前端**: React + TypeScript + Vite + Ant Design + Zustand
- **后端**: Python + FastAPI
- **桌面框架**: Electron
- **推理引擎**: llama.cpp（待集成）

## 开发优先级

### P0 - MVP 核心（第 1 周）
1. **聊天界面** - 新增 Chat 页面，支持流式对话
2. **多模型切换** - 支持加载和切换不同模型
3. **对话历史** - 本地存储对话记录

### P1 - 增强功能（第 2 周）
1. **模型下载管理** - 集成 HuggingFace，支持模型浏览和下载
2. **API 服务** - 提供 RESTful API 供外部调用

### P2 - 高级功能（第 3-4 周）
1. **RAG 知识库** - 文档上传、向量检索
2. **可视化工作流** - 拖拽式 Agent 编排

## 项目结构

```
finetune-platform/
├── client/                 # React 前端
│   └── src/
│       ├── pages/         # 页面组件
│       ├── components/    # 通用组件
│       └── store/         # Zustand 状态管理
├── server/                # FastAPI 后端
│   └── api/
│       ├── inference.py   # 推理 API（需扩展）
│       └── models.py      # 模型管理 API
├── electron/              # Electron 主进程
└── models/                # 模型存储
```

## 开发约束

- 用户编程经验 6 个月 -1 年，Python 熟练，会 React/Vue
- 开发时间：每晚 19:00-22:00（3 小时/天）
- 难度适中，跳一跳够得着
- 优先复用现有代码，避免重写

## 现有资源

- 已有模型：`models/Qwen--Qwen2.5-0.5B-Instruct`
- 已有推理 API：`server/api/inference.py`
- 已有前端页面：`client/src/pages/Inference.tsx`

## 开发原则

1. **小步快跑** - 每天完成一个小功能
2. **先跑起来** - 先实现基础功能，再优化
3. **复用优先** - 能用现有的就不重写
4. **文档同步** - 代码和文档一起更新

## 常用命令

```bash
# 启动开发环境
npm run dev              # 前端
python server/main.py    # 后端

# Electron 打包
npm run electron:dev
```

## 注意事项

- 所有模型数据本地存储，不上传云端
- 支持 Windows 环境开发
- 优先使用已有 Ant Design 组件
- 状态管理使用 Zustand
