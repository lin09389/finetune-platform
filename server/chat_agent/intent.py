from __future__ import annotations


class ChatAgentIntentClassifier:
    """Small deterministic classifier for routing chat messages into agent work."""

    agent_keywords = (
        "修改",
        "新增",
        "实现",
        "修复",
        "重构",
        "优化代码",
        "给当前项目",
        "代码里",
        "页面",
        "接口",
        "组件",
        "后端",
        "前端",
        "跑测试",
        "运行测试",
        "typecheck",
        "pytest",
        "npm run",
        "让agent做",
        "自动处理",
        "帮我改",
        "补丁",
        "执行",
    )
    discussion_only_keywords = ("不要执行", "只讨论", "只分析", "解释一下", "什么是", "为什么")

    def classify(self, content: str, force_agent: bool = False) -> tuple[bool, str]:
        text = content.strip().lower()
        if force_agent:
            return True, "manual_agent"
        if not text:
            return False, "empty"
        if any(keyword in text for keyword in self.discussion_only_keywords):
            return False, "chat"
        if any(keyword in text for keyword in self.agent_keywords):
            return True, "agent_work"
        return False, "chat"
