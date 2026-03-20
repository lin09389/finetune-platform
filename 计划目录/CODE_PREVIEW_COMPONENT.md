# 代码预览组件文档

## 📦 组件位置

```
client/src/components/CodePreview.tsx
```

## ✨ 功能特性

| 功能 | 说明 |
|------|------|
| ✅ 语法高亮 | 基于 highlight.js，支持 9 种常用语言 |
| ✅ 一键复制 | 点击复制按钮即可复制全部代码 |
| ✅ 保存为文件 | 自动根据语言类型生成正确的文件扩展名 |
| ✅ 语言检测 | 自动识别代码语言，也支持手动切换 |
| ✅ 行号显示 | 左侧显示代码行号，方便定位 |
| ✅ 折叠/展开 | 可折叠代码区域，节省空间 |
| ✅ 全屏预览 | 弹窗模式全屏查看代码 |
| ✅ 主题切换 | 自动适配深色/浅色模式 |
| ✅ 行数统计 | 底部显示总行数和当前语言 |

## 🎯 支持的语言

- **Python** (`.py`)
- **JavaScript** (`.js`)
- **TypeScript** (`.ts`)
- **JSON** (`.json`)
- **XML/HTML** (`.xml`)
- **Bash/Shell** (`.sh`)
- **YAML** (`.yaml`)
- **Markdown** (`.md`)
- **纯文本** (`.txt`)

## 📖 使用示例

### 基础用法

```tsx
import CodePreview from './components/CodePreview'

function App() {
  const code = `
def hello_world():
    print("Hello, World!")
`
  
  return (
    <CodePreview
      code={code}
      language="python"
      title="示例代码"
    />
  )
}
```

### 完整配置

```tsx
<CodePreview
  code={code}
  language="auto"              // 自动检测语言
  showLineNumbers={true}       // 显示行号
  collapsible={true}           // 可折叠
  showFullscreen={true}        // 显示全屏按钮
  showSave={true}              // 显示保存按钮
  defaultFilename="my-code"    // 默认文件名
  maxHeight={500}              // 最大高度 (px)
  title="我的代码"              // 标题
  className="custom-class"     // 自定义类名
/>
```

### 在 Markdown 中使用

组件已集成到 `ChatMessage` 组件中，当 AI 回复包含代码块时自动使用：

```markdown
这里是 Python 代码示例：

```python
def greet(name):
    return f"Hello, {name}!"
```

更多详情请查看文档。
```

## 🔧 Props 接口

```typescript
interface CodePreviewProps {
  /** 代码内容 */
  code: string
  
  /** 编程语言，可自动检测 (默认：'auto') */
  language?: string
  
  /** 是否显示行号 (默认：true) */
  showLineNumbers?: boolean
  
  /** 是否可折叠 (默认：true) */
  collapsible?: boolean
  
  /** 是否显示全屏按钮 (默认：true) */
  showFullscreen?: boolean
  
  /** 是否显示保存按钮 (默认：true) */
  showSave?: boolean
  
  /** 默认文件名（保存时使用）(默认：'code') */
  defaultFilename?: string
  
  /** 最大高度（px）(默认：500) */
  maxHeight?: number
  
  /** 自定义类名 */
  className?: string
  
  /** 代码块标题 */
  title?: string
}
```

## 🎨 界面预览

```
┌─────────────────────────────────────────────────┐
│  示例代码                              [语言 ▼] │
│  [📋复制] [💾保存] [⛶全屏] [≡折叠]              │
├─────────────────────────────────────────────────┤
│  1  │ def hello_world():                        │
│  2  │     print("Hello, World!")                │
│  3  │                                           │
│  4  │ if __name__ == "__main__":                │
│  5  │     hello_world()                         │
│     │                                           │
├─────────────────────────────────────────────────┤
│  5 行                              python        │
└─────────────────────────────────────────────────┘
```

## 🚀 技术实现

- **语法高亮**: `highlight.js` (atom-one-dark 主题)
- **UI 组件**: `antd` Card、Button、Select、Modal
- **语言检测**: 基于代码特征的正则匹配
- **文件保存**: `Blob` + `<a>` 标签下载
- **复制功能**: `navigator.clipboard.writeText`

## 📝 更新日志

### 2026-03-08
- ✅ 初始版本发布
- ✅ 集成到 ChatMessage 组件
- ✅ 支持 9 种编程语言
- ✅ 完整的前后端功能

## 🔮 未来优化

- [ ] 支持更多编程语言
- [ ] 代码搜索/高亮匹配
- [ ] 代码缩进调整
- [ ] 自定义主题选择
- [ ] 代码 diff 对比
- [ ] 在线运行代码（沙箱环境）
