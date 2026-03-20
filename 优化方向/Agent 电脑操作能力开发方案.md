# 🤖 Agent 电脑操作能力 - 开发方案

## 🎯 核心目标

让 AI Agent 能够**直接操作你的电脑**，执行实际任务

---

## 📊 业界现状

### 已有的解决方案

| 产品 | 能力 | 开源 | 本地 | 难度 |
|------|------|------|------|------|
| **Claude Computer Use** | 操作电脑 | ❌ | ❌ | 高 |
| **OpenAI Operator** | 操作浏览器 | ❌ | ❌ | 高 |
| **AutoGPT** | 执行任务链 | ✅ | ✅ | 中 |
| **AgentGPT** | 执行任务 | ✅ | ✅ | 中 |
| **PyAutoGUI** | 模拟操作 | ✅ | ✅ | 低 |
| **Playwright** | 浏览器自动化 | ✅ | ✅ | 低 |
| **Robot Framework** | RPA 自动化 | ✅ | ✅ | 中 |

---

## 🏗️ 你的项目优势

### 现有架构完美适合

```
你的项目：
✅ Electron 桌面应用（系统权限）
✅ Python 后端（丰富的自动化库）
✅ FastAPI（API 接口）
✅ React 前端（可视化编辑器）

业界方案需要从零搭建，你的项目已有基础！
```

---

## 🎯 推荐方案：Python Agent + Electron

### 架构设计

```
┌─────────────────────────────────────────────────────────┐
│              用户界面（React）                           │
│  ┌─────────────────────────────────────────────────┐   │
│  │  工作流编辑器                                    │   │
│  │  - 拖拽式任务编排                               │   │
│  │  - 可视化操作流程                               │   │
│  └─────────────────────────────────────────────────┘   │
└─────────────────────┬───────────────────────────────────┘
                      │ HTTP
┌─────────────────────▼───────────────────────────────────┐
│              Agent 大脑（Python）                        │
│  ┌─────────────────────────────────────────────────┐   │
│  │  任务理解                                        │   │
│  │  - 分析用户意图                                  │   │
│  │  - 生成执行计划                                  │   │
│  └─────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────┐   │
│  │  执行引擎                                        │   │
│  │  - 文件操作                                      │   │
│  │  - 应用操作                                      │   │
│  │  - 浏览器操作                                    │   │
│  └─────────────────────────────────────────────────┘   │
└─────────────────────┬───────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────┐
│              操作层（PyAutoGUI）                        │
│  - 鼠标操作（点击、移动、拖拽）                        │
│  - 键盘操作（输入、快捷键）                            │
│  - 屏幕识别（OCR、图像识别）                          │
│  - 文件操作（读写、移动、删除）                       │
└─────────────────────────────────────────────────────────┘
```

---

## 📝 详细实现

### 第一层：Agent 大脑

#### 1. 任务理解模块

```python
# server/agent/brain.py

from typing import Dict, List, Any
import json

class AgentBrain:
    """Agent 大脑 - 理解任务并生成执行计划"""
    
    def __init__(self, llm_client):
        self.llm = llm_client
    
    async def understand_task(
        self,
        user_input: str,
        context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """理解用户任务"""
        
        # 构建提示词
        prompt = f"""
你是一个电脑操作助手。用户想要执行任务，请分析任务并生成执行计划。

用户输入：{user_input}

上下文：
{json.dumps(context, ensure_ascii=False, indent=2)}

请返回 JSON 格式的执行计划：
{{
  "task_type": "file_operation | app_operation | browser_operation | system_operation",
  "description": "任务描述",
  "steps": [
    {{
      "action": "click | type | scroll | open_app | open_file | ...",
      "target": "目标元素或文件",
      "params": {{}},
      "description": "步骤描述"
    }}
  ],
  "risk_level": "low | medium | high",
  "estimated_time": "预估时间（秒）"
}}

只返回 JSON，不要其他内容。
"""
        
        # 调用 LLM
        response = await self.llm.generate(prompt)
        
        # 解析响应
        try:
            plan = json.loads(response)
            return plan
        except:
            return {
                "task_type": "unknown",
                "description": "无法理解任务",
                "steps": [],
                "risk_level": "high"
            }
    
    def validate_plan(self, plan: Dict) -> bool:
        """验证执行计划是否安全"""
        # 禁止的操作
        forbidden = [
            "format disk",
            "delete system",
            "shutdown",
            "reboot",
            "registry edit",
            "install software"
        ]
        
        for step in plan.get("steps", []):
            action = step.get("action", "").lower()
            for f in forbidden:
                if f in action:
                    return False
        
        return True
```

---

### 第二层：执行引擎

#### 2. 操作执行器

```python
# server/agent/executor.py

import pyautogui
import pyperclip
import os
import subprocess
from pathlib import Path
from typing import Dict, List, Any
import asyncio

class ComputerOperator:
    """电脑操作器 - 执行具体操作"""
    
    def __init__(self):
        # 安全设置
        pyautogui.FAILSAFE = True  # 移动鼠标到角落可中止
        pyautogui.PAUSE = 0.1      # 每个操作后暂停
        
        # 操作映射
        self.actions = {
            # 鼠标操作
            'click': self.click,
            'double_click': self.double_click,
            'right_click': self.right_click,
            'move': self.move_mouse,
            'drag': self.drag,
            'scroll': self.scroll,
            
            # 键盘操作
            'type': self.type_text,
            'hotkey': self.hotkey,
            'press': self.press_key,
            
            # 文件操作
            'open_file': self.open_file,
            'create_file': self.create_file,
            'delete_file': self.delete_file,
            'move_file': self.move_file,
            'copy_file': self.copy_file,
            'list_files': self.list_files,
            
            # 应用操作
            'open_app': self.open_app,
            'close_app': self.close_app,
            'switch_app': self.switch_app,
            
            # 浏览器操作
            'open_url': self.open_url,
            
            # 系统
            'screenshot': self.take_screenshot,
            'wait': self.wait
        }
    
    async def execute(
        self,
        action: str,
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """执行操作"""
        if action not in self.actions:
            return {
                "success": False,
                "error": f"未知操作: {action}"
            }
        
        try:
            result = await self.actions[action](**params)
            return {
                "success": True,
                "result": result
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    # ========== 鼠标操作 ==========
    
    async def click(
        self,
        x: int = None,
        y: int = None,
        button: str = 'left'
    ):
        """点击"""
        if x and y:
            pyautogui.click(x, y, button=button)
        else:
            pyautogui.click(button=button)
        return {"clicked": True}
    
    async def double_click(self, x: int = None, y: int = None):
        """双击"""
        if x and y:
            pyautogui.doubleClick(x, y)
        else:
            pyautogui.doubleClick()
        return {"double_clicked": True}
    
    async def right_click(self, x: int = None, y: int = None):
        """右键点击"""
        if x and y:
            pyautogui.rightClick(x, y)
        else:
            pyautogui.rightClick()
        return {"right_clicked": True}
    
    async def move_mouse(self, x: int, y: int, duration: float = 0.5):
        """移动鼠标"""
        pyautogui.moveTo(x, y, duration=duration)
        return {"moved_to": (x, y)}
    
    async def drag(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        duration: float = 1.0
    ):
        """拖拽"""
        pyautogui.moveTo(start_x, start_y)
        pyautogui.drag(end_x - start_x, end_y - start_y, duration)
        return {"dragged": True}
    
    async def scroll(self, clicks: int, direction: str = 'down'):
        """滚动"""
        if direction == 'up':
            pyautogui.scroll(clicks)
        else:
            pyautogui.scroll(-clicks)
        return {"scrolled": clicks}
    
    # ========== 键盘操作 ==========
    
    async def type_text(
        self,
        text: str,
        interval: float = 0.05
    ):
        """输入文本"""
        pyautogui.typewrite(text, interval=interval)
        return {"typed": text}
    
    async def hotkey(self, *keys: str):
        """快捷键"""
        pyautogui.hotkey(*keys)
        return {"hotkey": keys}
    
    async def press_key(self, key: str):
        """按键"""
        pyautogui.press(key)
        return {"pressed": key}
    
    # ========== 文件操作 ==========
    
    async def open_file(self, file_path: str):
        """打开文件"""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")
        
        # 使用系统默认程序打开
        os.startfile(str(path))
        return {"opened": file_path}
    
    async def create_file(
        self,
        file_path: str,
        content: str = ""
    ):
        """创建文件"""
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        return {"created": file_path}
    
    async def delete_file(self, file_path: str):
        """删除文件"""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")
        
        path.unlink()
        return {"deleted": file_path}
    
    async def move_file(
        self,
        source: str,
        destination: str
    ):
        """移动文件"""
        import shutil
        
        src = Path(source)
        dst = Path(destination)
        
        if not src.exists():
            raise FileNotFoundError(f"源文件不存在: {source}")
        
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        
        return {"moved": source, "to": destination}
    
    async def copy_file(
        self,
        source: str,
        destination: str
    ):
        """复制文件"""
        import shutil
        
        src = Path(source)
        dst = Path(destination)
        
        if not src.exists():
            raise FileNotFoundError(f"源文件不存在: {source}")
        
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(src), str(dst))
        
        return {"copied": source, "to": destination}
    
    async def list_files(
        self,
        directory: str,
        pattern: str = "*"
    ):
        """列出文件"""
        dir_path = Path(directory)
        if not dir_path.exists():
            raise FileNotFoundError(f"目录不存在: {directory}")
        
        files = list(dir_path.glob(pattern))
        
        return {
            "files": [
                {
                    "name": f.name,
                    "path": str(f),
                    "is_dir": f.is_dir(),
                    "size": f.stat().st_size if f.is_file() else 0
                }
                for f in files
            ]
        }
    
    # ========== 应用操作 ==========
    
    async def open_app(self, app_name: str):
        """打开应用"""
        # Windows
        if os.name == 'nt':
            subprocess.Popen(app_name)
        # macOS
        elif os.name == 'posix':
            subprocess.Popen(['open', '-a', app_name])
        
        return {"opened_app": app_name}
    
    async def close_app(self, app_name: str):
        """关闭应用"""
        # Windows
        if os.name == 'nt':
            os.system(f'taskkill /f /im {app_name}')
        # macOS
        elif os.name == 'posix':
            os.system(f'killall {app_name}')
        
        return {"closed_app": app_name}
    
    async def switch_app(self, app_name: str):
        """切换应用"""
        # Windows: Alt + Tab
        # macOS: Cmd + Tab
        
        if os.name == 'nt':
            pyautogui.hotkey('alt', 'tab')
        else:
            pyautogui.hotkey('command', 'tab')
        
        await asyncio.sleep(0.5)
        return {"switched_to": app_name}
    
    # ========== 浏览器操作 ==========
    
    async def open_url(self, url: str):
        """打开 URL"""
        import webbrowser
        webbrowser.open(url)
        return {"opened_url": url}
    
    # ========== 系统操作 ==========
    
    async def take_screenshot(
        self,
        save_path: str = None
    ):
        """截图"""
        if save_path:
            screenshot = pyautogui.screenshot()
            screenshot.save(save_path)
            return {"saved": save_path}
        else:
            screenshot = pyautogui.screenshot()
            return {"screenshot": "captured"}
    
    async def wait(self, seconds: float):
        """等待"""
        await asyncio.sleep(seconds)
        return {"waited": seconds}
```

---

### 第三层：Agent 编排器

#### 3. 工作流引擎

```python
# server/agent/orchestrator.py

from typing import Dict, List, Any
import asyncio

class AgentOrchestrator:
    """Agent 编排器 - 协调任务执行"""
    
    def __init__(self, brain, operator):
        self.brain = brain
        self.operator = operator
        self.history = []
    
    async def execute_task(
        self,
        user_input: str,
        context: Dict = None
    ) -> Dict[str, Any]:
        """执行完整任务"""
        
        # 1. 理解任务
        plan = await self.brain.understand_task(user_input, context)
        
        # 2. 验证计划
        if not self.brain.validate_plan(plan):
            return {
                "success": False,
                "error": "任务计划不安全，已拒绝执行"
            }
        
        # 3. 执行步骤
        results = []
        for i, step in enumerate(plan["steps"]):
            # 记录执行前状态
            before_state = await self._capture_state()
            
            # 执行操作
            result = await self.operator.execute(
                step["action"],
                step.get("params", {})
            )
            
            # 记录
            self.history.append({
                "step": i,
                "action": step["action"],
                "result": result,
                "before": before_state
            })
            
            results.append(result)
            
            # 如果失败，停止执行
            if not result.get("success"):
                return {
                    "success": False,
                    "error": f"步骤 {i} 失败: {result.get('error')}",
                    "completed_steps": results
                }
        
        return {
            "success": True,
            "plan": plan,
            "results": results
        }
    
    async def _capture_state(self) -> Dict:
        """捕获当前状态"""
        # 截图
        screenshot = pyautogui.screenshot()
        
        # 鼠标位置
        mouse_pos = pyautogui.position()
        
        return {
            "mouse_position": mouse_pos,
            "timestamp": time.time()
        }
```

---

### 第四层：API 接口

```python
# server/api/agent.py

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any

router = APIRouter()

class TaskRequest(BaseModel):
    user_input: str
    context: Dict[str, Any] = None

@router.post("/execute")
async def execute_task(request: TaskRequest):
    """执行任务"""
    orchestrator = get_orchestrator()
    
    result = await orchestrator.execute_task(
        user_input=request.user_input,
        context=request.context
    )
    
    return result

@router.get("/history")
async def get_history():
    """获取执行历史"""
    orchestrator = get_orchestrator()
    return {"history": orchestrator.history}

@router.post("/abort")
async def abort_task():
    """中止任务"""
    # 移动鼠标到角落触发 FAILSAFE
    pyautogui.moveTo(0, 0)
    return {"aborted": True}
```

---

### 第五层：前端界面

#### 4. 可视化工作流编辑器

```tsx
// client/src/pages/AgentWorkflow.tsx

import React, { useState } from 'react'
import ReactFlow, { 
  Node, 
  Edge, 
  addEdge,
  useNodesState,
  useEdgesState
} from 'reactflow'
import 'reactflow/dist/style.css'

const nodeTypes = {
  action: ActionNode,
  condition: ConditionNode,
  loop: LoopNode
}

export const AgentWorkflow: React.FC = () => {
  const [nodes, setNodes, onNodesChange] = useNodesState([])
  const [edges, setEdges, onEdgesChange] = useEdgesState([])
  const [executing, setExecuting] = useState(false)
  
  // 执行工作流
  const execute = async () => {
    setExecuting(true)
    
    // 遍历节点执行
    for (const node of nodes) {
      if (node.type === 'action') {
        await executeAction(node.data)
      }
    }
    
    setExecuting(false)
  }
  
  return (
    <div style={{ height: 600 }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        nodeTypes={nodeTypes}
      />
      
      <button 
        onClick={execute}
        disabled={executing}
      >
        {executing ? '执行中...' : '执行'}
      </button>
    </div>
  )
}

// 动作节点
function ActionNode({ data }) {
  return (
    <div className="action-node">
      <div>{data.label}</div>
      <div>{data.action}</div>
    </div>
  )
}
```

---

## 🎯 支持的操作类型

### 1. 文件操作

```python
示例任务：
"打开 C:/Users/Documents/report.pdf"
"创建一个 test.txt 文件"
"把所有图片移到 Pictures 文件夹"
"删除临时文件"
"列出当前目录的文件"
```

### 2. 应用操作

```python
示例任务：
"打开 VS Code"
"关闭记事本"
"切换到浏览器"
"打开微信"
```

### 3. 浏览器操作

```python
示例任务：
"打开 github.com"
"在浏览器中搜索..."
```

### 4. 输入操作

```python
示例任务：
"在搜索框输入..."
"点击确定按钮"
"复制这段文字"
```

### 5. 屏幕识别（高级）

```python
示例任务：
"找到登录按钮并点击"
"识别屏幕上的文字"
"找到图片位置"
```

---

## 📊 安全措施

### 1. 操作白名单

```python
# 只允许这些操作
ALLOWED_ACTIONS = [
    'open_file',
    'create_file',
    'list_files',
    'open_app',
    'open_url',
    'type_text',
    'click',
    'screenshot'
]

# 禁止的操作
FORBIDDEN_ACTIONS = [
    'delete_system',
    'format_disk',
    'registry_edit',
    'install_software'
]
```

### 2. 确认机制

```python
# 危险操作需要确认
async def execute_with_confirm(
    action: str,
    params: Dict
):
    if is_dangerous(action):
        # 等待用户确认
        confirmed = await ask_user_confirm(action, params)
        if not confirmed:
            return {"success": False, "error": "用户取消"}
    
    return await execute(action, params)
```

### 3. 回滚机制

```python
# 执行前保存状态
before_state = capture_state()
result = execute_action(action)
if not result.success:
    restore_state(before_state)
```

---

## 🚀 开发计划

### 第 1 周：基础能力（20 小时）

```
Day 1-2: 核心操作器（8h）
├─ 文件操作
├─ 鼠标键盘
└─ 应用操作

Day 3-4: Agent 大脑（8h）
├─ 任务理解
├─ 计划生成
└─ 执行编排

Day 5-7: API + 测试（4h)
├─ API 接口
└─ 测试用例
```

### 第 2 周：可视化（15 小时）

```
Day 1-3: 工作流编辑器（10h)
├─ React Flow 集成
├─ 节点组件
└─ 连线逻辑

Day 4-5: 集成优化（5h)
├─ 前后端集成
└─ 用户体验
```

---

## 💡 与你的项目结合

### 现有优势

```
✅ Electron（系统权限）
✅ Python（自动化库）
✅ FastAPI（API 接口）
✅ React（可视化）
✅ RAG（知识库）
```

### 集成方案

```
1. 新增模块
├── server/agent/
│   ├── brain.py
│   ├── executor.py
│   └── orchestrator.py
└── server/api/agent.py

2. 前端新增页面
└── client/src/pages/Agent.tsx

3. 依赖
└── PyAutoGUI
    Pyperclip
    Pillow
```

---

## 📋 总结

### 你的项目做这个的优势

```
✅ 桌面应用（Electron）- 有系统权限
✅ Python 后端 - 有自动化库支持
✅ React 前端 - 可视化编辑器
✅ 已有 RAG - 知识库支持
```

### 2 周可以做出来的

```
Week 1: 基础操作能力
Week 2: 可视化工作流

成果：
- Agent 能操作电脑
- 可视化编排任务
- 安全可控
```

---

准备好开始了吗？🤖

告诉我你的想法！💪