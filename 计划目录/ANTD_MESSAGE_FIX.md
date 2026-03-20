# Ant Design Message 警告修复

## 🐛 警告信息

```
Warning: [antd: message] Static function can not consume context like dynamic theme. 
Please use 'App' component instead.
```

## 📝 问题原因

Ant Design v5 的静态 `message` 方法无法使用 Context，导致：
- 无法使用动态主题
- 无法继承配置

## ✅ 修复方案

### 修改前
```tsx
import { message } from 'antd'

export default function MyComponent() {
  message.success('操作成功')
}
```

### 修改后
```tsx
import { App } from 'antd'

export default function MyComponent() {
  const { message } = App.useApp()
  message.success('操作成功')
}
```

## 📁 已修复的文件

1. **KnowledgeBase.tsx**
   - 添加 `App` 导入
   - 使用 `const { message } = App.useApp()`

2. **WorkspaceManager.tsx**
   - 添加 `App` 导入
   - 使用 `const { message } = App.useApp()`

3. **ModelHub.tsx**
   - 添加 `App` 和 `Empty` 导入
   - 使用 `const { message } = App.useApp()`

4. **Chat.tsx**
   - 添加 `App` 导入
   - 使用 `const { message } = App.useApp()`

## 🧪 验证

```bash
cd client
npm run typecheck
# 结果：通过 ✅
```

启动前端后，控制台不再显示警告。

## 📖 参考文档

- [Ant Design App 组件](https://ant.design/components/app-cn)
- [Ant Design message 全局提示](https://ant.design/components/message-cn#static-method)

## ⚠️ 注意事项

### 必须使用 App 组件的场景
- 需要使用动态主题
- 需要使用配置继承
- 需要在 Hook 中调用

### 可以继续使用静态方法的场景
- 简单场景
- 不需要主题支持
- 工具函数中

## 🎯 最佳实践

**推荐**: 统一使用 `App.useApp()` 方式

```tsx
// 根组件确保有 App.Provider
import { App } from 'antd'

function AppWrapper() {
  return (
    <App>
      <MyComponent />
    </App>
  )
}

// 子组件使用 Hook
function MyComponent() {
  const { message } = App.useApp()
  return <Button onClick={() => message.success('成功')}>点击</Button>
}
```
