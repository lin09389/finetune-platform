# 🎉 Minimax Coding Plan 集成方案

## ✅ 可以直接使用！

你的 **Minimax Coding Plan** 完全可以在 finetune-platform 项目中使用！

---

## 📊 Minimax Coding Plan 说明

### 什么是 Coding Plan

```
Minimax Coding Plan 是 Minimax 推出的编程套餐

包含：
✅ abab6.5 模型（最强编程能力）
✅ 专用编程优化
✅ 代码理解/生成/优化
✅ 比标准版更便宜

适用场景：
- 代码生成
- 代码优化
- Bug 修复
- 代码解释
- 技术问答
```

### 套餐内容

```
Coding Plan 通常包含：
- 每月一定额度 tokens
- abab6.5 模型使用权
- 编程专用优化
- API 调用权限

价格：
- 约 ¥99-199/月（看具体套餐）
- 比按量付费划算
```

---

## 🔑 获取你的 API Key

### 如果你已经有 Key

```
格式：group_id:api_key

示例：
1234567890:abcdefghijklmnop

位置：
1. 登录 https://api.minimax.chat
2. 进入"控制台"
3. 点击"API Key 管理"
4. 复制你的 Key
```

### 如果还没有 Key

```
Step 1: 登录官网
https://api.minimax.chat

Step 2: 进入控制台
点击右上角头像 → 控制台

Step 3: 查看套餐
- 进入"套餐管理"
- 确认 Coding Plan 已激活
- 查看剩余额度

Step 4: 创建 API Key
- 进入"API Key 管理"
- 点击"创建 API Key"
- 复制 Key（只显示一次！）
```

---

## 🔧 集成到你的项目

### 第 1 步：添加到 API Key 管理

```tsx
// client/src/pages/APIKeyManager.tsx

// 在 PROVIDERS 列表中添加
const PROVIDERS = [
  { value: 'minimax', label: 'Minimax', icon: '🔵' },
  { value: 'minimax-coding', label: 'Minimax Coding', icon: '💻' }, // ⭐ 新增
  { value: 'glm', label: '智谱 GLM', icon: '🟠' },
  // ...
]
```

### 第 2 步：更新网关代码

```python
# server/ai/gateway.py

class MinimaxCodingProvider(MinimaxProvider):
    """Minimax Coding Plan 专用适配器"""
    
    def __init__(self):
        super().__init__()
        self.base_url = "https://api.minimax.chat/v1"
        self.default_model = "abab6.5-chat"  # Coding 专用模型
    
    async def chat(
        self,
        messages: List[Dict],
        model: str = "abab6.5-chat",  # 默认使用编程模型
        api_key: str = "",
        **kwargs
    ) -> str:
        # Coding Plan 有特殊优化
        # 可以添加编程相关的默认参数
        default_kwargs = {
            "temperature": 0.7,
            "max_tokens": 4096,
            "top_p": 0.95,
            "presence_penalty": 0.1,  # 鼓励多样性
        }
        
        # 合并参数
        kwargs = {**default_kwargs, **kwargs}
        
        # 调用父类方法
        return await super().chat(messages, model, api_key, **kwargs)
    
    async def stream(
        self,
        messages: List[Dict],
        model: str = "abab6.5-chat",
        api_key: str = "",
        **kwargs
    ) -> AsyncGenerator[str, None]:
        # 同样使用编程优化参数
        default_kwargs = {
            "temperature": 0.7,
            "max_tokens": 4096,
            "top_p": 0.95,
        }
        kwargs = {**default_kwargs, **kwargs}
        
        async for chunk in super().stream(messages, model, api_key, **kwargs):
            yield chunk


# 注册到 PROVIDERS
PROVIDERS: Dict[str, AIProvider] = {
    "openai": OpenAIProvider(),
    "claude": ClaudeProvider(),
    "minimax": MinimaxProvider(),
    "minimax-coding": MinimaxCodingProvider(),  # ⭐ 新增
    "glm": GLMProvider(),
}
```

### 第 3 步：更新 API 端点

```python
# server/api/cloud_chat.py

# 在模型列表中显示 Coding 专用模型
@router.get("/models/minimax-coding")
async def get_minimax_coding_models():
    """获取 Minimax Coding 可用模型"""
    return {
        "models": [
            {
                "id": "abab6.5-chat",
                "name": "abab6.5 Chat（编程优化）",
                "description": "最强编程能力，适合代码生成/优化"
            },
            {
                "id": "abab6.5",
                "name": "abab6.5（通用）",
                "description": "通用场景"
            },
            {
                "id": "abab6",
                "name": "abab6（平衡）",
                "description": "性能和成本平衡"
            }
        ]
    }
```

### 第 4 步：前端集成

```tsx
// client/src/pages/Chat.tsx

// 添加 Coding Plan 专用选项
const MODEL_OPTIONS = {
  'minimax-coding': [
    { value: 'abab6.5-chat', label: '💻 abab6.5 Chat（编程）' },
    { value: 'abab6.5', label: '🔵 abab6.5（通用）' },
    { value: 'abab6', label: '⚪ abab6（平衡）' },
  ],
  // ... 其他服务商
}

// 在 UI 中显示
<Select
  value={selectedModel}
  onChange={setSelectedModel}
  options={MODEL_OPTIONS[selectedProvider] || []}
  style={{ width: 250 }}
/>
```

---

## 📝 使用示例

### 场景 1：代码生成

```
用户："帮我写一个 Python 快速排序"

使用 Minimax Coding Plan：
✅ 自动识别编程任务
✅ 使用 abab6.5-chat 模型
✅ 生成优化后的代码
✅ 包含注释和说明
```

### 场景 2：代码优化

```
用户："优化这段代码的性能"

使用 Minimax Coding Plan：
✅ 理解代码意图
✅ 识别性能瓶颈
✅ 提供优化建议
✅ 给出优化后代码
```

### 场景 3：Bug 修复

```
用户："这段代码为什么报错？"

使用 Minimax Coding Plan：
✅ 分析错误原因
✅ 定位问题所在
✅ 提供修复方案
✅ 解释修复原理
```

---

## 💰 成本优势

### Coding Plan vs 按量付费

```
Coding Plan（套餐）：
✅ 固定月费（¥99-199）
✅ 包含大量 tokens
✅ 单价更便宜
✅ 优先支持

按量付费：
❌ 按使用量计费
❌ 单价较高
❌ 无优先支持

建议：
- 重度使用 → Coding Plan（划算）
- 轻度使用 → 按量付费（灵活）
```

### 你的套餐使用

```
查看剩余额度：
1. 登录 https://api.minimax.chat
2. 进入"控制台"
3. 查看"套餐管理"
4. 查看剩余 tokens/调用次数

监控用量：
- 设置用量告警
- 定期检查使用量
- 避免超额
```

---

## 🚀 快速开始

### 今晚就可以用（30 分钟）

```
19:00-19:10   获取 API Key
              登录官网 → 复制 Key

19:10-19:30   添加到项目
              修改 gateway.py
              添加 MinimaxCodingProvider

19:30-20:00   测试调用
              添加 Key 到管理
              测试聊天功能

20:00-20:30   优化体验
              添加编程专用提示词
              调整默认参数

产出：可以使用 Minimax Coding Plan！
```

---

## 📋 完整代码

### 简化版集成（最快）

```python
# server/ai/gateway.py (最小改动)

# 在 MinimaxProvider 中添加编程优化
class MinimaxProvider(AIProvider):
    def __init__(self, coding_mode: bool = False):
        self.base_url = "https://api.minimax.chat/v1"
        self.coding_mode = coding_mode  # 是否启用编程模式
    
    async def chat(
        self,
        messages: List[Dict],
        model: str = "abab6.5",
        api_key: str = "",
        **kwargs
    ) -> str:
        # 编程模式使用专用参数
        if self.coding_mode:
            model = "abab6.5-chat"
            kwargs = {
                "temperature": 0.7,
                "max_tokens": 4096,
                "top_p": 0.95,
                **kwargs
            }
        
        # ... 原有代码 ...
```

### 使用方式

```python
# 普通 Minimax
provider = MinimaxProvider(coding_mode=False)

# Coding Plan
provider = MinimaxProvider(coding_mode=True)
```

---

## ⚠️ 注意事项

### API Key 安全

```
✅ 要做：
- 加密存储
- 只存哈希
- 不上传云端
- 定期更换

❌ 不要：
- 明文存储
- 上传到 GitHub
- 分享给他人
```

### 套餐额度

```
✅ 建议：
- 定期检查剩余额度
- 设置用量告警
- 避免超额使用

❌ 避免：
- 无限制调用
- 不监控用量
- 滥用 API
```

### 模型选择

```
编程任务：
✅ abab6.5-chat（Coding Plan 专用）
✅ abab6.5（通用编程）

通用任务：
✅ abab6.5
✅ abab6（便宜）
```

---

## 📊 总结

### 你的优势

```
✅ 已有 Coding Plan
   - 不用额外付费
   - 编程能力强
   - 中文优化好

✅ 项目已有基础
   - Minimax 适配器已有
   - 只需小改动
   - 30 分钟可完成

✅ 用户体验好
   - 代码生成强
   - Bug 修复准
   - 中文理解好
```

### 推荐配置

```
默认模型：abab6.5-chat（编程优化）
温度：0.7（平衡创造性和准确性）
最大 tokens：4096（足够长代码）
top_p：0.95（多样性）
```

---

## 💬 你的决定

**A. 立即集成** — 我帮你写完整代码  
**B. 先看测试** — 测试 API Key 是否可用  
**C. 调整方案** — 有其他想法？  
**D. 继续提问** — 还有疑问？  

**30 分钟即可完成集成！今晚就能用！** 🚀

告诉我你的选择！💪
