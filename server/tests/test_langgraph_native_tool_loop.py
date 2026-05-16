from __future__ import annotations

from copy import deepcopy

from langchain_core.messages import AIMessage

from agent_runtime_legacy.langgraph.nodes import LangGraphWorkflowRuntime


class FakeRepository:
    def __init__(self):
        self.project = {
            "id": "wf_1",
            "goal": "inspect project",
            "template_id": "tpl_1",
            "provider": "glm",
            "model": "glm-4",
            "status": "created",
            "current_stage": "",
            "metadata": {},
            "tasks": [],
        }
        self.tool_calls = []
        self.events = []
        self.artifacts = []
        self.actions = {}

    def get_project(self, workflow_id):
        assert workflow_id == "wf_1"
        return deepcopy(self.project)

    def update_project(self, workflow_id, **fields):
        assert workflow_id == "wf_1"
        self.project.update(fields)

    def create_task(self, **kwargs):
        task = {
            "id": f"task_{len(self.project['tasks']) + 1}",
            "workflow_id": kwargs["project_id"],
            "role": kwargs["role"],
            "title": kwargs["title"],
            "description": kwargs["description"],
            "status": kwargs["status"],
            "input_data": kwargs["input_data"],
            "requires_approval": kwargs["requires_approval"],
            "step_key": kwargs["step_key"],
            "sort_order": kwargs["sort_order"],
            "output": None,
        }
        self.project["tasks"].append(task)
        return deepcopy(task)

    def get_task(self, task_id):
        for task in self.project["tasks"]:
            if task["id"] == task_id:
                return deepcopy(task)
        return None

    def update_task(self, task_id, **fields):
        for task in self.project["tasks"]:
            if task["id"] == task_id:
                task.update(fields)
                return
        raise AssertionError(f"unknown task: {task_id}")

    def add_event(self, workflow_id, step_id, event_type, actor, message, payload=None):
        self.events.append({"workflow_id": workflow_id, "step_id": step_id, "event_type": event_type, "actor": actor, "message": message, "payload": payload or {}})

    def add_tool_call(self, **kwargs):
        call = {"id": f"call_{len(self.tool_calls) + 1}", **kwargs}
        self.tool_calls.append(call)
        return deepcopy(call)

    def update_tool_call(self, call_id, **fields):
        for call in self.tool_calls:
            if call["id"] == call_id:
                call.update(fields)
                return deepcopy(call)
        raise AssertionError(f"unknown tool call: {call_id}")

    def get_action_proposal(self, action_id):
        return self.actions.get(action_id)

    def add_artifact(self, workflow_id, step_id, artifact_type, title, content):
        self.artifacts.append({"workflow_id": workflow_id, "step_id": step_id, "artifact_type": artifact_type, "title": title, "content": content})


class FakeExecutor:
    def execute(self, request, **kwargs):
        payload = {"files": ["a.py", "b.py"]} if request.tool == "list_files" else request.arguments
        return type(
            "Result",
            (),
            {
                "tool": request.tool,
                "status": "completed",
                "summary": f"{request.tool} done",
                "payload": payload,
                "error": None,
                "model_dump": lambda self: {
                    "tool": request.tool,
                    "status": "completed",
                    "summary": f"{request.tool} done",
                    "payload": payload,
                    "error": None,
                },
            },
        )()


class FakeRunner:
    def __init__(self):
        self.executor = FakeExecutor()

    def _build_messages(self, agent_id, context, step_input):
        return [{"role": "system", "content": "You are a workflow agent."}, {"role": "user", "content": step_input["step"]["title"]}]


class FakeModel:
    def __init__(self):
        self.calls = 0

    def bind_tools(self, tools):
        self.tools = tools
        return self

    async def ainvoke(self, messages):
        self.calls += 1
        if self.calls == 1:
            return AIMessage(content="", tool_calls=[{"name": "list_files", "args": {"pattern": "**/*"}, "id": "tool_1"}])
        return AIMessage(
            content='{"summary":"done","tasks":[],"risks":[],"artifacts":[],"next_action":"","requires_approval":false}'
        )


async def test_native_tool_loop_runs_read_tool_and_completes(monkeypatch):
    repository = FakeRepository()
    runtime = LangGraphWorkflowRuntime(repository=repository, runner=FakeRunner(), context_builder=None, memory_curator=None, action_service=object())
    fake_model = FakeModel()
    monkeypatch.setattr("agent_runtime_legacy.langgraph.nodes.get_chat_model", lambda context: fake_model)

    state = {
        "workflow_id": "wf_1",
        "step_index": 0,
        "messages": [],
        "metadata": {
            "workflow_steps": [
                {
                    "step_key": "plan",
                    "agent_id": "planner",
                    "title": "Plan work",
                    "description": "Plan",
                    "artifact_type": "plan",
                    "artifact_title": "Plan work",
                    "requires_approval": False,
                    "sort_order": 0,
                }
            ],
            "workflow_agents": {"planner": {"id": "planner", "system_prompt": "Plan carefully.", "output_requirements": ""}},
        },
    }

    state.update(await runtime.bootstrap_node(state))
    model_update = await runtime.model_call_node(state)
    state.update(model_update)
    assert state["pending_tool_calls"][0]["name"] == "list_files"

    tool_update = await runtime.tool_exec_node(state)
    state["messages"] = list(state["messages"]) + list(tool_update["messages"])
    state.update({k: v for k, v in tool_update.items() if k != "messages"})
    assert repository.tool_calls[0]["tool_name"] == "list_files"

    second_model_update = await runtime.model_call_node(state)
    state["messages"] = list(state["messages"]) + [second_model_update["messages"][0]]
    state.update({k: v for k, v in second_model_update.items() if k != "messages"})
    review_update = await runtime.review_gate_node(state)

    assert review_update["execution_state"] == "completed"
    assert repository.project["status"] == "completed"
    assert repository.artifacts[0]["artifact_type"] == "plan"

