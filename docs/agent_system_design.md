# OpenCode Agent 系统移植设计文档

## 目录
1. [概述](#概述)
2. [核心架构](#核心架构)
3. [Agent 定义系统](#agent-定义系统)
4. [权限系统](#权限系统)
5. [工具调用框架](#工具调用框架)
6. [实施路线图](#实施路线图)
7. [代码示例](#代码示例)

---

## 概述

本文档描述如何将 OpenCode 的 Agent 定义和管理系统移植到 finetune-platform 项目中。

### OpenCode Agent 系统核心特性

- **声明式 Agent 定义**: 使用 Markdown + YAML frontmatter 定义 Agent
- **细粒度权限控制**: 基于规则的权限系统 (allow/deny/ask)
- **Agent 模式分类**: primary/subagent/all 三种模式
- **工具调用抽象**: 统一的工具注册和执行机制
- **Effect-TS 架构**: 类型安全的副作用管理

### 移植目标

将 TypeScript/Effect-TS 架构转换为 Python/Pydantic 架构，保持核心设计思想。

---

## 核心架构

### 1. 目录结构

```
server/
├── agent/                      # Agent 系统核心
│   ├── __init__.py
│   ├── schema.py              # Agent 数据模型
│   ├── manager.py             # Agent 管理器
│   ├── loader.py              # Markdown Agent 加载器
│   ├── permission.py          # 权限系统
│   └── builtin/               # 内置 Agent 定义
│       ├── build.md
│       ├── plan.md
│       ├── explore.md
│       └── general.md
├── tools/                      # 工具系统
│   ├── __init__.py
│   ├── registry.py            # 工具注册表
│   ├── executor.py            # 工具执行器
│   ├── base.py                # 工具基类
│   └── builtin/               # 内置工具
│       ├── read.py
│       ├── write.py
│       ├── bash.py
│       └── ...
└── api/
    └── agent.py               # Agent API 端点
```

---

## Agent 定义系统

### 2.1 数据模型 (schema.py)

```python
from pydantic import BaseModel, Field
from typing import Literal, Optional, Dict, Any
from enum import Enum

class AgentMode(str, Enum):
    """Agent 模式"""
    PRIMARY = "primary"      # 用户可选的主 Agent
    SUBAGENT = "subagent"    # 被其他 Agent 调用
    ALL = "all"              # 两者皆可

class PermissionAction(str, Enum):
    """权限动作"""
    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"

class PermissionRule(BaseModel):
    """权限规则"""
    permission: str          # 权限名称 (如 "read", "edit", "bash")
    pattern: str             # 匹配模式 (支持通配符)
    action: PermissionAction

class ModelConfig(BaseModel):
    """模型配置"""
    provider_id: str         # 如 "openai", "anthropic"
    model_id: str            # 如 "gpt-4", "claude-3-opus"

class AgentInfo(BaseModel):
    """Agent 完整信息"""
    name: str                                    # Agent 唯一标识
    description: Optional[str] = None            # 描述
    mode: AgentMode                              # 模式
    native: bool = False                         # 是否内置
    hidden: bool = False                         # 是否在 UI 隐藏

    # 模型参数
    model: Optional[ModelConfig] = None
    temperature: Optional[float] = None
    top_p: Optional[float] = None

    # 提示词和配置
    prompt: Optional[str] = None                 # 系统提示词
    steps: Optional[int] = None                  # 最大迭代次数
    color: Optional[str] = None                  # UI 颜色

    # 权限和选项
    permission: list[PermissionRule] = Field(default_factory=list)
    options: Dict[str, Any] = Field(default_factory=dict)
```

### 2.2 Markdown Agent 定义格式

```markdown
---
name: explore
description: "Fast agent specialized for exploring codebases"
mode: subagent
temperature: 0.3
steps: 10
permission:
  "*": deny
  read: allow
  grep: allow
  glob: allow
  bash: allow
  external_directory:
    "*": ask
---

You are a file search specialist. You excel at thoroughly navigating and exploring codebases.

Your strengths:
- Rapidly finding files using glob patterns
- Searching code and text with powerful regex patterns
- Reading and analyzing file contents

Guidelines:
- Use Glob for broad file pattern matching
- Use Grep for searching file contents with regex
- Complete the user's search request efficiently
```

### 2.3 Agent 加载器 (loader.py)

```python
import yaml
from pathlib import Path
from typing import Dict
from .schema import AgentInfo, AgentMode, PermissionRule, PermissionAction

class AgentLoader:
    """从 Markdown 文件加载 Agent 定义"""

    @staticmethod
    def load_from_markdown(file_path: Path) -> AgentInfo:
        """解析 Markdown Agent 文件"""
        content = file_path.read_text(encoding='utf-8')

        # 分离 frontmatter 和 prompt
        if content.startswith('---'):
            parts = content.split('---', 2)
            if len(parts) >= 3:
                frontmatter = yaml.safe_load(parts[1])
                prompt = parts[2].strip()
            else:
                raise ValueError(f"Invalid markdown format in {file_path}")
        else:
            raise ValueError(f"Missing frontmatter in {file_path}")

        # 解析权限规则
        permission_rules = []
        if 'permission' in frontmatter:
            permission_rules = AgentLoader._parse_permissions(
                frontmatter.pop('permission')
            )

        # 构建 AgentInfo
        return AgentInfo(
            **frontmatter,
            prompt=prompt,
            permission=permission_rules
        )

    @staticmethod
    def _parse_permissions(config: Dict) -> list[PermissionRule]:
        """解析权限配置"""
        rules = []
        for key, value in config.items():
            if isinstance(value, str):
                # 简单格式: "read": "allow"
                rules.append(PermissionRule(
                    permission=key,
                    pattern="*",
                    action=PermissionAction(value)
                ))
            elif isinstance(value, dict):
                # 嵌套格式: "external_directory": {"*": "ask"}
                for pattern, action in value.items():
                    rules.append(PermissionRule(
                        permission=key,
                        pattern=pattern,
                        action=PermissionAction(action)
                    ))
        return rules

    @staticmethod
    def load_builtin_agents() -> Dict[str, AgentInfo]:
        """加载所有内置 Agent"""
        builtin_dir = Path(__file__).parent / "builtin"
        agents = {}

        for md_file in builtin_dir.glob("*.md"):
            agent = AgentLoader.load_from_markdown(md_file)
            agent.native = True
            agents[agent.name] = agent

        return agents
```

### 2.4 Agent 管理器 (manager.py)

```python
from typing import Dict, Optional, List
from pathlib import Path
from .schema import AgentInfo, AgentMode
from .loader import AgentLoader
from .permission import PermissionManager

class AgentManager:
    """Agent 管理器 - 负责注册、查询、权限检查"""

    def __init__(self):
        self._agents: Dict[str, AgentInfo] = {}
        self._permission_manager = PermissionManager()
        self._load_builtin_agents()

    def _load_builtin_agents(self):
        """加载内置 Agent"""
        builtin = AgentLoader.load_builtin_agents()
        self._agents.update(builtin)

    def load_user_agents(self, agents_dir: Path):
        """从目录加载用户自定义 Agent"""
        for md_file in agents_dir.rglob("*.md"):
            try:
                agent = AgentLoader.load_from_markdown(md_file)
                self._agents[agent.name] = agent
            except Exception as e:
                print(f"Failed to load agent from {md_file}: {e}")

    def get(self, name: str) -> Optional[AgentInfo]:
        """获取 Agent"""
        return self._agents.get(name)

    def list(self, include_hidden: bool = False) -> List[AgentInfo]:
        """列出所有 Agent"""
        agents = list(self._agents.values())
        if not include_hidden:
            agents = [a for a in agents if not a.hidden]
        return agents

    def list_primary(self) -> List[AgentInfo]:
        """列出所有主 Agent"""
        return [
            a for a in self._agents.values()
            if a.mode in (AgentMode.PRIMARY, AgentMode.ALL) and not a.hidden
        ]

    def list_subagents(self) -> List[AgentInfo]:
        """列出所有子 Agent"""
        return [
            a for a in self._agents.values()
            if a.mode in (AgentMode.SUBAGENT, AgentMode.ALL)
        ]

    def get_default_agent(self) -> str:
        """获取默认 Agent"""
        # 优先返回 build agent
        if "build" in self._agents:
            return "build"

        # 否则返回第一个可见的主 Agent
        primary = self.list_primary()
        if primary:
            return primary[0].name

        raise ValueError("No primary agent available")

    def check_permission(
        self,
        agent_name: str,
        permission: str,
        pattern: str
    ) -> str:
        """检查权限 - 返回 'allow'/'deny'/'ask'"""
        agent = self.get(agent_name)
        if not agent:
            return "deny"

        return self._permission_manager.evaluate(
            permission,
            pattern,
            agent.permission
        )
```

---

## 权限系统

### 3.1 权限管理器 (permission.py)

```python
import fnmatch
from typing import List
from .schema import PermissionRule, PermissionAction

class PermissionManager:
    """权限评估引擎"""

    @staticmethod
    def evaluate(
        permission: str,
        pattern: str,
        ruleset: List[PermissionRule]
    ) -> str:
        """
        评估权限

        规则:
        1. 从后往前匹配 (最后定义的规则优先级最高)
        2. 同时匹配 permission 和 pattern
        3. 支持通配符 (*, **)
        """
        # 反向遍历规则列表
        for rule in reversed(ruleset):
            if PermissionManager._match(permission, rule.permission) and \
               PermissionManager._match(pattern, rule.pattern):
                return rule.action.value

        # 默认策略: ask
        return "ask"

    @staticmethod
    def _match(text: str, pattern: str) -> bool:
        """通配符匹配"""
        # 支持 * 和 ** 通配符
        if pattern == "*":
            return True

        # 使用 fnmatch 进行路径匹配
        return fnmatch.fnmatch(text, pattern)

    @staticmethod
    def merge_rulesets(*rulesets: List[PermissionRule]) -> List[PermissionRule]:
        """合并多个规则集 (后面的覆盖前面的)"""
        merged = []
        for ruleset in rulesets:
            merged.extend(ruleset)
        return merged

    @staticmethod
    def from_config(config: dict) -> List[PermissionRule]:
        """从配置字典创建规则集"""
        rules = []
        for key, value in config.items():
            if isinstance(value, str):
                rules.append(PermissionRule(
                    permission=key,
                    pattern="*",
                    action=PermissionAction(value)
                ))
            elif isinstance(value, dict):
                for pattern, action in value.items():
                    rules.append(PermissionRule(
                        permission=key,
                        pattern=pattern,
                        action=PermissionAction(action)
                    ))
        return rules
```

### 3.2 权限使用示例

```python
# 定义默认权限
default_permissions = PermissionManager.from_config({
    "*": "allow",
    "external_directory": {
        "*": "ask",
        "/home/user/projects/*": "allow"
    },
    "bash": "ask",
    "edit": {
        "*.env": "ask",
        "*.env.*": "ask"
    }
})

# 评估权限
action = PermissionManager.evaluate(
    permission="read",
    pattern="/home/user/projects/file.py",
    ruleset=default_permissions
)
# 返回: "allow"

action = PermissionManager.evaluate(
    permission="edit",
    pattern=".env.local",
    ruleset=default_permissions
)
# 返回: "ask"
```

---

## 工具调用框架

### 4.1 工具基类 (tools/base.py)

```python
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from pydantic import BaseModel

class ToolInput(BaseModel):
    """工具输入基类"""
    pass

class ToolOutput(BaseModel):
    """工具输出"""
    success: bool
    data: Any
    error: Optional[str] = None

class Tool(ABC):
    """工具抽象基类"""

    @property
    @abstractmethod
    def name(self) -> str:
        """工具名称"""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """工具描述"""
        pass

    @property
    @abstractmethod
    def input_schema(self) -> type[ToolInput]:
        """输入 Schema"""
        pass

    @abstractmethod
    async def execute(self, input_data: ToolInput) -> ToolOutput:
        """执行工具"""
        pass

    def to_openai_function(self) -> Dict:
        """转换为 OpenAI Function Calling 格式"""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.input_schema.model_json_schema()
        }
```

### 4.2 工具注册表 (tools/registry.py)

```python
from typing import Dict, List, Optional
from .base import Tool

class ToolRegistry:
    """工具注册表"""

    def __init__(self):
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool):
        """注册工具"""
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[Tool]:
        """获取工具"""
        return self._tools.get(name)

    def list(self) -> List[Tool]:
        """列出所有工具"""
        return list(self._tools.values())

    def to_openai_functions(self) -> List[Dict]:
        """转换为 OpenAI Functions 格式"""
        return [tool.to_openai_function() for tool in self._tools.values()]

# 全局工具注册表
tool_registry = ToolRegistry()
```

### 4.3 工具示例 (tools/builtin/read.py)

```python
from pathlib import Path
from pydantic import Field
from ..base import Tool, ToolInput, ToolOutput

class ReadInput(ToolInput):
    """读取文件输入"""
    file_path: str = Field(description="文件路径")
    offset: int = Field(default=0, description="起始行号")
    limit: int = Field(default=2000, description="读取行数")

class ReadTool(Tool):
    """读取文件工具"""

    @property
    def name(self) -> str:
        return "read"

    @property
    def description(self) -> str:
        return "读取文件内容"

    @property
    def input_schema(self) -> type[ToolInput]:
        return ReadInput

    async def execute(self, input_data: ReadInput) -> ToolOutput:
        try:
            file_path = Path(input_data.file_path)

            if not file_path.exists():
                return ToolOutput(
                    success=False,
                    data=None,
                    error=f"File not found: {file_path}"
                )

            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            # 应用 offset 和 limit
            start = input_data.offset
            end = start + input_data.limit
            selected_lines = lines[start:end]

            # 添加行号
            numbered_lines = [
                f"{i+start+1:6d}→{line.rstrip()}"
                for i, line in enumerate(selected_lines)
            ]

            return ToolOutput(
                success=True,
                data="\n".join(numbered_lines)
            )

        except Exception as e:
            return ToolOutput(
                success=False,
                data=None,
                error=str(e)
            )
```

### 4.4 工具执行器 (tools/executor.py)

```python
from typing import Dict, Any
from .registry import tool_registry
from ..agent.manager import AgentManager

class ToolExecutor:
    """工具执行器 - 集成权限检查"""

    def __init__(self, agent_manager: AgentManager):
        self.agent_manager = agent_manager

    async def execute(
        self,
        agent_name: str,
        tool_name: str,
        tool_input: Dict[str, Any]
    ) -> Dict:
        """执行工具调用"""

        # 1. 获取工具
        tool = tool_registry.get(tool_name)
        if not tool:
            return {
                "success": False,
                "error": f"Tool not found: {tool_name}"
            }

        # 2. 权限检查
        pattern = self._extract_pattern(tool_name, tool_input)
        permission_action = self.agent_manager.check_permission(
            agent_name,
            tool_name,
            pattern
        )

        if permission_action == "deny":
            return {
                "success": False,
                "error": f"Permission denied for {tool_name} on {pattern}"
            }

        if permission_action == "ask":
            # TODO: 实现用户确认流程
            pass

        # 3. 执行工具
        input_obj = tool.input_schema(**tool_input)
        result = await tool.execute(input_obj)

        return result.model_dump()

    def _extract_pattern(self, tool_name: str, tool_input: Dict) -> str:
        """从工具输入提取匹配模式"""
        # 根据不同工具提取关键路径/模式
        if tool_name in ("read", "write", "edit"):
            return tool_input.get("file_path", "*")
        elif tool_name == "bash":
            return tool_input.get("command", "*")
        else:
            return "*"
```

---

## 实施路线图

### Phase 1: 基础架构 (1-2 天)

1. 创建目录结构
2. 实现数据模型 (`schema.py`)
3. 实现权限系统 (`permission.py`)
4. 编写单元测试

### Phase 2: Agent 系统 (2-3 天)

1. 实现 Markdown 加载器 (`loader.py`)
2. 实现 Agent 管理器 (`manager.py`)
3. 创建内置 Agent 定义文件
4. 集成到现有 API

### Phase 3: 工具系统 (2-3 天)

1. 实现工具基类和注册表
2. 迁移现有工具到新框架
3. 实现工具执行器
4. 集成权限检查

### Phase 4: API 集成 (1-2 天)

1. 创建 Agent API 端点
2. 更新现有 Chat/Inference API
3. 前端适配
4. 文档更新

---

## 代码示例

### 使用示例 1: 创建自定义 Agent

```markdown
<!-- agents/code-reviewer.md -->
---
name: code-reviewer
description: "专注于代码审查的 Agent"
mode: subagent
temperature: 0.2
steps: 5
permission:
  read: allow
  write: deny
  bash: deny
  grep: allow
  glob: allow
---

你是一个专业的代码审查专家。

你的职责:
- 检查代码质量和最佳实践
- 发现潜在的 bug 和安全问题
- 提供改进建议

审查时请关注:
- 代码可读性
- 性能优化
- 安全漏洞
- 测试覆盖率
```

### 使用示例 2: API 端点

```python
# api/agent.py
from fastapi import APIRouter, HTTPException
from ..agent.manager import AgentManager

router = APIRouter(prefix="/agent", tags=["agent"])
agent_manager = AgentManager()

@router.get("/list")
async def list_agents(include_hidden: bool = False):
    """列出所有 Agent"""
    agents = agent_manager.list(include_hidden=include_hidden)
    return [agent.model_dump() for agent in agents]

@router.get("/{name}")
async def get_agent(name: str):
    """获取 Agent 详情"""
    agent = agent_manager.get(name)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent.model_dump()

@router.get("/default")
async def get_default_agent():
    """获取默认 Agent"""
    return {"name": agent_manager.get_default_agent()}

@router.post("/check-permission")
async def check_permission(
    agent_name: str,
    permission: str,
    pattern: str
):
    """检查权限"""
    action = agent_manager.check_permission(agent_name, permission, pattern)
    return {"action": action}
```

### 使用示例 3: 在 Chat API 中使用

```python
# api/chat.py (修改现有代码)
from ..agent.manager import AgentManager
from ..tools.executor import ToolExecutor

agent_manager = AgentManager()
tool_executor = ToolExecutor(agent_manager)

@router.post("/chat")
async def chat(
    message: str,
    agent_name: str = "build"  # 新增参数
):
    # 获取 Agent 配置
    agent = agent_manager.get(agent_name)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # 使用 Agent 的系统提示词
    system_prompt = agent.prompt or "You are a helpful assistant."

    # 调用 LLM (使用 Agent 的模型配置)
    response = await call_llm(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message}
        ],
        temperature=agent.temperature,
        top_p=agent.top_p
    )

    # 如果有工具调用,通过 ToolExecutor 执行
    if response.tool_calls:
        for tool_call in response.tool_calls:
            result = await tool_executor.execute(
                agent_name=agent_name,
                tool_name=tool_call.name,
                tool_input=tool_call.arguments
            )
            # 处理结果...

    return response
```

---

## 总结

这个设计方案提供了:

1. **完整的 Agent 定义系统** - 支持 Markdown 配置
2. **细粒度权限控制** - 基于规则的权限评估
3. **可扩展的工具框架** - 统一的工具注册和执行
4. **Python 原生实现** - 使用 Pydantic 替代 Effect-TS
5. **渐进式迁移路径** - 可以逐步集成到现有系统

下一步你可以:
- 按照路线图逐步实施
- 根据实际需求调整设计
- 先实现核心功能,再扩展高级特性
