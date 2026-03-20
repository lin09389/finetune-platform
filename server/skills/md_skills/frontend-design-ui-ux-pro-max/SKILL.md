---
name: "frontend-design-ui-ux-pro-max"
description: "Crafts premium, distinctive frontend interfaces with non-AI-homogenized aesthetics. Invoke when designing UIs that need unique visual identity, sophisticated details, and human-crafted design sensibility beyond generic AI gradients and minimalism."
---

# Frontend Design & UI-UX-PRO-MAX

## 核心设计理念

### ❌ 拒绝 AI 同质化设计
- **不用** 蓝紫渐变 (AI Blue-Purple Gradient)
- **不用** 玻璃拟态 (Glassmorphism) 泛滥使用
- **不用** 千篇一律的圆角卡片
- **不用** 过度简化的"性冷淡"极简主义
- **不用** 无意义的微交互动画堆砌

### ✅ 独特的审美方向

#### 1. 色彩哲学
```
🎨 推荐配色方案：

【复古数字风】
- 主色: #1a1a2e (深海军蓝)
- 辅色: #16213e (墨蓝)
- 强调: #e94560 (珊瑚红)
- 文字: #eaeaea (暖白)
- 点缀: #0f3460 (靛青)

【编辑主义】
- 背景: #faf9f7 (纸白)
- 主色: #2d2d2d (炭黑)
- 强调: #d4a373 (铜金)
- 辅助: #6b7280 (石墨灰)
- 边框: #e5e5e5 (淡银)

【赛博工匠】
- 暗部: #0d1117 (深空黑)
- 亮部: #f0f6fc (冰白)
- 强调: #ff6b35 (熔岩橙)
- 辅助: #58a6ff (电光蓝)
- 成功: #3fb950 (霓虹绿)

【东方雅致】
- 底色: #f7f5f0 (宣纸白)
- 墨: #2c2c2c (松烟墨)
- 朱: #c45c48 (朱砂)
- 青: #5b8a72 (石青)
- 金: #c9b037 (泥金)
```

#### 2. 排版系统
```
📐 字体层级：

标题字体选择：
- 英文: "Playfair Display", "Space Grotesk", "Clash Display"
- 中文: "Source Han Serif CN", "Noto Serif SC", "霞鹜文楷"

正文字体：
- 英文: "Inter", "Switzer", "General Sans"
- 中文: "Source Han Sans CN", "Noto Sans SC"

字号比例：
- Hero: 64px / 4rem (行高 1.1)
- H1: 48px / 3rem (行高 1.2)
- H2: 32px / 2rem (行高 1.3)
- H3: 24px / 1.5rem (行高 1.4)
- Body: 16px / 1rem (行高 1.7)
- Small: 14px / 0.875rem (行高 1.5)
- Caption: 12px / 0.75rem (行高 1.4)

字重策略：
- 标题: 600-700 (SemiBold-Bold)
- 正文: 400-450 (Regular)
- 强调: 500-550 (Medium)
- 轻量: 300-350 (Light)
```

#### 3. 间距系统
```
📏 8pt 基准网格：

基础单位: 4px
--space-1: 4px   (0.25rem)
--space-2: 8px   (0.5rem)
--space-3: 12px  (0.75rem)
--space-4: 16px  (1rem)
--space-5: 24px  (1.5rem)
--space-6: 32px  (2rem)
--space-7: 48px  (3rem)
--space-8: 64px  (4rem)
--space-9: 96px  (6rem)
--space-10: 128px (8rem)

组件间距：
- 卡片内边距: 24px-32px
- 表单字段间距: 16px-20px
- 按钮内边距: 12px 24px (垂直 水平)
- 列表项间距: 8px-12px
```

#### 4. 细节控的质感

**边框处理：**
```css
/* 细线边框 - 精致感 */
--border-thin: 1px solid rgba(0, 0, 0, 0.08);

/*  hairline 边框 - 极细 */
--border-hairline: 0.5px solid rgba(0, 0, 0, 0.06);

/* 双色边框 - 立体感 */
--border-double: 
  1px solid rgba(255, 255, 255, 0.1),
  1px solid rgba(0, 0, 0, 0.1);
```

**阴影层次：**
```css
/* 悬浮感 */
--shadow-float: 0 2px 8px rgba(0, 0, 0, 0.04);

/* 卡片抬升 */
--shadow-elevate: 
  0 1px 2px rgba(0, 0, 0, 0.02),
  0 4px 12px rgba(0, 0, 0, 0.04);

/* 模态聚焦 */
--shadow-focus: 
  0 0 0 1px rgba(0, 0, 0, 0.05),
  0 20px 40px rgba(0, 0, 0, 0.1);
```

**圆角策略：**
```css
/* 小圆角 - 精致 */
--radius-sm: 4px;

/* 中圆角 - 友好 */
--radius-md: 8px;

/* 大圆角 - 柔和 */
--radius-lg: 12px;

/* 全圆 - 按钮/标签 */
--radius-full: 9999px;
```

## 组件设计规范

### Button 按钮
```tsx
// 主按钮 - 实心填充
<button className="
  px-6 py-3 
  bg-[#2d2d2d] 
  text-white 
  text-sm font-medium
  rounded-md
  transition-all duration-200
  hover:bg-[#1a1a1a]
  active:scale-[0.98]
  focus:outline-none focus:ring-2 focus:ring-[#2d2d2d]/20
">
  确认操作
</button>

// 次按钮 - 描边风格
<button className="
  px-6 py-3
  bg-transparent
  border border-[#e5e5e5]
  text-[#2d2d2d]
  text-sm font-medium
  rounded-md
  transition-all duration-200
  hover:bg-[#faf9f7] hover:border-[#d4d4d4]
  active:bg-[#f0f0f0]
">
  取消
</button>
```

### Card 卡片
```tsx
// 编辑主义风格卡片
<div className="
  bg-white
  border border-[#e5e5e5]
  rounded-lg
  p-6
  transition-all duration-200
  hover:border-[#d4d4d4]
  hover:shadow-[0_2px_8px_rgba(0,0,0,0.04)]
">
  <div className="flex items-start justify-between mb-4">
    <h3 className="text-lg font-semibold text-[#2d2d2d]">卡片标题</h3>
    <span className="text-xs text-[#6b7280] uppercase tracking-wider">标签</span>
  </div>
  <p className="text-[#6b7280] leading-relaxed">
    卡片内容描述，使用舒适的行高和灰度层次。
  </p>
</div>
```

### Input 输入框
```tsx
// 精致输入框
<div className="space-y-2">
  <label className="text-sm font-medium text-[#2d2d2d]">
    邮箱地址
  </label>
  <input 
    type="email"
    className="
      w-full px-4 py-3
      bg-white
      border border-[#e5e5e5]
      rounded-md
      text-[#2d2d2d] placeholder:text-[#9ca3af]
      transition-all duration-200
      focus:outline-none focus:border-[#2d2d2d] focus:ring-1 focus:ring-[#2d2d2d]/10
      hover:border-[#d4d4d4]
    "
    placeholder="name@example.com"
  />
</div>
```

## 动效设计

### 原则
- **克制**: 动画时长 150-300ms
- **目的性**: 每个动画都有功能意义
- **一致性**: 使用相同的缓动函数

### 缓动函数
```css
--ease-out: cubic-bezier(0.16, 1, 0.3, 1);
--ease-in-out: cubic-bezier(0.65, 0, 0.35, 1);
--ease-spring: cubic-bezier(0.34, 1.56, 0.64, 1);
```

## 设计检查清单

### 视觉层次
- [ ] 标题、正文、辅助文字有明显区分
- [ ] 重要操作使用主色强调
- [ ] 信息层级通过间距而非分割线区分

### 交互反馈
- [ ] 所有可点击元素有 hover 状态
- [ ] 按钮有 active/pressed 状态
- [ ] 表单元素有 focus 状态
- [ ] 加载状态有明确指示

### 细节打磨
- [ ] 文字无锯齿 (antialiased)
- [ ] 图片有圆角或统一风格
- [ ] 空状态有友好提示
- [ ] 错误状态有清晰指引

### 响应式
- [ ] 移动端触控区域 ≥ 44px
- [ ] 文字在移动端适当缩小
- [ ] 布局在不同屏幕有适配
- [ ] 图片有合适的 object-fit

## 总结

这个 skill 的核心是：**克制、精致、有目的性**

- 用色克制但有记忆点
- 排版清晰但有层次
- 动效微妙但有反馈
- 细节打磨但不炫技

设计不是堆砌特效，而是解决问题的同时带来愉悦感。
