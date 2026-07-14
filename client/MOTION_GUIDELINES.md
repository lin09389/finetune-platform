# Finetune Platform 高级质感动效规范 (Motion Guidelines)

> **权威令牌源**：动效令牌以 `client/src/styles/variables.css`（`--duration-*` / `--ease-*`）为准，本文档仅描述设计意图。
> **reduce-motion 实现**：集中封装在 `client/src/hooks/useMotion.ts`（`useMotion`）与 `client/src/components/motion/useMotionConfig.ts`（`useMotionConfig`）。所有 Framer Motion 使用应优先通过这两个 hook，而非直接 import `motion`。

## 1. 核心设计原则 (Core Principles)

### 1.1 目的性动效 (Purposeful Motion)
- **反馈 (Feedback)**: 明确响应用户的每一个微小操作（悬浮、点击、拖拽）。
- **引导 (Orientation)**: 在页面切换和组件展开时，展示元素的来源与去向。
- **聚焦 (Focus)**: 通过动效将用户的注意力引导至最重要的状态变化上。

### 1.2 玻璃拟态结合 (Glassmorphism Integration)
- 动效不应破坏背景的模糊 (`backdrop-filter`) 与颗粒感层 (`noise`)。
- 卡片悬浮时，应优先通过光影、边框高亮和阴影深度的变化来表现，而非生硬的放大。

## 2. 动效令牌字典 (Motion Tokens)

### 2.1 持续时长 (Durations)
| Token | 时长 | 场景 |
| --- | --- | --- |
| `instant` | 100ms | 极速反馈（如点击缩放） |
| `fast` | 150ms | 状态切换（如 Checkbox、Hover 变色） |
| `base` | 200ms | 标准小组件位移、淡入 |
| `smooth` | 300ms | 侧边栏折叠、模态框弹出 |
| `slow` | 500ms | 页面进出场、复杂的交错动画 |

### 2.2 缓动曲线 (Easings)
- **Smooth (`cubic-bezier(0.16, 1, 0.3, 1)`)**: 用于大部分位移与淡入，强调进入时的减速，呈现高级感。
- **Spring (物理弹簧)**: 用于按钮按压、卡片悬浮。
  - `Gentle`: 阻尼大，不回弹，用于卡片 hover。
  - `Bouncy`: 阻尼小，带轻微回弹，用于重要按钮交互。

## 3. 关键场景动效清单 (Motion Inventory)

### 3.1 首屏与页面切换 (Page Transitions)
- **触发时机**: 路由变化时。
- **动效**: `AnimatePresence` 结合 `opacity` (0->1) 与 `y` (-10px->0)，使用 `smooth` (300ms) 曲线。

### 3.2 导航与菜单 (Navigation)
- **触发时机**: 展开折叠或 Hover。
- **动效**: 下拉菜单使用纵向缩放 (`scaleY`) 结合淡入，锚点设为 `top`，时长 `fast` (150ms)。

### 3.3 卡片交互 (Cards)
- **触发时机**: 鼠标悬浮。
- **动效**: 玻璃态卡片采用 3D 轻微倾斜或 `y` 轴上浮 (-2px)，结合阴影扩张 (`box-shadow`)，时长 `base` (200ms)。

### 3.4 按钮交互 (Buttons)
- **触发时机**: Hover 与 Tap。
- **动效**: Hover 放大 (`scale: 1.02`)，Tap 缩小 (`scale: 0.96`)。采用 `Spring` 曲线 (`stiffness: 400, damping: 17`)。

### 3.5 加载与骨架屏 (Loading)
- **触发时机**: 数据请求中。
- **动效**: 骨架屏使用 `shimmer` 闪烁 (1.5s 周期)；局部加载使用 SVG `stroke-dasharray` 动画，保障 60fps。

## 4. 可访问性与降级 (Accessibility & Reduced Motion)
- **媒体查询支持**: 必须监听 `prefers-reduced-motion: reduce`。
- **降级策略**: 当用户开启“减弱动态效果”时，将所有 duration 置为 `0` 或 `0.01ms`，仅保留硬切的淡入淡出，取消所有位移与缩放动效。
