"""Context window management for agent tool loops.

Provides message compression and token estimation to prevent the
conversation history from exceeding the model's context window.
"""

from __future__ import annotations

import json
import re
from typing import Any


# Rough token estimation ratios
_CJK_CHARS_PER_TOKEN = 1.5
_LATIN_CHARS_PER_TOKEN = 4.0
_CJK_RANGE = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf\u2e80-\u2eff\u3000-\u303f\uff00-\uffef]")


def _estimate_tokens_for_text(text: str) -> int:
    """Estimate token count for mixed CJK/Latin text."""
    if not text:
        return 0
    cjk_count = len(_CJK_RANGE.findall(text))
    latin_count = len(text) - cjk_count
    return int(cjk_count / _CJK_CHARS_PER_TOKEN + latin_count / _LATIN_CHARS_PER_TOKEN)


def estimate_tokens(messages: list[dict[str, str]]) -> int:
    """Estimate total token count for a list of chat messages."""
    total = 0
    for message in messages:
        # ~4 tokens per message for role/framing overhead
        total += 4
        total += _estimate_tokens_for_text(message.get("content", ""))
    return total


def _summarize_observation(content: str, max_chars: int = 600) -> str:
    """Compress a tool observation message into a shorter summary."""
    try:
        parsed = json.loads(content.split("\n", 1)[-1]) if "\n" in content else json.loads(content)
    except (json.JSONDecodeError, ValueError):
        parsed = None

    if isinstance(parsed, dict):
        tool = parsed.get("tool", "")
        status = parsed.get("status", "")
        summary = parsed.get("summary", "")
        error = parsed.get("error", "")
        parts = [f"tool={tool}", f"status={status}"]
        if summary:
            parts.append(f"summary={summary[:200]}")
        if error:
            parts.append(f"error={error[:200]}")
        result = ", ".join(parts)
        return result[:max_chars]

    # Fallback: truncate raw text
    if len(content) <= max_chars:
        return content
    return content[:max_chars - 20] + "\n...[已压缩]"


class ToolLoopContextManager:
    """Manages the message list inside a tool loop to prevent context overflow.

    When messages exceed ``summary_threshold``, early tool-observation pairs
    are compressed into brief summaries.  An optional ``token_budget`` can
    trigger forced compression when the estimated token count approaches
    the model's context window.
    """

    def __init__(
        self,
        max_messages: int = 24,
        summary_threshold: int = 16,
        token_budget: int | None = None,
        budget_ratio: float = 0.85,
    ):
        self.max_messages = max_messages
        self.summary_threshold = summary_threshold
        self.token_budget = token_budget
        self.budget_ratio = budget_ratio

    def should_compress(self, messages: list[dict[str, str]]) -> bool:
        """Return True if the message list needs compression."""
        if len(messages) >= self.summary_threshold:
            return True
        if self.token_budget and estimate_tokens(messages) >= int(self.token_budget * self.budget_ratio):
            return True
        return False

    def compress(self, messages: list[dict[str, str]]) -> list[dict[str, str]]:
        """Compress older tool-call/observation pairs into summaries.

        Preserves:
        - The system message (index 0)
        - The initial user message (index 1)
        - The most recent ``keep_recent`` assistant/user pairs
        - Compresses everything in between into a single summary block.
        """
        if not self.should_compress(messages):
            return messages

        keep_recent = 6  # keep last 3 assistant+user pairs
        if len(messages) <= 2 + keep_recent:
            return messages

        head = messages[:2]  # system + initial user
        tail = messages[-keep_recent:]
        middle = messages[2:-keep_recent] if len(messages) > 2 + keep_recent else []

        if not middle:
            return messages

        # Compress middle into a summary
        summaries: list[str] = []
        for msg in middle:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "assistant":
                # Tool call by agent
                try:
                    parsed = json.loads(content)
                    tool = parsed.get("tool", "?")
                    thought = parsed.get("thought", "")
                    summaries.append(f"  → Agent 调用 {tool}" + (f" ({thought[:60]})" if thought else ""))
                except (json.JSONDecodeError, ValueError):
                    summaries.append(f"  → Agent 输出（{len(content)} 字符）")
            elif role == "user":
                compressed = _summarize_observation(content, max_chars=200)
                summaries.append(f"  ← {compressed}")

        summary_text = (
            f"[已压缩 {len(middle)} 条历史工具交互]\n"
            + "\n".join(summaries)
        )

        compressed_message = {
            "role": "user",
            "content": f"以下是之前工具调用的摘要：\n{summary_text}\n\n请继续工作。",
        }

        return head + [compressed_message] + tail

    def trim_large_payload(self, content: str, max_chars: int = 8000) -> str:
        """Trim a single message content if it's excessively large."""
        if len(content) <= max_chars:
            return content
        # Try to preserve structure by cutting at line boundaries
        lines = content.splitlines(True)
        result: list[str] = []
        char_count = 0
        for line in lines:
            if char_count + len(line) > max_chars - 40:
                result.append(f"\n...[已截断，原始 {len(content)} 字符]")
                break
            result.append(line)
            char_count += len(line)
        return "".join(result)
