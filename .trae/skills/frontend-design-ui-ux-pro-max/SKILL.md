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

/* 不使用: 大模糊阴影如 0 25px 50px -12px rgba(0,0,0,0.25) */
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

/* 不使用: 统一 16px+ 大圆角 */
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

// 文字按钮 - 极简
<button className="
  px-2 py-1
  text-[#2d2d2d]
  text-sm font-medium
  underline-offset-4
  hover:underline
  transition-all
">
  查看详情
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
  <p className="text-xs text-[#6b7280]">我们将发送验证邮件到此地址</p>
</div>
```

### Navigation 导航
```tsx
// 顶部导航 - 编辑风格
<nav className="
  sticky top-0 z-50
  bg-[#faf9f7]/95 backdrop-blur-sm
  border-b border-[#e5e5e5]
">
  <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
    {/* Logo */}
    <div className="flex items-center gap-2">
      <div className="w-8 h-8 bg-[#2d2d2d] rounded-md flex items-center justify-center">
        <span className="text-white font-bold text-sm">L</span>
      </div>
      <span className="font-semibold text-[#2d2d2d] tracking-tight">Logo</span>
    </div>
    
    {/* Nav Links */}
    <div className="flex items-center gap-1">
      {['首页', '产品', '关于', '联系'].map((item) => (
        <a
          key={item}
          href="#"
          className="
            px-4 py-2
            text-sm text-[#6b7280]
            rounded-md
            transition-all duration-200
            hover:text-[#2d2d2d] hover:bg-[#f0f0f0]
          "
        >
          {item}
        </a>
      ))}
    </div>
    
    {/* CTA */}
    <button className="
      px-4 py-2
      bg-[#2d2d2d] text-white
      text-sm font-medium
      rounded-md
      transition-all duration-200
      hover:bg-[#1a1a1a]
    ">
      开始使用
    </button>
  </div>
</nav>
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

### 推荐动画
```tsx
// 淡入上移 - 内容加载
const fadeInUp = {
  initial: { opacity: 0, y: 10 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: 0.3, ease: [0.16, 1, 0.3, 1] }
};

// 缩放反馈 - 点击
const tapScale = {
  whileTap: { scale: 0.98 },
  transition: { duration: 0.1 }
};

// 悬浮抬升 - 卡片
const hoverLift = {
  whileHover: { y: -2 },
  transition: { duration: 0.2, ease: [0.16, 1, 0.3, 1] }
};
```

## 布局原则

### 容器系统
```
📦 最大宽度：
- 阅读内容: max-w-2xl (672px)
- 标准内容: max-w-4xl (896px)
- 宽屏内容: max-w-6xl (1152px)
- 全宽: 100%

水平内边距：
- 移动端: px-4 (16px)
- 平板: px-6 (24px)
- 桌面: px-8 (32px)
```

### 网格系统
```tsx
// 响应式网格
<div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
  {items.map(item => <Card key={item.id} {...item} />)}
</div>

// 不对称布局
<div className="grid grid-cols-12 gap-6">
  <div className="col-span-12 lg:col-span-8">主要内容</div>
  <div className="col-span-12 lg:col-span-4">侧边栏</div>
</div>
```

## 图标系统

### 推荐图标库
- **Lucide React** - 精致、一致
- **Heroicons** - 简洁、友好
- **Radix Icons** - 极简、现代

### 使用规范
```tsx
// 图标尺寸
<size-16 />  // 12px - 行内小图标
<size-20 />  // 16px - 按钮图标
<size-24 />  // 20px - 导航图标
<size-32 />  // 24px - 功能图标

// 图标+文字按钮
<button className="flex items-center gap-2 px-4 py-2">
  <PlusIcon className="w-4 h-4" />
  <span>新建</span>
</button>
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

## 代码示例：完整页面

```tsx
// Dashboard 页面 - 编辑主义风格
export default function Dashboard() {
  return (
    <div className="min-h-screen bg-[#faf9f7]">
      {/* Navigation */}
      <nav className="sticky top-0 z-50 bg-white/95 backdrop-blur border-b border-[#e5e5e5]">
        <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-[#2d2d2d] rounded-lg flex items-center justify-center">
              <span className="text-white font-bold">D</span>
            </div>
            <span className="font-semibold text-[#2d2d2d]">Dashboard</span>
          </div>
          <div className="flex items-center gap-4">
            <button className="p-2 text-[#6b7280] hover:text-[#2d2d2d] transition-colors">
              <BellIcon className="w-5 h-5" />
            </button>
            <div className="w-8 h-8 bg-[#d4a373] rounded-full" />
          </div>
        </div>
      </nav>

      {/* Main Content */}
      <main className="max-w-6xl mx-auto px-6 py-8">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-2xl font-semibold text-[#2d2d2d] mb-2">
            欢迎回来
          </h1>
          <p className="text-[#6b7280]">
            今天有 3 个任务需要处理
          </p>
        </div>

        {/* Stats Grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
          {[
            { label: '总项目', value: '24', change: '+12%' },
            { label: '进行中', value: '8', change: '+3' },
            { label: '已完成', value: '16', change: '98%' }
          ].map((stat) => (
            <div 
              key={stat.label}
              className="
                bg-white border border-[#e5e5e5] rounded-lg p-6
                transition-all duration-200
                hover:border-[#d4d4d4] hover:shadow-[0_2px_8px_rgba(0,0,0,0.04)]
              "
            >
              <p className="text-sm text-[#6b7280] mb-1">{stat.label}</p>
              <div className="flex items-baseline gap-2">
                <span className="text-3xl font-semibold text-[#2d2d2d]">
                  {stat.value}
                </span>
                <span className="text-sm text-[#5b8a72] font-medium">
                  {stat.change}
                </span>
              </div>
            </div>
          ))}
        </div>

        {/* Content Section */}
        <div className="bg-white border border-[#e5e5e5] rounded-lg">
          <div className="px-6 py-4 border-b border-[#e5e5e5] flex items-center justify-between">
            <h2 className="font-semibold text-[#2d2d2d]">最近项目</h2>
            <button className="text-sm text-[#6b7280] hover:text-[#2d2d2d] transition-colors">
              查看全部
            </button>
          </div>
          <div className="divide-y divide-[#e5e5e5]">
            {[1, 2, 3].map((i) => (
              <div 
                key={i}
                className="
                  px-6 py-4 flex items-center justify-between
                  transition-colors hover:bg-[#faf9f7]
                "
              >
                <div className="flex items-center gap-4">
                  <div className="w-10 h-10 bg-[#f0f0f0] rounded-lg flex items-center justify-center">
                    <FolderIcon className="w-5 h-5 text-[#6b7280]" />
                  </div>
                  <div>
                    <p className="font-medium text-[#2d2d2d]">项目 {i}</p>
                    <p className="text-sm text-[#6b7280]">更新于 2 小时前</p>
                  </div>
                </div>
                <ChevronRightIcon className="w-5 h-5 text-[#9ca3af]" />
              </div>
            ))}
          </div>
        </div>
      </main>
    </div>
  );
}
```

## 总结

这个 skill 的核心是：**克制、精致、有目的性**

- 用色克制但有记忆点
- 排版清晰但有层次
- 动效微妙但有反馈
- 细节打磨但不炫技

设计不是堆砌特效，而是解决问题的同时带来愉悦感。
