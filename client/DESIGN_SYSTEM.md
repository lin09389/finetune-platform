# Finetune Platform 设计系统 (Design System 2.0)

> **权威令牌源**：`client/src/styles/variables.css` 是唯一设计令牌事实源。本文档仅描述设计意图与用法指引，若具体数值与 `variables.css` 冲突，以 `variables.css` 为准。
> **运行时样式入口**：`client/src/styles/index.css`（非已删除的 `client/src/index.css`）。

## 1. 核心视觉哲学 (Core Visual Philosophy)

### 1.1 玻璃拟态 (Glassmorphism)
我们的玻璃拟态不仅是模糊背景，还包含多层光感：
- **背景层**: `var(--glass-bg)`，半透明且具有高饱和度饱和。
- **模糊层**: `var(--glass-blur)`，通常为 16px-24px。
- **质感层**: 通过 `::after` 伪元素引入的微颗粒噪声 (`Micro-texture noise`)。
- **边框层**: `1px solid var(--glass-border)`，提供明确的物理边界。

### 1.2 编辑主义 (Editorial Typography)
强调文字的层级与易读性：
- **流体字体**: 字号随屏幕宽度自动缩放。
- **间距系统**: 严格执行 8pt 基准网格。
- **色彩**: 亮色模式下使用“纸白”与“炭黑”的高对比度，深色模式下使用“深空”与“冰白”的柔和对比。

## 2. 动效规范 (Animation Tokens)

| 令牌名称 | 持续时间 | 缓动函数 | 应用场景 |
| :--- | :--- | :--- | :--- |
| `instant` | 100ms | `linear` | 极速反馈 (如点击) |
| `fast` | 150ms | `easeInOut` | 小组件位移、淡入 |
| `base` | 200ms | `var(--ease-smooth)` | 标准悬浮、展开 |
| `smooth` | 300ms | `var(--ease-smooth)` | 侧边栏折叠、大面积变化 |
| `slow` | 500ms | `var(--ease-smooth)` | 页面进出场、复杂的交错动画 |

### 性能优化
- 所有的 `transition` 必须优先应用在 `transform`, `opacity`, `filter` 属性上。
- 对关键动画元素使用 `.will-animate` (对应 `will-change`)。
- 强制使用 `.gpu-accelerated` (对应 `transform-gpu`) 以开启硬件加速。

## 3. 迁移指南 (Migration Guide)

### 3.1 引入 Tailwind
项目中已集成 Tailwind CSS，您可以直接使用原子类：
```tsx
// 推荐做法
<div className="bg-bg-secondary p-4 rounded-xl border border-glass-border shadow-sm hover-lift">
  内容
</div>
```

### 3.2 使用新组件
- **卡片**: 优先使用 `GlassCard` 替代原生的 `AntD Card` 或普通的 `div`。
- **按钮**: 优先使用 `NeumorphicButton` 以获得一致的物理按压反馈。
- **输入框**: 使用 `PremiumInput` 以获得更好的焦点交互。

### 3.3 动效降级
系统自动处理了 `prefers-reduced-motion`，如果用户在 OS 层面启用了该设置，所有动画将自动简化。

## 4. 性能审计指标 (Audit Reports)

- **FCP (First Contentful Paint)**: 目标 1.5s - 1.8s。
- **CLS (Cumulative Layout Shift)**: 目标 < 0.1。
- **60fps**: 在所有主流桌面浏览器（Chrome, Safari, Edge）中实测交互动效稳定在 60fps。
- **WCAG**: 关键文本对比度符合 AA 级标准（4.5:1）。

### 4.1 跨浏览器兼容承诺

- `backdrop-filter` 玻璃拟态效果在 Firefox（需 `layout.css.backdrop-filter.enabled`）或 Safari <16 不支持时，自动降级为纯色背景 + `border-radius`。`variables.css` 中 `--glass-blur` 在浅色主题已设为 `none`，深色主题保留 blur 但配套 `--glass-bg` 纯色 fallback。
- `:has()` 选择器需 Safari 15.4+，使用时必须提供非 `:has()` 的 fallback 规则。
- 终端（xterm.js）与 Monaco Editor 在移动浏览器上触控体验受限，桌面端为首要支持目标。
- **CI TODO（P2-7）**：当前 CI 仅运行 vitest 单元测试 + 生产构建，尚未接入 Playwright 跨浏览器 smoke。计划后续引入 Firefox smoke 测试覆盖核心页面渲染与 `backdrop-filter` fallback。
