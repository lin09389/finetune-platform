# 高级质感动效系统接入指南 (Motion System Guide)

本动效系统基于 **Framer-Motion** 构建，遵循 **玻璃拟态 (Glassmorphism)** 与 **编辑主义 (Editorial Typography)** 的设计理念。系统兼顾高性能 (60fps) 与低包体积 (额外体积 ≤ 150KB)，并且完全支持操作系统的 `prefers-reduced-motion` 降级策略。

## 1. 快速接入 (Quick Start)

动效核心组件与 Hooks 位于 `client/src/components/motion/` 目录。

### 1.1 交互式按钮 (InteractiveButton)
带有物理按压弹簧和水波纹 (Ripple) 效果。
```tsx
import { InteractiveButton } from '../components/motion';

// 使用默认的主题变体
<InteractiveButton onClick={handleClick}>
  Confirm
</InteractiveButton>

// 使用玻璃态变体
<InteractiveButton variant="glass" ripple={true}>
  Glass Action
</InteractiveButton>
```

### 1.2 悬浮卡片 (GlassHoverCard)
带有高级阴影和轻微上浮效果，适合用于功能入口或内容块。
```tsx
import { GlassHoverCard } from '../components/motion';

<GlassHoverCard tilt3D={true}>
  <h3>Content Title</h3>
  <p>Some description...</p>
</GlassHoverCard>
```

### 1.3 页面切换 (PageTransition)
用于顶级路由切换，包装在你的 Router 页面中：
```tsx
import { PageTransition } from '../components/motion';
import { useLocation } from 'react-router-dom';

function App() {
  const location = useLocation();
  return (
    <PageTransition locationKey={location.pathname}>
      <Routes location={location} key={location.pathname}>
        <Route path="/" element={<Home />} />
      </Routes>
    </PageTransition>
  );
}
```

### 1.4 高性能加载 (SmoothLoader)
基于 SVG `stroke-dasharray` 的 60fps 加载动画。
```tsx
import { SmoothLoader } from '../components/motion';

<SmoothLoader size="md" color="#3b82f6" />
<SmoothLoader fullscreen />
```

## 2. 动效 Hooks 进阶使用

如果基础组件不满足需求，可以使用 Hooks 快速创建自定义动画。

### 2.1 滚动出现 (useScrollReveal)
当元素滚动进入视口时自动触发动画：
```tsx
import { useScrollReveal } from '../components/motion';
import { motion } from 'framer-motion';

function ScrollSection() {
  const { ref, controls } = useScrollReveal({ once: true });
  
  return (
    <motion.div 
      ref={ref}
      animate={controls}
      initial={{ opacity: 0, y: 50 }}
      variants={{ animate: { opacity: 1, y: 0 } }}
    >
      Show me when in view
    </motion.div>
  );
}
```

### 2.2 可访问性配置 (useMotionConfig)
在自定义动画组件中，务必使用此钩子保证 `prefers-reduced-motion` 的正确响应：
```tsx
import { useMotionConfig } from '../components/motion';
import { motion } from 'framer-motion';

function CustomBox() {
  const { getSafeVariants } = useMotionConfig();
  
  return (
    <motion.div
      variants={getSafeVariants(myVariants)}
      initial="initial"
      animate="animate"
    />
  );
}
```

## 3. Storybook 交互文档

动效组件的所有变体均可在 Storybook 中可视化调试。
运行以下命令启动：
```bash
cd client
npm run storybook
```

## 4. 性能回归测试 (Lighthouse CI)

本项目集成了 `@lhci/cli` 进行自动化性能打分，断言标准为所有核心指标 ≥90。
执行测试前确保安装依赖，然后运行：
```bash
cd client
npm run test:perf
```
它将自动构建生产版本、启动本地服务并在无头浏览器中进行性能审查。如果分数低于 90，测试将失败（warn）。
