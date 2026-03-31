# Finetune Platform Design Tokens Document

本文件定义了 Finetune Platform 2.0 的高级设计令牌系统，旨在确保全平台视觉一致性，并支持 4K/Retina 等高分辨率显示。

## 1. 字体系统 (Typography)

### 1.1 字体族 (Font Families)
- **Sans (UI)**: `Inter`, -apple-system, BlinkMacSystemFont...
- **Mono (Code)**: `JetBrains Mono`, `Fira Code`...
- **Serif (Headings)**: `Source Han Serif CN`, `Noto Serif SC`...

### 1.2 流体字号 (Fluid Font Sizes)
使用 `clamp()` 实现随屏幕宽度自动缩放：
- **xs**: 12px -> 14px
- **sm**: 14px -> 16px
- **base**: 15px -> 18px
- **lg**: 17px -> 20px
- **xl**: 19px -> 24px
- **2xl**: 22px -> 32px
- **3xl**: 28px -> 40px
- **4xl**: 36px -> 56px
- **5xl**: 48px -> 80px

## 2. 阴影与深度 (Shadows & Depth)

### 2.1 基础阴影 (Standard Shadows)
- `xs` / `sm` / `md` / `lg` / `xl` / `2xl`
- 采用分层阴影技术，增强物理空间感。

### 2.2 特殊阴影 (Special Shadows)
- **Glass**: 用于玻璃拟态组件，提供柔和的扩散效果。
- **Neumorph-Out**: 物理凹凸质感的外阴影。
- **Neumorph-In**: 物理凹凸质感的内阴影。

## 3. 玻璃拟态 (Glassmorphism)

- **Background**: 半透明背景（亮色 0.65, 深色 0.6）。
- **Border**: 极细半透明边框，模拟高光。
- **Blur**: 12px - 16px 的高强度毛玻璃效果。
- **Saturate**: 150% - 180% 增强背景色彩饱和度。

## 4. 间距系统 (Spacing)

遵循 8pt 网格系统，建议使用 `var(--space-*)`。
- `space-1`: 4px
- `space-4`: 16px
- `space-8`: 32px
- ...

## 5. 主题色彩 (Themes)

### 5.1 亮色主题 (Light Theme - Editorial Style)
- **Primary**: `#faf9f7` (纸白背景)
- **Accent**: `#d4a373` (铜金)
- **Secondary Accent**: `#5b8a72` (石青)

### 5.2 深色主题 (Dark Theme - Premium Dark)
- **Primary**: `#1a1a1a` (深空灰)
- **Accent**: `#d4a373` (铜金)
- **Success**: `#7aa88f` (暗石青)

## 7. 组件使用指南 (Component Usage)

### 7.1 GlassCard (玻璃拟态卡片)
- **用途**: 容器、面板、统计卡片。
- **属性**: `intensity` ('low' | 'medium' | 'high'), `noHover` (boolean).
- **位置**: `src/components/shared/GlassCard.tsx`

### 7.2 NeumorphicButton (物理质感按钮)
- **用途**: 主要操作、切换开关、工具栏按钮。
- **属性**: `variant` ('primary' | 'secondary' | 'danger' | 'ghost'), `active` (boolean).
- **位置**: `src/components/shared/NeumorphicButton.tsx`

### 7.3 PremiumInput (高级输入框)
- **用途**: 表单、搜索框。
- **属性**: `icon`, `error`, `label`.
- **位置**: `src/components/shared/PremiumInput.tsx`

### 7.4 AnimatedLayout (页面过渡容器)
- **用途**: 页面级包装，提供平滑的入场和退场动画。
- **位置**: `src/components/shared/AnimatedLayout.tsx`
