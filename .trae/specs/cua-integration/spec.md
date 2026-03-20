# Computer Use Agent 集成方案 Spec

## Why

当前 finetune-platform 项目已具备基础的 Agent 执行、Skills 系统、三级记忆架构等功能，但与 OpenClaw 等领先的 Computer Use Agent (CUA) 项目相比，存在显著差距：

- **缺失屏幕感知能力** - 无法"看见"屏幕，无法进行视觉理解
- **缺失桌面操作能力** - 无法模拟鼠标点击、键盘输入、GUI自动化
- **Skills 系统与记忆系统未打通** - 技能无法读取系统记忆、无法学习用户偏好
- **缺乏 MCP 协议支持** - 无法连接外部工具服务器扩展能力
- **安全边界不完善** - 缺乏沙箱执行和细粒度权限控制

通过集成 Computer Use Agent 能力，平台将实现"通过 Skills 功能读取系统记忆、学习并自如操作电脑"的目标，显著提升自动化能力和用户体验。

## What Changes

### 1. Computer Use Agent 核心模块

- 新增 `server/cua/` 模块，实现 Computer Use Agent 核心
- 实现屏幕截图捕获（Windows GDI/DirectX、macOS ScreenCaptureKit）
- 实现鼠标键盘模拟（PyAutoGUI 集成）
- 实现 GUI 元素识别（OCR + 视觉模型）
- 实现操作录制与回放

### 2. CUA Skills 集成

- 新增 `server/skills/implemented/cua_skills.py` 桌面操作技能
- 实现屏幕截图技能
- 实现鼠标操作技能（点击、移动、拖拽、滚动）
- 实现键盘操作技能（输入、快捷键、组合键）
- 实现窗口管理技能（切换、最小化、最大化、关闭）
- 实现应用操作技能（启动、查找、操作）

### 3. 记忆-技能联动系统

- 新增 `server/skills/memory_aware_skill.py` 记忆感知技能基类
- 实现技能执行时的记忆上下文注入
- 实现操作结果自动记忆存储
- 实现用户偏好学习与技能参数优化
- 实现操作历史追溯与回放

### 4. MCP 协议集成

- 新增 `server/mcp/` 模块
- 实现 MCP 客户端连接外部工具服务器
- 实现 MCP 工具动态发现与注册
- 实现 MCP 工具调用路由
- 支持将 MCP 服务器转换为 Skills

### 5. 安全沙箱增强

- 增强 `server/sandbox/` 模块
- 实现桌面操作权限控制
- 实现敏感操作确认机制
- 实现操作审计与回滚
- 实现资源限制（操作频率、范围）

### 6. 前端界面扩展

- 新增 CUA 控制面板页面
- 新增操作录制与回放界面
- 新增记忆-技能配置界面
- 新增安全审计仪表板

## Impact

- **Affected specs**: Agent 执行器、Skills 系统、记忆系统、安全模块
- **Affected code**:
  - `server/agent/` - 执行器扩展
  - `server/skills/` - 新增 CUA Skills
  - `server/memory/` - 记忆-技能联动
  - `server/mcp/` - 新增模块
  - `server/sandbox/` - 安全增强
  - `client/src/pages/` - 新增页面
  - `client/src/services/api.ts` - API 扩展

## ADDED Requirements

### Requirement: 屏幕感知能力

系统 SHALL 提供屏幕感知能力，支持：

- 实时屏幕截图捕获
- 多显示器支持
- 指定区域截图
- 截图压缩与传输优化

#### Scenario: 屏幕截图捕获

- **WHEN** Agent 需要了解当前屏幕状态
- **THEN** 系统捕获当前屏幕并返回图像数据

#### Scenario: 多显示器支持

- **WHEN** 系统连接多个显示器
- **THEN** 支持指定显示器截图或全屏截图

### Requirement: 鼠标键盘模拟

系统 SHALL 提供鼠标键盘模拟操作，支持：

- 鼠标移动、点击、双击、右键、拖拽、滚动
- 键盘输入、快捷键、组合键
- 操作延迟与速度控制
- 操作轨迹录制

#### Scenario: 鼠标点击操作

- **WHEN** Agent 需要点击屏幕特定位置
- **THEN** 系统模拟鼠标点击并返回操作结果

#### Scenario: 键盘输入操作

- **WHEN** Agent 需要输入文本
- **THEN** 系统模拟键盘输入并确认输入完成

### Requirement: GUI 元素识别

系统 SHALL 提供 GUI 元素识别能力，支持：

- 基于坐标的元素定位
- 基于文本的元素查找（OCR）
- 基于图像的元素匹配
- 元素属性获取（位置、大小、状态）

#### Scenario: 文本元素查找

- **WHEN** Agent 需要点击包含特定文本的按钮
- **THEN** 系统通过 OCR 定位元素并返回坐标

#### Scenario: 图像元素匹配

- **WHEN** Agent 需要查找特定图标
- **THEN** 系统通过图像匹配定位元素位置

### Requirement: 记忆感知技能

系统 SHALL 提供记忆感知技能执行，支持：

- 技能执行前自动注入相关记忆上下文
- 技能执行后自动存储操作结果到记忆
- 用户偏好学习与技能参数优化
- 操作历史追溯

#### Scenario: 记忆上下文注入

- **WHEN** 执行记忆感知技能
- **THEN** 系统自动检索相关记忆并注入技能上下文

#### Scenario: 操作结果记忆存储

- **WHEN** 技能执行完成
- **THEN** 系统自动将操作结果存储到记忆系统

#### Scenario: 用户偏好学习

- **WHEN** 用户多次执行相似操作
- **THEN** 系统学习用户偏好并优化技能参数

### Requirement: MCP 协议支持

系统 SHALL 支持 Model Context Protocol：

- 连接外部 MCP 服务器
- 动态发现和注册 MCP 工具
- MCP 工具调用路由
- 将 MCP 服务器转换为 Skills

#### Scenario: MCP 工具发现

- **WHEN** 用户配置 MCP 服务器
- **THEN** 系统自动发现并注册可用工具

#### Scenario: MCP 工具调用

- **WHEN** Agent 需要使用 MCP 工具
- **THEN** 通过协议路由调用并返回结果

### Requirement: 桌面操作安全控制

系统 SHALL 提供桌面操作安全控制：

- 操作权限分级（只读、受限、完全）
- 敏感操作确认机制
- 操作审计日志
- 操作回滚支持

#### Scenario: 敏感操作确认

- **WHEN** Agent 尝试执行敏感操作（如删除文件、系统设置）
- **THEN** 系统请求用户确认后执行

#### Scenario: 操作审计

- **WHEN** 执行任何桌面操作
- **THEN** 系统记录详细审计日志

## MODIFIED Requirements

### Requirement: Agent 执行器扩展

原有 Agent 执行器 SHALL 集成 CUA 能力：

- 支持屏幕感知操作
- 支持鼠标键盘模拟
- 支持操作录制与回放
- 审计日志增强

### Requirement: Skills 系统扩展

原有 Skills 系统 SHALL 支持：

- 记忆感知技能基类
- CUA 技能类别
- MCP 工具转换
- 技能学习与优化

### Requirement: 记忆系统扩展

原有记忆系统 SHALL 增加：

- 操作记忆类型
- 技能执行历史存储
- 用户偏好记忆
- 操作模式学习

### Requirement: API 端点扩展

原有 API SHALL 新增端点：

- `POST /cua/screenshot` - 屏幕截图
- `POST /cua/mouse/click` - 鼠标点击
- `POST /cua/mouse/move` - 鼠标移动
- `POST /cua/keyboard/type` - 键盘输入
- `POST /cua/window/list` - 窗口列表
- `POST /cua/record/start` - 开始录制
- `POST /cua/record/stop` - 停止录制
- `POST /cua/record/play` - 回放操作
- `GET /mcp/tools` - 列出 MCP 工具
- `POST /mcp/call` - 调用 MCP 工具

## REMOVED Requirements

无移除的功能，所有改动为增量添加。

## 技术选型

### 屏幕捕获

- **Windows**: `mss` (Multiple Screen Shots) + `PIL`
- **macOS**: `pyobjc` + `Quartz` / `ScreenCaptureKit`
- **跨平台**: `mss` 作为主要方案

### 鼠标键盘模拟

- **PyAutoGUI**: 跨平台鼠标键盘自动化
- **pynput**: 键盘鼠标监听与控制
- **pywinauto** (Windows): Windows GUI 自动化增强

### OCR 与视觉识别

- **Tesseract OCR**: 开源 OCR 引擎
- **EasyOCR**: 深度学习 OCR
- **OpenCV**: 图像处理与模板匹配
- **可选**: Claude/GPT-4V 视觉模型 API

### MCP 协议

- **mcp**: 官方 MCP Python SDK
- **JSON-RPC 2.0**: 协议基础

### 安全沙箱

- **能力权限模型**: 细粒度权限控制
- **操作审计**: 完整操作日志
- **确认机制**: 敏感操作人工确认

## 架构设计

### CUA 模块架构

```
server/cua/
├── __init__.py
├── screen.py          # 屏幕捕获
├── mouse.py           # 鼠标操作
├── keyboard.py        # 键盘操作
├── window.py          # 窗口管理
├── ocr.py             # OCR 识别
├── vision.py          # 视觉识别
├── recorder.py        # 操作录制
├── player.py          # 操作回放
├── safety.py          # 安全控制
└── coordinator.py     # 协调器
```

### 记忆-技能联动架构

```
┌─────────────────────────────────────────────────────────┐
│                    Memory-Aware Skill                    │
├─────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐     │
│  │   Before    │  │   Execute   │  │    After    │     │
│  │   Hook      │──│   Skill     │──│    Hook     │     │
│  └─────────────┘  └─────────────┘  └─────────────┘     │
│         │                                    │          │
│         ▼                                    ▼          │
│  ┌─────────────┐                    ┌─────────────┐     │
│  │   Memory    │                    │   Memory    │     │
│  │   Recall    │                    │    Store    │     │
│  └─────────────┘                    └─────────────┘     │
└─────────────────────────────────────────────────────────┘
```

### 与 OpenClaw 对比

| 特性        | OpenClaw | 当前项目 | 改进后 |
| --------- | -------- | ---- | --- |
| 屏幕感知      | ✅        | ❌    | ✅   |
| 鼠标键盘模拟    | ✅        | ❌    | ✅   |
| 三层记忆      | ✅        | ✅    | ✅   |
| MCP 协议    | ✅        | ❌    | ✅   |
| Skills 系统 | ✅        | ✅    | ✅   |
| 记忆-技能联动   | ✅        | ❌    | ✅   |
| 安全沙箱      | ✅        | 部分   | ✅   |
| 操作录制      | ✅        | ❌    | ✅   |

## 预期成果

**完整的 Computer Use Agent 能力**

# 屏幕感知与理解

# 鼠标键盘自动化

- GUI 元素识别
- **记忆驱动的智能操作**
  - 技能执行时自动获取相关记忆
  - 操作结果自动存储
  - 用户偏好学习与优化
- **可扩展的工具生态**
  - MCP 协议支持外部工具
  - Skills 广场集成
- **安全的操作环境**
  - 细粒度权限控制
  - 敏感操作确认
  - 完整审计日志

