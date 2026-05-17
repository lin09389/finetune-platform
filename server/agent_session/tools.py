from __future__ import annotations

from typing import Any

from .action_tools import ActionToolsMixin
from .browser_tools import BrowserToolsMixin
from .dev_server_tools import DEV_SERVER_PROCESSES, DevServerToolsMixin
from .file_tools import FileToolsMixin
from .http_tools import HttpToolsMixin
from .log_tools import LogToolsMixin
from .page_parser import LocalPageParser
from .symbol_index_tools import AST_GREP_SYMBOL_RE, SymbolIndexToolsMixin
from .test_tools import TestToolsMixin
from .tool_base import ToolBaseMixin
from .tool_types import ToolDefinition, ToolResult
from .git_tools import GitToolsMixin


__all__ = [
    "AgentToolRegistry",
    "ToolResult",
    "ToolDefinition",
    "LocalPageParser",
    "DEV_SERVER_PROCESSES",
    "AST_GREP_SYMBOL_RE",
]


class AgentToolRegistry(
    ToolBaseMixin,
    FileToolsMixin,
    SymbolIndexToolsMixin,
    ActionToolsMixin,
    DevServerToolsMixin,
    LogToolsMixin,
    TestToolsMixin,
    GitToolsMixin,
    HttpToolsMixin,
    BrowserToolsMixin,
):
    def __init__(self, repository: Any | None = None):
        self._tools: dict[str, ToolDefinition] = {}
        self.repository = repository
        self.register_defaults()

    def register(self, tool: ToolDefinition) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolDefinition | None:
        return self._tools.get(name)

    def list(self) -> list[ToolDefinition]:
        return list(self._tools.values())

    def register_defaults(self) -> None:
        self.register(ToolDefinition("read", "读取文件", "read", {"path": "string"}, self._read))
        self.register(ToolDefinition("search", "搜索代码", "read", {"query": "string"}, self._search))
        self.register(ToolDefinition("find_symbol", "查找符号定义", "read", {"symbol": "string"}, self._find_symbol))
        self.register(ToolDefinition("find_references", "查找符号引用", "read", {"symbol": "string"}, self._find_references))
        self.register(ToolDefinition("glob", "列出文件", "read", {"path_glob": "string"}, self._glob))
        self.register(ToolDefinition("collect_context", "批量收集上下文", "read", {}, self._collect_context))
        self.register(ToolDefinition("detect_project_commands", "识别验证命令", "read", {}, self._detect_project_commands))
        self.register(ToolDefinition("git_status", "读取 Git 状态", "read", {}, self._git_status))
        self.register(ToolDefinition("git_diff", "读取 Git 差异", "read", {}, self._git_diff))
        self.register(ToolDefinition("list_changed_files", "列出变更文件", "read", {}, self._list_changed_files))
        self.register(ToolDefinition("read_logs", "读取日志", "read", {}, self._read_logs))
        self.register(ToolDefinition("http_probe", "探测本地 HTTP 服务", "read", {"url": "string"}, self._http_probe))
        self.register(ToolDefinition("probe_json_endpoint", "探测本地 JSON 接口", "read", {"url": "string"}, self._probe_json_endpoint))
        self.register(ToolDefinition("read_local_page", "读取本地页面摘要", "read", {"url": "string"}, self._read_local_page))
        self.register(ToolDefinition("browser_validate_page", "使用浏览器验证本地页面", "read", {"url": "string"}, self._browser_validate_page))
        self.register(ToolDefinition("capture_network_errors", "捕获本地页面网络错误", "read", {"url": "string"}, self._capture_network_errors))
        self.register(ToolDefinition("browser_click", "使用浏览器点击本地页面元素", "read", {"url": "string", "selector": "string"}, self._browser_click))
        self.register(ToolDefinition("browser_fill", "使用浏览器填写本地页面表单", "read", {"url": "string", "selector": "string", "value": "string"}, self._browser_fill))
        self.register(ToolDefinition("browser_wait_for", "等待本地页面元素或文本出现", "read", {"url": "string"}, self._browser_wait_for))
        self.register(ToolDefinition("run_targeted_test", "精准运行测试目标", "command", {}, self._run_targeted_test))
        self.register(ToolDefinition("summarize_test_results", "汇总最近测试结果", "read", {}, self._summarize_test_results))
        self.register(ToolDefinition("collect_test_failures", "汇总最近测试失败信息", "read", {}, self._collect_test_failures))
        self.register(ToolDefinition("run_dev_server", "启动开发服务器", "command", {}, self._run_dev_server))
        self.register(ToolDefinition("stop_dev_server", "停止开发服务器", "command", {}, self._stop_dev_server))
        self.register(ToolDefinition("get_server_status", "查看开发服务器状态", "read", {}, self._get_server_status))
        self.register(ToolDefinition("patch", "提出或应用补丁", "patch", {}, self._patch))
        self.register(ToolDefinition("bash_command", "运行白名单命令", "command", {}, self._command))
        self.register(ToolDefinition("read_execution", "读取执行结果", "read", {}, self._read_execution))
        self.register(ToolDefinition("finalize", "完成总结", "read", {}, self._finalize))

    def _finalize(self, args: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        content = str(args.get("summary") or args.get("content") or "任务已完成。")
        return ToolResult("completed", content, self._normalize_tool_payload({"summary": content, **args}))

