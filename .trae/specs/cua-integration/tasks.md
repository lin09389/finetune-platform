# Tasks

## Phase 1: CUA 核心模块实现

- [ ] Task 1: 创建 CUA 模块基础结构
  - [ ] SubTask 1.1: 创建 `server/cua/__init__.py` 模块入口
  - [ ] SubTask 1.2: 创建 `server/cua/models.py` 数据模型定义
  - [ ] SubTask 1.3: 创建 `server/cua/config.py` 配置管理
  - [ ] SubTask 1.4: 创建 `server/cua/exceptions.py` 异常定义

- [ ] Task 2: 实现屏幕捕获模块
  - [ ] SubTask 2.1: 创建 `server/cua/screen.py` 屏幕捕获器
  - [ ] SubTask 2.2: 实现 Windows 平台屏幕捕获（mss + PIL）
  - [ ] SubTask 2.3: 实现多显示器支持
  - [ ] SubTask 2.4: 实现指定区域截图
  - [ ] SubTask 2.5: 实现截图压缩与编码优化

- [ ] Task 3: 实现鼠标操作模块
  - [ ] SubTask 3.1: 创建 `server/cua/mouse.py` 鼠标控制器
  - [ ] SubTask 3.2: 实现鼠标移动（绝对坐标、相对移动）
  - [ ] SubTask 3.3: 实现鼠标点击（左键、右键、双击）
  - [ ] SubTask 3.4: 实现鼠标拖拽操作
  - [ ] SubTask 3.5: 实现鼠标滚动操作
  - [ ] SubTask 3.6: 实现操作延迟与速度控制

- [ ] Task 4: 实现键盘操作模块
  - [ ] SubTask 4.1: 创建 `server/cua/keyboard.py` 键盘控制器
  - [ ] SubTask 4.2: 实现文本输入（支持中文）
  - [ ] SubTask 4.3: 实现按键操作（单键、组合键）
  - [ ] SubTask 4.4: 实现快捷键模拟
  - [ ] SubTask 4.5: 实现输入速度控制

- [ ] Task 5: 实现窗口管理模块
  - [ ] SubTask 5.1: 创建 `server/cua/window.py` 窗口管理器
  - [ ] SubTask 5.2: 实现窗口列表获取
  - [ ] SubTask 5.3: 实现窗口切换
  - [ ] SubTask 5.4: 实现窗口状态操作（最小化、最大化、关闭）
  - [ ] SubTask 5.5: 实现窗口位置和大小调整

## Phase 2: OCR 与视觉识别

- [ ] Task 6: 实现 OCR 识别模块
  - [ ] SubTask 6.1: 创建 `server/cua/ocr.py` OCR 识别器
  - [ ] SubTask 6.2: 集成 Tesseract OCR
  - [ ] SubTask 6.3: 集成 EasyOCR（可选）
  - [ ] SubTask 6.4: 实现文本定位功能
  - [ ] SubTask 6.5: 实现中英文混合识别优化

- [ ] Task 7: 实现视觉识别模块
  - [ ] SubTask 7.1: 创建 `server/cua/vision.py` 视觉识别器
  - [ ] SubTask 7.2: 实现图像模板匹配（OpenCV）
  - [ ] SubTask 7.3: 实现图标识别
  - [ ] SubTask 7.4: 实现按钮检测
  - [ ] SubTask 7.5: 实现视觉模型 API 集成（可选）

## Phase 3: 操作录制与回放

- [ ] Task 8: 实现操作录制模块
  - [ ] SubTask 8.1: 创建 `server/cua/recorder.py` 操作录制器
  - [ ] SubTask 8.2: 实现鼠标事件监听
  - [ ] SubTask 8.3: 实现键盘事件监听
  - [ ] SubTask 8.4: 实现操作序列存储
  - [ ] SubTask 8.5: 实现录制控制（开始、暂停、停止）

- [ ] Task 9: 实现操作回放模块
  - [ ] SubTask 9.1: 创建 `server/cua/player.py` 操作回放器
  - [ ] SubTask 9.2: 实现操作序列解析
  - [ ] SubTask 9.3: 实现时间精确回放
  - [ ] SubTask 9.4: 实现回放速度控制
  - [ ] SubTask 9.5: 实现回放中断与恢复

## Phase 4: 安全控制模块

- [ ] Task 10: 实现安全控制模块
  - [ ] SubTask 10.1: 创建 `server/cua/safety.py` 安全控制器
  - [ ] SubTask 10.2: 实现操作权限分级（只读、受限、完全）
  - [ ] SubTask 10.3: 实现敏感操作检测
  - [ ] SubTask 10.4: 实现操作确认机制
  - [ ] SubTask 10.5: 实现操作审计日志
  - [ ] SubTask 10.6: 实现操作频率限制

## Phase 5: CUA Skills 实现

- [ ] Task 11: 创建 CUA Skills 基础
  - [ ] SubTask 11.1: 创建 `server/skills/implemented/cua_skills.py`
  - [ ] SubTask 11.2: 实现 `ScreenshotSkill` 屏幕截图技能
  - [ ] SubTask 11.3: 实现 `MouseClickSkill` 鼠标点击技能
  - [ ] SubTask 11.4: 实现 `MouseMoveSkill` 鼠标移动技能
  - [ ] SubTask 11.5: 实现 `KeyboardTypeSkill` 键盘输入技能
  - [ ] SubTask 11.6: 实现 `WindowListSkill` 窗口列表技能
  - [ ] SubTask 11.7: 实现 `AppLaunchSkill` 应用启动技能
  - [ ] SubTask 11.8: 实现 `FindTextSkill` 文本查找技能

- [ ] Task 12: 实现复合操作技能
  - [ ] SubTask 12.1: 实现 `ClickTextSkill` 点击文本技能
  - [ ] SubTask 12.2: 实现 `TypeInFieldSkill` 输入框输入技能
  - [ ] SubTask 12.3: 实现 `DragDropSkill` 拖拽技能
  - [ ] SubTask 12.4: 实现 `RecordActionsSkill` 录制操作技能
  - [ ] SubTask 12.5: 实现 `PlaybackActionsSkill` 回放操作技能

## Phase 6: 记忆-技能联动系统

- [ ] Task 13: 创建记忆感知技能基类
  - [ ] SubTask 13.1: 创建 `server/skills/memory_aware_skill.py`
  - [ ] SubTask 13.2: 实现记忆上下文注入钩子
  - [ ] SubTask 13.3: 实现操作结果存储钩子
  - [ ] SubTask 13.4: 实现记忆检索辅助方法

- [ ] Task 14: 实现操作记忆管理
  - [ ] SubTask 14.1: 扩展 `server/memory/models.py` 添加操作记忆类型
  - [ ] SubTask 14.2: 实现操作历史存储
  - [ ] SubTask 14.3: 实现用户偏好记忆
  - [ ] SubTask 14.4: 实现操作模式学习

- [ ] Task 15: 实现技能学习与优化
  - [ ] SubTask 15.1: 创建 `server/skills/learner.py` 技能学习器
  - [ ] SubTask 15.2: 实现用户偏好学习
  - [ ] SubTask 15.3: 实现技能参数优化
  - [ ] SubTask 15.4: 实现操作建议生成

## Phase 7: MCP 协议集成

- [ ] Task 16: 创建 MCP 核心模块
  - [ ] SubTask 16.1: 创建 `server/mcp/__init__.py` 模块入口
  - [ ] SubTask 16.2: 创建 `server/mcp/protocol.py` 协议定义
  - [ ] SubTask 16.3: 创建 `server/mcp/client.py` MCP 客户端
  - [ ] SubTask 16.4: 创建 `server/mcp/server_manager.py` 服务器管理器

- [ ] Task 17: 实现工具注册与发现
  - [ ] SubTask 17.1: 创建 `server/mcp/tool_registry.py` 工具注册表
  - [ ] SubTask 17.2: 实现动态工具发现
  - [ ] SubTask 17.3: 实现 MCP 工具到 Skill 转换
  - [ ] SubTask 17.4: 实现工具调用路由

- [ ] Task 18: 创建 MCP API 端点
  - [ ] SubTask 18.1: 创建 `server/api/mcp.py` API 路由
  - [ ] SubTask 18.2: 实现 `GET /mcp/tools` 列出工具
  - [ ] SubTask 18.3: 实现 `POST /mcp/call` 调用工具
  - [ ] SubTask 18.4: 实现 `POST /mcp/servers` 管理服务器

## Phase 8: CUA API 端点

- [ ] Task 19: 创建 CUA API 端点
  - [ ] SubTask 19.1: 创建 `server/api/cua.py` API 路由
  - [ ] SubTask 19.2: 实现屏幕截图端点 `POST /cua/screenshot`
  - [ ] SubTask 19.3: 实现鼠标操作端点
  - [ ] SubTask 19.4: 实现键盘操作端点
  - [ ] SubTask 19.5: 实现窗口管理端点
  - [ ] SubTask 19.6: 实现录制回放端点
  - [ ] SubTask 19.7: 实现安全控制端点

## Phase 9: 前端界面扩展

- [ ] Task 20: 创建 CUA 控制面板
  - [ ] SubTask 20.1: 创建 `client/src/pages/CUAControl.tsx` 页面组件
  - [ ] SubTask 20.2: 实现实时屏幕预览组件
  - [ ] SubTask 20.3: 实现鼠标键盘控制面板
  - [ ] SubTask 20.4: 实现操作日志显示

- [ ] Task 21: 创建操作录制界面
  - [ ] SubTask 21.1: 创建 `client/src/pages/ActionRecorder.tsx` 页面组件
  - [ ] SubTask 21.2: 实现录制控制按钮
  - [ ] SubTask 21.3: 实现操作列表展示
  - [ ] SubTask 21.4: 实现回放控制

- [ ] Task 22: 创建记忆-技能配置界面
  - [ ] SubTask 22.1: 创建 `client/src/pages/SkillMemory.tsx` 页面组件
  - [ ] SubTask 22.2: 实现技能记忆关联配置
  - [ ] SubTask 22.3: 实现用户偏好设置
  - [ ] SubTask 22.4: 实现操作历史查看

- [ ] Task 23: 更新导航和 API 服务
  - [ ] SubTask 23.1: 更新 `client/src/components/Sidebar.tsx` 添加新菜单
  - [ ] SubTask 23.2: 更新 `client/src/services/api.ts` 添加新 API 方法
  - [ ] SubTask 23.3: 更新 `client/src/types/index.ts` 添加类型定义

## Phase 10: 测试与文档

- [ ] Task 24: 编写后端测试
  - [ ] SubTask 24.1: 编写 `server/tests/test_cua_screen.py` 屏幕捕获测试
  - [ ] SubTask 24.2: 编写 `server/tests/test_cua_mouse.py` 鼠标操作测试
  - [ ] SubTask 24.3: 编写 `server/tests/test_cua_keyboard.py` 键盘操作测试
  - [ ] SubTask 24.4: 编写 `server/tests/test_cua_skills.py` CUA 技能测试
  - [ ] SubTask 24.5: 编写 `server/tests/test_mcp.py` MCP 测试
  - [ ] SubTask 24.6: 编写 `server/tests/test_memory_skill.py` 记忆-技能联动测试

- [ ] Task 25: 编写前端测试
  - [ ] SubTask 25.1: 编写 CUA 控制面板测试
  - [ ] SubTask 25.2: 编写操作录制界面测试
  - [ ] SubTask 25.3: 编写记忆-技能配置界面测试

# Task Dependencies

- [Task 2] depends on [Task 1]
- [Task 3] depends on [Task 1]
- [Task 4] depends on [Task 1]
- [Task 5] depends on [Task 1]
- [Task 6] depends on [Task 2]
- [Task 7] depends on [Task 2]
- [Task 8] depends on [Task 3, Task 4]
- [Task 9] depends on [Task 8]
- [Task 10] depends on [Task 1]
- [Task 11] depends on [Task 2, Task 3, Task 4, Task 5, Task 6]
- [Task 12] depends on [Task 11]
- [Task 13] depends on [Task 11]
- [Task 14] depends on [Task 13]
- [Task 15] depends on [Task 14]
- [Task 17] depends on [Task 16]
- [Task 18] depends on [Task 16, Task 17]
- [Task 19] depends on [Task 2, Task 3, Task 4, Task 5, Task 8, Task 9, Task 10]
- [Task 20] depends on [Task 19]
- [Task 21] depends on [Task 19]
- [Task 22] depends on [Task 13, Task 14]
- [Task 23] depends on [Task 20, Task 21, Task 22]
- [Task 24] depends on [Task 1-18]
- [Task 25] depends on [Task 20-23]

# Parallelizable Work

以下任务可以并行执行：
- Phase 1 中的 Task 2-5 可以并行开发
- Phase 2 中的 Task 6-7 可以并行开发
- Phase 3 中的 Task 8-9 可以并行开发（录制和回放独立）
- Phase 5 和 Phase 6 可以部分并行
- Phase 7 可以与其他 Phase 并行
- Phase 9 中的 Task 20-22 可以并行开发
