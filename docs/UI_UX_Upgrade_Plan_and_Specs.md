# Finetune Platform 2.0 - UI/UX 视觉与交互升级规范

## 1. 核心设计愿景 (Design Vision)
为了将系统从“内部工具感”升级为**“企业级现代化智能平台”**，本次设计升级遵循三大原则：
1. **Tech-Premium (现代科技质感)**：摒弃老旧的高饱和蓝白配，借鉴 Vercel, Linear 等顶尖开发者工具的设计语言。采用更极致的“纯黑 (OLED Black) / 极简白 (Clean White)”为主背景，辅以低对比度的柔和边框，并通过极高亮度的品牌色（Indigo / 荧光靛）点亮关键操作。
2. **Focus-First (去线框化与空间感)**：减少实线边框的使用，引入大量的留白 (Negative Space)。利用多层级平滑阴影 (Multi-layered Shadows) 与环境毛玻璃 (Glassmorphism) 来区分页面层级（如背景层 -> 卡片层 -> 弹出层）。
3. **Fluid-Motion (流体与弹簧动效)**：拒绝僵硬的线性动画。在按钮点击、卡片悬浮、状态流转时，全面引入基于物理反馈的弹簧动画 (Spring Animations)，使系统仿佛具有生命力和物理触感。

---

## 2. 设计系统规范 (Design System Specs)

### 2.1 色彩方案 (Color Palette)
色彩重构的重点在于降低背景干扰，提高内容对比度。
* **Light Theme (浅色模式)**
  * `bg-primary`: `#FAFAFA` (极浅灰，作为页面底色)
  * `bg-secondary`: `#FFFFFF` (纯白，作为主要卡片背景)
  * `border-color`: `#E5E7EB` (更柔和的边框)
  * `accent-primary`: `#4F46E5` (Indigo-600，深邃且有活力的品牌主色)
* **Dark Theme (深色模式)**
  * `bg-primary`: `#000000` (全黑背景，提供无边界的沉浸感)
  * `bg-secondary`: `#0A0A0A` (微亮卡片层)
  * `border-color`: `#262626` (仅比背景亮一点点的隐形边框)
  * `accent-primary`: `#6366F1` (Indigo-500，在深色背景下具有霓虹发光感)

### 2.2 字体排版 (Typography)
* **Font-Family**: 引入新一代无衬线字体栈。优先加载 `'Geist', 'Outfit', 'Inter'`，确保数字、字母的几何线条更具备未来感。代码等宽字体升级为 `'Geist Mono', 'JetBrains Mono'`。
* **Border-Radius**: 将圆角体系整体放大，带来更友好、现代的包裹感。`--radius-md: 8px`, `--radius-lg: 16px`, `--radius-xl: 24px`。

### 2.3 阴影与深度 (Shadows & Elevation)
摒弃传统的单层黑影，转而采用叠加的多层阴影，使元素看起来悬浮在半空：
* `shadow-sm`: `0 1px 2px rgba(0,0,0, 0.02), 0 1px 1px rgba(0,0,0, 0.01)`
* `shadow-lg`: `0 10px 15px -3px rgba(0,0,0, 0.04), 0 4px 6px -4px rgba(0,0,0, 0.02)`

---

## 3. 分阶段实施计划 (Phased Rollout Plan)

为了保证平台的现有业务逻辑不受破坏（零侵入功能改造），视觉升级将分四个阶段进行：

### 🏁 Phase 1: 基础设施与全局令牌替换 (Foundation) —— 【本轮已启动并实施】
**目标**：全局焕新，改动成本最低但收益最大。
**执行内容**：
- 在 `client/src/index.css` 中重写全局 CSS Variables，包含上述的色彩体系、字体栈、多层阴影、圆角加大。
- 为 `<Button>`, `<Card>`, `Table row` 等常见全局组件统一添加弹簧缩放 (`transform: scale()`) 与悬停上移的微交互动画。
- **兼容性保障**：只修改原生 CSS Token 映射，完全不触碰 React 组件内部的 Ant Design 组件结构，确保功能 100% 稳定运行。

### 🚧 Phase 2: 核心容器与布局结构改造 (Layout & Containers)
**目标**：优化空间布局，消除拥挤感。
**执行内容**：
- 重新设计 `AnimatedLayout`，为主内容区增加最大宽度限制，使其在超宽带鱼屏下不显得松散。
- 将左侧 `Sidebar` 重构为悬浮式或带深度高斯模糊的岛屿式边栏 (Island Sidebar)。
- 对所有的 `GlassCard` 去除实线边框，仅依赖阴影和透明度渲染轮廓。

### 🔮 Phase 3: 表单与交互组件原子级打磨 (Atomic Components Polish)
**目标**：提升用户的录入快感与操作容错感。
**执行内容**：
- 放大表单控件的尺寸 (Input, Select 默认高度增至 `40px`)，文本内边距加大。
- 自定义 Ant Design 的 Focus 环：改为从元素边缘向外扩散的带透明度品牌色光晕。
- 替换现有粗放的 `<Alert>` 样式为更克制、带有小面积左侧色带的高级提示框。

### 🚀 Phase 4: 业务链路特调微交互 (Delightful Micro-interactions)
**目标**：提升页面的生命力与高端感知。
**执行内容**：
- 在 Inference 推理页：对话生成时加入类似 ChatGPT 的呼吸发光焦点效果。
- 在 Training 训练页：队列状态增加脉冲波纹 (`pulse-ring`)；Loss 曲线图表的初始加载增加平滑的遮罩拉开动画。
- 加入页面之间的路由级过场动画 (`Framer Motion` 出入场增强)。

---

## 4. 后续协作建议
我们已通过全局样式覆写完成了 Phase 1。开发团队可直接检出代码预览全局的“暗黑高级感”与“弹簧微交互”。在下一次迭代中，建议选择 `Inference.tsx` (推理对话) 或 `Sidebar.tsx` 页面开启 Phase 2 的深度布局重构。