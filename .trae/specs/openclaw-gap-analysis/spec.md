# OpenClaw 桌面操作能力差距分析与改进升级方案 Spec

## Why

当前 finetune-platform 项目已具备基础的 Agent 执行、Skills 系统、三级记忆架构等功能，但与 OpenClaw 等领先的 Computer Use Agent 项目相比，存在显著差距。用户希望通过 skills 功能读取系统记忆、学习并自如操作电脑，这需要全面分析差距并制定改进方案。

### 当前项目已有能力

| 模块 | 现状 | 完成度 |
|------|------|--------|
| Skills 系统 | 基础框架完整，有 SkillBase、Registry、参数验证 | 70% |
| 记忆系统 | MemoryService 支持向量存储，三级记忆架构 | 60% |
| Agent 执行器 | 文件操作、应用操作、URL 操作 | 40% |
| 系统技能 | SystemInfo、CommandExecute、TimeNow、Delay、Calculator | 30% |
| 安全模块 | SecurityValidator、路径验证 | 50% |

### 核心差距

1. **缺失屏幕感知能力** - 无法"看见"屏幕，无法进行视觉理解
2. **缺失桌面操作能力** - 无法模拟鼠标点击、键盘输入、GUI 自动化
3. **Skills 系统与记忆系统未打通** - 技能无法读取系统记忆、无法学习用户偏好
4. **缺乏 MCP 协议支持** - 无法连接外部工具服务器扩展能力
5. **安全边界不完善** - 缺乏沙箱执行和细粒度权限控制
6. **缺乏操作录制与回放** - 无法记录和复现用户操作

## What Changes

### 1. OpenClaw 核心能力移植

- 新增屏幕感知模块（截图、OCR、视觉识别）
- 新增鼠标键盘模拟模块（PyAutoGUI 集成）
- 新增窗口管理模块
- 新增操作录制与回放模块

### 2. 记忆-技能联动系统

- 新增记忆感知技能基类
- 实现技能执行时的记忆上下文注入
- 实现操作结果自动记忆存储
- 实现用户偏好学习与技能参数优化

### 3. MCP 协议集成

- 新增 MCP 客户端模块
- 实现工具动态发现与注册
- 实现 MCP 工具转换为 Skills

### 4. 安全沙箱增强

- 实现桌面操作权限控制
- 实现敏感操作确认机制
- 实现操作审计与回滚

### 5. 前端界面扩展

- 新增 CUA 控制面板页面
- 新增操作录制与回放界面
- 新增记忆-技能配置界面

## Impact

- **Affected specs**: Agent 执行器、Skills 系统、记忆系统、安全模块
- **Affected code**:
  - `server/agent/` - 执行器扩展
  - `server/skills/` - 新增 CUA Skills 和记忆感知技能
  - `server/memory/` - 记忆-技能联动
  - `server/mcp/` - 新增模块
  - `server/cua/` - 新增模块
  - `client/src/pages/` - 新增页面
  - `client/src/services/api.ts` - API 扩展

## ADDED Requirements

### Requirement: OpenClaw 能力差距分析报告

系统 SHALL 提供完整的 OpenClaw 能力差距分析报告，包括：

- OpenClaw 项目架构分析
- 核心功能模块对比
- 技术实现差异
- 可借鉴的设计模式

#### Scenario: 差距分析完成

- **WHEN** 用户请求分析 OpenClaw 差距
- **THEN** 系统生成详细的差距分析报告

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

### OpenClaw vs 当前项目对比

| 特性 | OpenClaw | 当前项目 | 改进后 |
|------|----------|----------|--------|
| 屏幕感知 | ✅ | ❌ | ✅ |
| 鼠标键盘模拟 | ✅ | ❌ | ✅ |
| 三层记忆 | ✅ | ✅ | ✅ |
| MCP 协议 | ✅ | ❌ | ✅ |
| Skills 系统 | ✅ (50+) | ✅ (5+) | ✅ |
| 记忆-技能联动 | ✅ | ❌ | ✅ |
| 安全沙箱 | ✅ | 部分 | ✅ |
| 操作录制 | ✅ | ❌ | ✅ |
| 多渠道支持 | ✅ | ❌ | 可选 |
| 插件系统 | ✅ | 基础 | ✅ |

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

## 实施阶段

### 阶段一：差距分析与架构设计（1 周）

- OpenClaw 项目深度分析
- 技术选型确认
- 架构设计文档
- 接口定义

### 阶段二：CUA 核心模块（2 周）

- 屏幕捕获模块
- 鼠标键盘模拟模块
- 窗口管理模块
- 安全控制模块

### 阶段三：OCR 与视觉识别（1 周）

- OCR 识别模块
- 视觉识别模块
- 元素定位功能

### 阶段四：记忆-技能联动（1 周）

- 记忆感知技能基类
- 操作记忆管理
- 技能学习与优化

### 阶段五：MCP 协议集成（1 周）

- MCP 客户端
- 工具注册与发现
- API 端点

### 阶段六：前端界面（1 周）

- CUA 控制面板
- 操作录制界面
- 记忆-技能配置界面

### 阶段七：测试与文档（1 周）

- 单元测试
- 集成测试
- 文档编写

## 预期成果

### 完整的 Computer Use Agent 能力

- 屏幕感知与理解
- 鼠标键盘自动化
- GUI 元素识别

### 记忆驱动的智能操作

- 技能执行时自动获取相关记忆
- 操作结果自动存储
- 用户偏好学习与优化

### 可扩展的工具生态

- MCP 协议支持外部工具
- Skills 广场集成

### 安全的操作环境

- 细粒度权限控制
- 敏感操作确认
- 完整审计日志

## 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 依赖冲突 | 高 | 使用虚拟环境，版本锁定 |
| 性能影响 | 中 | 异步执行，资源限制 |
| 安全风险 | 高 | 沙箱隔离，权限控制 |
| 兼容性 | 中 | 平台适配层，降级方案 |
