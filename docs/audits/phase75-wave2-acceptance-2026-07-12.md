# Phase 7.5 Wave 2 跨页视觉与无障碍验收契约

日期：2026-07-12
范围：Wave 2 Track F2（仅测试、场景和验收审计；不修改生产 UI）

## 结论

本契约冻结应用壳和主要页面的共同结果，而不规定 Sidebar、Header、Mobile navigation 或共享状态组件的内部实现。`/agent` 是 Coding 日常主线与 Training 专业线共享的唯一 Workbench；`/training` 仍是保留专业信息密度的 GA 页面。Build、Train、Hybrid 都是 Workbench 内任务模式，不是独立产品导航，也不能被 Experimental 入口取代。

自动化只校验可由代码可靠证明的公共事实：路由标题的单一来源、路由能力 tier，以及 Workbench 的 Build/Train/Hybrid 归属。它不声称通过了截图、对比度、浏览器布局、读屏或焦点循环验收。

## 冻结的导航与守卫边界

| 路由 | 规范名称 | Tier | 产品角色 | 不可回归的边界 |
| --- | --- | --- | --- | --- |
| `/agent` | Agent 工作台 | GA | Coding 日常主线、共享 Workbench | 能从同一任务上下文创建 Build、Train、Hybrid。 |
| `/training` | 模型训练 | GA | Training 专业线 | 保留专业页面；训练任务仍可在 `/agent` 的 Train/Hybrid 中跟踪与恢复。 |
| `/workspace` | 工作空间 | Beta | 支持性入口 | 不替代 Workbench 内“先确认工作区”的前置步骤。 |
| `/gateway` | Gateway | Experimental | 守卫的实验入口 | 仅由 `/api/info.experimental_enabled` 控制；绝不能成为默认 Workbench 模式或 GA 主线。 |

标题必须继续通过 `client/src/routes/meta.ts` 的公开 `getRouteTitle` 取得，capability tier 必须与 `client/src/capability/tiers.ts` 一致。F2 不规定导航项的 DOM 层级、组件名称或 CSS 模块，因此 D2/E2 可以重构实现而不受此测试的内部细节束缚。

## 验收场景矩阵

| 维度 | 场景 | 必须人工确认的结果 |
| --- | --- | --- |
| 桌面 | 1280×720 | 页面标题、主要行动和当前任务继续路径无裁切；辅助区域不抢占 Agent 主任务。 |
| 移动 | 390×844 | 同时至多一个辅助抽屉覆盖主内容；关闭后回到当前任务与下一步。 |
| 键盘 | 导航、主要行动、retry | 可通过键盘到达、具备可读名称、可激活；焦点环不被裁切。 |
| 触控 | 导航、关闭、主要行动、retry | 实际命中目标至少 44×44 CSS px。 |
| 动效 | reduced-motion | 使用已有 motion token；减少动效后仍能看懂加载、错误和状态变化。 |
| 主题 | 浅色与深色 | 复用语义 token，不依赖主题相关白/黑 alpha。 |

| Surface | Loading | Empty | Error / retry |
| --- | --- | --- | --- |
| Agent Workbench | 说明正在恢复 Workbench，不让辅助空状态冒充主任务完成。 | 清楚指向“确认工作区并输入任务”。 | 失败文案与可访问的 retry/恢复行动同时出现，不能仅使用颜色。 |
| Training 专业页 | 保留页面标题和加载上下文。 | 说明下一步专业操作，不抹平模型、数据集、资源前置条件。 | 保留诊断上下文与 retry、恢复或下一步。 |
| GA / Beta 应用壳断线 | 断线状态可读，GA/Beta 分层不丢失。 | 不适用。 | Experimental 不得在离线时被误标为 GA。 |

## 自动化证据与边界

`client/src/testing/phase75CrossPageScenarios.ts` 是实现无关的场景 fixture；`client/src/test/Phase75CrossPageAcceptance.test.tsx` 断言：

- `/agent`、`/training`、`/workspace`、`/gateway` 的名称来自单一的路由标题元数据，并且其 GA/Beta/Experimental tier 与公开 capability metadata 一致；
- Workbench 的 Build、Train、Hybrid 均是 GA 默认工作流，且 `/agent`、`/training` 不受 Experimental route guard 约束；
- 1280×720、390×844、键盘、44px 触控目标及 loading/empty/error/retry 的完整矩阵被冻结；
- 所有布局和状态矩阵条目均标为人工视觉验收，所有不适合由 DOM/代码证明的项目明确为 `deferred`，不会由 fixture 输出“通过”。

这不是像素测试，且不从 JSDOM 推断实际元素尺寸、对比度或焦点循环。现有页面/组件测试可继续验证各自语义 DOM；F2 的责任是防止跨页验收范围被静默遗漏。

## 主线程必做的实测 gate

在 D2/E2 合并后的集成应用中，主线程必须逐项完成并保存证据：

1. 在浅色与深色主题下，按 1280×720 和 390×844 截图对照同一任务、Training、空状态和断线状态；检查纸张/编辑器风格、terra-cotta 语义 token、字体、圆角和间距没有漂移。
2. 在浏览器 200% 缩放时检查标题、主操作、抽屉关闭按钮、底部导航和 retry 无裁切或遮挡。
3. 使用真实键盘验证 skip link、路由切换后的主内容焦点、打开/关闭抽屉、主要操作及错误 recovery；人工确认抽屉焦点循环和关闭后的返回焦点。
4. 用真实读屏器检查 loading、error/retry、连接状态和训练进度的名称、顺序与播报；`aria-*` 存在不等于播报正确。
5. 在 390×844 设备仿真或实机测量导航、关闭、主要行动和 retry 的可点击区域均至少 44×44 CSS px。
6. 打开 reduced-motion 后检查状态仍可辨识，没有依赖位移/淡入来传达唯一信息。

## 当前状态与风险

状态：**契约已建立；视觉与辅助技术验收待主线程集成实测。**

- 本轨道没有生成或检查截图，因而不会把“测试绿”表述为视觉验收绿。
- 根目录 `AGENTS.md` 在本新 worktree 中不存在；执行时遵守委派请求内提供的“学生、独立开发者”指令。若仓库另有正式根级文件，主线程应在合并前补充审阅。
- D2/E2 若改变公开路由名称、tier 或把 Train/Hybrid 拆出 Workbench，F2 测试会失败；若只调整内部组件结构，F2 不应阻碍重构。
