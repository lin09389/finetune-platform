# OpenCode Agent 系统整合计划

## 项目现状分析

### 已有架构

你的 finetune-platform 项目已经具备相当完整的 Agent 基础设施：

#### 1. Agent Runtime 系统 (`server/agent_runtime/`)
- **AgentRuntimeEngine** - 工作流编排引擎
- **AgentToolExecutor** - 工具执行器（list_files, search_code, read_file, propose_patch 等）
- **WorkflowDefinition** - 基于模板的工作流定义
- **ContextBuilder** - 上下文构建器
- **MemoryCurator** - 记忆管理器
- **ActionService** - 动作提议和执行

#### 2. Gateway 系统 (`server/gateway/`)
- **GatewayServer** - WebSocket 统一入口
- **MessageRouter** - 消息路由（Binding Router 最具体匹配）
- **AgentIsolation** - Agent 隔离管理（workspace/session）
- **DeviceAuth** - 设备认证
- **CrossAgent** - 跨 Agent 通信

#### 3. Chat Agent (`server/chat_agent/`)
- 意图识别
- 对话服务
- 仓库管理

#### 4. 其他模块
- **RAG** - 向量检索
- **Memory** - 三层记忆系统
- **Skills** - 技能系统
- **Context** - 项目上下文理解
- **Security** - 安全沙箱

### 现有架构的特点

✅ **优势**：
- 完整的工作流引擎（多步骤 Agent 协作）
- Gateway 统一入口（WebSocket + 消息路由）
- Agent 隔离机制（workspace/session 管理）
- 工具系统已实现（文件操作、代码搜索）
- 动作审批流程（propose → approve → execute）

❌ **缺失**：
- **声明式 Agent 定义**：当前 Agent 硬编码在 templates.py 中
- **细粒度权限系统**：缺少 allow/deny/ask 规则引擎
- **Markdown Agent 配置**：无法通过文件定义 Agent
- **Agent 模式分类**：无 primary/subagent/all 概念
- **工具权限检查**：工具执行前无权限验证

---

## OpenCode 核心价值

从 OpenCode 借鉴的关键设计：

### 1. 声明式 Agent 定义
```markdown
---
name: code-reviewer
mode: subagent
permission:
  read: allow
  write: deny
  bash: deny
---
你是代码审查专家...
```

### 2. 权限系统
```python
# 规则优先级：最后定义的规则优先
rules = [
    {"permission": "read", "pattern": "*", "action": "allow"},
    {"permission": "edit", "pattern": "*.env", "action": "ask"},
    {"permission": "bash", "pattern": "*", "action": "deny"},
]
```

### 3. Agent 模式
- **primary**: 用户直接选择的主 Agent
- **subagent**: 被其他 Agent 调用（如 @explore）
- **all**: 两者皆可

### 4. 工具抽象
```python
class Tool(ABC):
    @abstractmethod
    async def execute(self, input_data: ToolInput) -> ToolOutput:
        pass
```

---

## 整合策略

### 核心原则

**不推倒重来，而是增强现有系统**

1. **保留现有架构** - AgentRuntimeEngine、Gateway、WorkflowDefinition 继续使用
2. **增加声明式层** - 在现有基础上添加 Markdown Agent 定义能力
3. **注入权限系统** - 在 AgentToolExecutor 中集成权限检查
4. **扩展工具注册** - 将现有工具迁移到统一注册表

---

## 实施计划

### Phase 1: 权限系统基础 (2-3 天)

#### 目标
在现有系统中注入细粒度权限控制

#### 任务

**1.1 创建权限模块** (`server/agent_runtime/permission.py`)
```python
class PermissionRule(BaseModel):
    permission: str  # "read", "write", "bash", "propose_patch"
    pattern: str     # 文件路径模式或 "*"
    action: Literal["allow", "deny", "ask"]

class PermissionManager:
    @staticmethod
    def evaluate(permission: str, pattern: str, ruleset: list[PermissionRule]) -> str:
        """评估权限 - 返回 allow/deny/ask"""
        # 从后往前匹配（最后定义的优先）
        for rule in reversed(ruleset):
            if fnmatch(permission, rule.permission) and fnmatch(pattern, rule.pattern):
                return rule.action
        return "ask"  # 默认策略
```

**1.2 扩展 AgentToolExecutor**
```python
class AgentToolExecutor:
    def __init__(self, ..., permission_manager: PermissionManager):
        self.permission_manager = permission_manager

    def execute(self, request: AgentToolRequest, *, agent_permission: list[PermissionRule], ...):
        # 权限检查
        pattern = self._extract_pattern(request.tool, request.arguments)
        action = self.permission_manager.evaluate(request.tool, pattern, agent_permission)

        if action == "deny":
            return AgentToolResult(status="failed", error="Permission denied")

        if action == "ask":
            # TODO: 集成到审批流程
            pass

        # 执行工具...
```

**1.3 集成到 WorkflowDefinition**
```python
@dataclass
class StepDefinition:
    key: str
    agent_id: str
    title: str
    permission: list[PermissionRule] = field(default_factory=list)  # 新增
```

#### 验收标准
- [ ] PermissionManager 单元测试通过
- [ ] AgentToolExecutor 集成权限检查
- [ ] 可以通过代码定义权限规则

---

### Phase 2: Agent 定义系统 (3-4 天)

#### 目标
支持 Markdown 文件定义 Agent

#### 任务

**2.1 创建 Agent Schema** (`server/agent_runtime/agent_schema.py`)
```python
class AgentMode(str, Enum):
    PRIMARY = "primary"
    SUBAGENT = "subagent"
    ALL = "all"

class AgentDefinition(BaseModel):
    name: str
    description: str = ""
    mode: AgentMode = AgentMode.ALL
    system_prompt: str
    permission: list[PermissionRule] = Field(default_factory=list)

    # 模型配置
    provider: str = "minimax"
    model: str | None = None
    temperature: float = 0.7

    # 能力配置
    tools: list[str] = Field(default_factory=list)  # 允许的工具列表
    max_iterations: int = 10

    # 元数据
    native: bool = False  # 是否内置
    hidden: bool = False  # 是否在 UI 隐藏
```

**2.2 当前方案：Agent Manifest v2 Registry** (`server/agent_session/agent_registry.py`)

> 已废弃：当前实现不再加载 Markdown Agent。请使用 `server/agent_session/agents/*.agent.yaml` 的 Agent Manifest v2，并由 `server/agent_session/agent_registry.py` 解析。
```python
class AgentRegistry:
    def _load_yaml_agent(self, path: Path) -> AgentDefinition:
        """解析 Agent Manifest v2 YAML"""
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        manifest = AgentManifestV2(**raw)
        return self._compile_manifest(manifest)
```

**2.3 当前 Agent 管理入口** (`server/agent_session/agent_registry.py`)
```python
class AgentManager:
    def __init__(self):
        self._registry = AgentRegistry()

    def load_user_agents(self, agents_dir: Path):
        """从目录加载用户自定义 Agent Manifest v2 YAML"""
        self._registry = AgentRegistry(agents_dir)

    def get(self, name: str) -> AgentDefinition | None:
        return self._registry.get(name)

    def list_primary(self) -> list[AgentDefinition]:
        return self._registry.list_primary_agents()
```

**2.4 创建内置 Agent 定义**

`server/agent_session/agents/developer.agent.yaml`:
```yaml
schema_version: 2
id: developer
name: Developer
description: 软件开发 Agent，负责编写和修改代码
mode: primary
Runtime:
  default_provider: minimax
  max_iterations: 8
Tools:
  allowed:
    - read_file
    - grep
    - edit_file
    - execute
SystemPrompt:
  identity: 你是一个专业的软件开发工程师。
  responsibilities:
    - 理解需求并编写高质量代码。
    - 遵循项目现有的代码风格。
    - 提出并验证代码修改。
OutputSchema:
  format: structured_markdown
  required_sections:
    - summary
    - changed_files
    - verification
```

`server/agent_session/agents/reviewer.agent.yaml`:
```yaml
schema_version: 2
id: reviewer
name: Reviewer
description: 代码审查 Agent，只读权限
mode: subagent
Runtime:
  default_provider: minimax
  max_iterations: 4
Tools:
  allowed:
    - read_file
    - grep
SystemPrompt:
  identity: 你是一个代码审查专家。
  responsibilities:
    - 检查代码质量和最佳实践。
    - 发现潜在的 bug 和安全问题。
    - 提供改进建议，但不能直接修改代码。
OutputSchema:
  format: structured_markdown
  required_sections:
    - conclusion
    - risks
    - verification
```

**2.5 集成到现有系统**

修改 `server/agent_runtime/engine.py`:
```python
class AgentRuntimeEngine:
    def __init__(self, ..., agent_manager: AgentManager):
        self.agent_manager = agent_manager
        ...

    async def _run_step(self, step: StepDefinition, ...):
        # 获取 Agent 定义
        agent_def = self.agent_manager.get(step.agent_id)
        if not agent_def:
            raise ValueError(f"Agent {step.agent_id} not found")

        # 使用 Agent 的系统提示词和权限
        system_prompt = agent_def.system_prompt
        permission = agent_def.permission

        # 执行工具时传入权限
        tool_result = self.tool_executor.execute(
            tool_request,
            agent_permission=permission,
            ...
        )
```

#### 验收标准
- [ ] 可以从 Markdown 加载 Agent 定义
- [ ] 内置 developer 和 reviewer Agent 可用
- [ ] AgentManager 集成到 AgentRuntimeEngine
- [ ] 工具执行时使用 Agent 的权限规则

---

### Phase 3: 工具系统重构 (2-3 天)

#### 目标
统一工具注册和执行机制

#### 任务

**3.1 创建工具基类** (`server/agent_runtime/tool_base.py`)
```python
class ToolInput(BaseModel):
    """工具输入基类"""
    pass

class ToolOutput(BaseModel):
    """工具输出"""
    success: bool
    data: Any
    error: str | None = None

class Tool(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        pass

    @abstractmethod
    async def execute(self, input_data: ToolInput) -> ToolOutput:
        pass
```

**3.2 迁移现有工具**

将 `AgentToolExecutor` 中的工具逻辑提取为独立工具类：

`server/agent_runtime/tools/list_files.py`:
```python
class ListFilesInput(ToolInput):
    path_glob: str = "**/*"
    limit: int = 200

class ListFilesTool(Tool):
    @property
    def name(self) -> str:
        return "list_files"

    @property
    def description(self) -> str:
        return "列出项目中的文件"

    async def execute(self, input_data: ListFilesInput) -> ToolOutput:
        # 原 _list_files 逻辑
        ...
```

**3.3 创建工具注册表** (`server/agent_runtime/tool_registry.py`)
```python
class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool):
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def list(self) -> list[Tool]:
        return list(self._tools.values())

# 全局注册表
tool_registry = ToolRegistry()

# 注册内置工具
tool_registry.register(ListFilesTool())
tool_registry.register(SearchCodeTool())
tool_registry.register(ReadFileTool())
tool_registry.register(ProposePatchTool())
```

**3.4 简化 AgentToolExecutor**
```python
class AgentToolExecutor:
    def __init__(self, tool_registry: ToolRegistry, permission_manager: PermissionManager, ...):
        self.tool_registry = tool_registry
        self.permission_manager = permission_manager

    def execute(self, request: AgentToolRequest, *, agent_permission: list[PermissionRule], ...):
        # 1. 获取工具
        tool = self.tool_registry.get(request.tool)
        if not tool:
            return AgentToolResult(status="failed", error="Tool not found")

        # 2. 权限检查
        pattern = self._extract_pattern(request.tool, request.arguments)
        action = self.permission_manager.evaluate(request.tool, pattern, agent_permission)

        if action == "deny":
            return AgentToolResult(status="failed", error="Permission denied")

        # 3. 执行工具
        input_obj = tool.input_schema(**request.arguments)
        result = await tool.execute(input_obj)

        return AgentToolResult(
            tool=request.tool,
            status="completed" if result.success else "failed",
            payload=result.data,
            error=result.error
        )
```

#### 验收标准
- [ ] 所有现有工具迁移到新架构
- [ ] ToolRegistry 正常工作
- [ ] AgentToolExecutor 简化完成
- [ ] 工具执行流程保持不变

---

### Phase 4: API 和 UI 集成 (2-3 天)

#### 目标
暴露 Agent 管理 API，前端支持 Agent 选择

#### 任务

**4.1 创建 Agent API** (`server/api/agent.py`)
```python
from fastapi import APIRouter, HTTPException
from agent_runtime.agent_manager import agent_manager

router = APIRouter(prefix="/agent", tags=["agent"])

@router.get("/list")
async def list_agents(mode: str | None = None):
    """列出所有 Agent"""
    if mode == "primary":
        agents = agent_manager.list_primary()
    else:
        agents = agent_manager.list()

    return [
        {
            "name": a.name,
            "description": a.description,
            "mode": a.mode,
            "provider": a.provider,
            "tools": a.tools,
            "native": a.native,
        }
        for a in agents
    ]

@router.get("/{name}")
async def get_agent(name: str):
    """获取 Agent 详情"""
    agent = agent_manager.get(name)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent.model_dump()

@router.post("/reload")
async def reload_agents():
    """重新加载用户自定义 Agent"""
    agents_dir = Path("agents")
    if agents_dir.exists():
        agent_manager.load_user_agents(agents_dir)
    return {"message": "Agents reloaded"}
```

**4.2 修改 Workflow API**

在 `server/api/digital_team.py` 中添加 Agent 选择：
```python
@router.post("/projects")
async def create_project(
    title: str,
    goal: str,
    template_id: str = "software_delivery",
    agent_id: str = "developer",  # 新增：指定使用的 Agent
    ...
):
    # 验证 Agent 存在
    agent = agent_manager.get(agent_id)
    if not agent:
        raise HTTPException(status_code=400, detail="Invalid agent_id")

    # 创建项目时记录 agent_id
    project = repository.create_project(
        title=title,
        goal=goal,
        template_id=template_id,
        metadata={"agent_id": agent_id},
        ...
    )
```

**4.3 前端集成**

修改 `client/src/pages/Training.tsx`（或创建新的 Agent 管理页面）：
```typescript
// 获取 Agent 列表
const [agents, setAgents] = useState([]);

useEffect(() => {
  fetch('http://127.0.0.1:8000/agent/list?mode=primary')
    .then(res => res.json())
    .then(data => setAgents(data));
}, []);

// Agent 选择器
<Select
  placeholder="选择 Agent"
  value={selectedAgent}
  onChange={setSelectedAgent}
>
  {agents.map(agent => (
    <Select.Option key={agent.name} value={agent.name}>
      {agent.description}
    </Select.Option>
  ))}
</Select>
```

**4.4 创建 Agent 管理页面**

`client/src/pages/AgentManager.tsx`:
```typescript
export default function AgentManager() {
  const [agents, setAgents] = useState([]);

  // 列表展示
  // 查看详情
  // 重新加载按钮

  return (
    <div>
      <h2>Agent 管理</h2>
      <Button onClick={reloadAgents}>重新加载</Button>
      <Table dataSource={agents} columns={columns} />
    </div>
  );
}
```

#### 验收标准
- [ ] Agent API 端点正常工作
- [ ] 前端可以列出和选择 Agent
- [ ] 创建 Workflow 时可以指定 Agent
- [ ] Agent 管理页面可用

---

### Phase 5: 高级特性 (可选，3-4 天)

#### 5.1 Subagent 调用

支持 Agent 之间的调用（如 @reviewer）：

```python
class SubagentTool(Tool):
    @property
    def name(self) -> str:
        return "call_subagent"

    async def execute(self, input_data: SubagentInput) -> ToolOutput:
        # 调用另一个 Agent
        subagent = agent_manager.get(input_data.agent_name)
        if subagent.mode not in (AgentMode.SUBAGENT, AgentMode.ALL):
            return ToolOutput(success=False, error="Not a subagent")

        # 执行 subagent...
```

#### 5.2 权限审批流程

集成到现有的 Action 审批机制：

```python
if action == "ask":
    # 创建审批动作
    approval_action = repository.add_action_proposal(
        workflow_id=workflow_id,
        step_id=step_id,
        action_type="permission_request",
        title=f"请求权限: {request.tool}",
        description=f"Agent 请求执行 {request.tool} on {pattern}",
        payload={"tool": request.tool, "pattern": pattern}
    )

    # 等待审批...
```

#### 5.3 Agent 热重载

监听 `agents/` 目录变化，自动重新加载：

```python
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class AgentFileHandler(FileSystemEventHandler):
    def on_modified(self, event):
        if event.src_path.endswith('.md'):
            agent_manager.reload_agent(event.src_path)
```

---

## 目录结构（整合后）

```
server/
├── agent_runtime/              # Agent 运行时（增强）
│   ├── __init__.py
│   ├── agent_schema.py        # 新增：Agent 数据模型
│   ├── agent_loader.py        # 新增：Markdown 加载器
│   ├── agent_manager.py       # 新增：Agent 管理器
│   ├── permission.py          # 新增：权限系统
│   ├── tool_base.py           # 新增：工具基类
│   ├── tool_registry.py       # 新增：工具注册表
│   ├── tools.py               # 重构：简化为工具执行器
│   ├── engine.py              # 修改：集成 AgentManager
│   ├── agents/                # 新增：内置 Agent 定义
│   │   ├── developer.md
│   │   ├── reviewer.md
│   │   └── explorer.md
│   └── tools/                 # 新增：独立工具模块
│       ├── list_files.py
│       ├── search_code.py
│       ├── read_file.py
│       └── propose_patch.py
├── api/
│   ├── agent.py               # 新增：Agent API
│   └── ...
├── gateway/                    # 保持不变
├── chat_agent/                 # 保持不变
└── ...

agents/                         # 新增：用户自定义 Agent
├── my_custom_agent.md
└── ...
```

---

## 迁移路径

### 向后兼容

1. **保留现有 templates.py** - 作为 fallback
2. **渐进式迁移** - 先支持 Markdown Agent，再逐步废弃硬编码
3. **API 兼容** - 现有 API 继续工作，新增 Agent 选择参数

### 数据迁移

无需数据迁移，因为：
- Agent 定义是代码层面的
- 现有 Workflow 数据结构不变
- 只是增加了 `agent_id` 字段

---

## 测试计划

### 单元测试

```python
# tests/test_permission.py
def test_permission_evaluate():
    rules = [
        PermissionRule(permission="read", pattern="*", action="allow"),
        PermissionRule(permission="read", pattern="*.env", action="ask"),
    ]
    assert PermissionManager.evaluate("read", "file.py", rules) == "allow"
    assert PermissionManager.evaluate("read", ".env", rules) == "ask"

# tests/test_agent_registry.py
def test_load_manifest_v2_agent():
    agent = AgentRegistry(Path("agents")).require("developer")
    assert agent.id == "developer"
    assert agent.mode == "primary"
```

### 集成测试

```python
# tests/test_agent_workflow.py
async def test_workflow_with_custom_agent():
    # 创建自定义 Agent
    agent_manager.load_user_agents(Path("test_agents"))

    # 创建 Workflow
    project = await engine.start(
        project={"agent_id": "test_agent", ...},
        project_context="..."
    )

    # 验证使用了正确的 Agent
    assert project["metadata"]["agent_id"] == "test_agent"
```

---

## 风险和缓解

### 风险 1: 性能影响
- **风险**: 权限检查增加延迟
- **缓解**: 权限规则缓存，使用高效的匹配算法

### 风险 2: 兼容性问题
- **风险**: 现有 Workflow 可能不兼容
- **缓解**: 保留 fallback 机制，渐进式迁移

### 风险 3: 学习曲线
- **风险**: 用户需要学习 Markdown Agent 语法
- **缓解**: 提供详细文档和示例，UI 提供模板

---

## 成功指标

- [ ] 可以通过 Markdown 定义 Agent
- [ ] 权限系统正常工作（allow/deny/ask）
- [ ] 工具执行前进行权限检查
- [ ] 前端可以选择和管理 Agent
- [ ] 现有功能不受影响
- [ ] 单元测试覆盖率 > 80%
- [ ] 集成测试通过

---

## 时间估算

| Phase | 任务 | 预计时间 |
|-------|------|---------|
| Phase 1 | 权限系统基础 | 2-3 天 |
| Phase 2 | Agent 定义系统 | 3-4 天 |
| Phase 3 | 工具系统重构 | 2-3 天 |
| Phase 4 | API 和 UI 集成 | 2-3 天 |
| Phase 5 | 高级特性（可选） | 3-4 天 |
| **总计** | **核心功能** | **9-13 天** |
| **总计** | **含高级特性** | **12-17 天** |

---

## 下一步行动

1. **Review 本计划** - 确认方向和优先级
2. **创建 Git 分支** - `feature/opencode-integration`
3. **Phase 1 启动** - 实现权限系统
4. **每日 Standup** - 跟踪进度和阻塞
5. **Code Review** - 每个 Phase 完成后 Review

---

## 参考资料

- OpenCode 源码: `C:\Users\JHJ\opencode`
- 现有架构文档: `C:\Users\JHJ\Desktop\finetune-platform\CLAUDE.md`
- Gateway 文档: `C:\Users\JHJ\Desktop\finetune-platform\server\gateway\README.md`
