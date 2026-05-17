"""
数据集格式检测与智能标签掩码
"""
from collections.abc import Mapping
from typing import Any

from core.logging import get_logger
from training_engine.schemas import SUPPORTED_DATASET_FORMATS

logger = get_logger(__name__)


def detect_dataset_sample_format(example: Any) -> str:
    """Detect the supported dataset sample format for a single record."""
    if not isinstance(example, Mapping):
        raise ValueError("Dataset sample must be a JSON object")

    if "messages" in example:
        return "messages"

    if "instruction" in example:
        if "output" not in example:
            raise ValueError("Alpaca format requires an 'output' field when 'instruction' is present")
        if "input" in example:
            return "instruction+input+output"
        return "instruction+output"

    if "description" in example and "code" in example:
        return "instruction+output"
    if "question" in example and "answer" in example:
        return "instruction+output"
    if "input" in example and "output" in example:
        return "instruction+output"

    if "content" in example:
        return "content"

    if "text" in example:
        return "text"

    supported = ", ".join(SUPPORTED_DATASET_FORMATS)
    raise ValueError(f"Unsupported dataset sample format; expected one of: {supported}")


def _detect_and_format(example: dict[str, Any], tokenizer) -> dict[str, Any]:
    """Detect format, normalize text, and carry format metadata for label masking.

    Returns a dict with 'text' (normalized string) and 'sample_format' (one of:
    'messages', 'instruction', 'content', 'text').
    """
    sample_format = detect_dataset_sample_format(example)

    if sample_format == "messages":
        messages = example.get("messages", [])

        if hasattr(tokenizer, "apply_chat_template") and messages:
            try:
                text = tokenizer.apply_chat_template(
                    messages,
                    tokenize=False,
                    add_generation_prompt=True,
                )
                return {"text": text, "sample_format": "messages"}
            except Exception as e:
                logger.warning(f"apply_chat_template failed, using fallback formatting: {e}")

        text = ""
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "user":
                text += f"User: {content}\n"
            elif role == "assistant":
                text += f"Assistant: {content}\n"
            elif role == "system":
                text += f"System: {content}\n"
        return {"text": text, "sample_format": "messages"}

    if sample_format in {"instruction+output", "instruction+input+output"}:
        instruction = example.get("instruction", "") or example.get("description", "") or example.get("question", "")
        input_text = example.get("input", "")
        output = example.get("output", "") or example.get("code", "") or example.get("answer", "")
        if input_text:
            text = f"Instruction: {instruction}\nInput: {input_text}\nResponse: {output}"
        else:
            text = f"Instruction: {instruction}\nResponse: {output}"
        return {"text": text, "sample_format": "instruction"}

    if sample_format == "content":
        return {"text": example.get("content", ""), "sample_format": "content"}

    return {"text": example.get("text", ""), "sample_format": "text"}


def _mask_before_response(label: list[int], text: str, tokenizer):
    """Mask all tokens before the response section for instruction format."""
    markers = [
        tokenizer.encode("Response:", add_special_tokens=False),
        tokenizer.encode("### Response", add_special_tokens=False),
        tokenizer.encode("Answer:", add_special_tokens=False),
        tokenizer.encode("### Answer", add_special_tokens=False),
        tokenizer.encode("Output:", add_special_tokens=False),
    ]
    markers = [m for m in markers if m]

    mask_until = -1
    for marker_ids in markers:
        if not marker_ids:
            continue
        marker_len = len(marker_ids)
        for start in range(1, len(label) - marker_len + 1):
            if label[start:start + marker_len] == marker_ids:
                mask_until = start + marker_len
                break
        if mask_until > 0:
            break

    if mask_until <= 0:
        return

    for j in range(mask_until):
        label[j] = -100


def _mask_before_assistant(label: list[int], text: str, tokenizer):
    """Mask all non-assistant tokens for messages format (multi-turn aware).

    策略：先将所有 token 掩码为 -100，再找出每个 assistant turn 的起止位置并
    恢复原始 token id，确保多轮对话中用户/系统消息不进入 loss 计算。
    """
    # assistant turn 开始标记（marker 之后是 assistant 内容）
    assistant_open_markers = [
        tokenizer.encode("[/INST]", add_special_tokens=False),
        tokenizer.encode(" Assistant:", add_special_tokens=False),
        tokenizer.encode("Assistant:", add_special_tokens=False),
        tokenizer.encode("### Response", add_special_tokens=False),
    ]
    # assistant turn 结束标记（marker 之前是 assistant 内容，之后是 user 内容）
    assistant_close_markers = [
        tokenizer.encode("[INST]", add_special_tokens=False),
        tokenizer.encode(" User:", add_special_tokens=False),
        tokenizer.encode("User:", add_special_tokens=False),
    ]

    assistant_open_markers = [m for m in assistant_open_markers if m]
    assistant_close_markers = [m for m in assistant_close_markers if m]

    # assistant 内容起始位置（紧接 open marker 之后）
    assist_starts = []
    for marker_ids in assistant_open_markers:
        mlen = len(marker_ids)
        if not mlen:
            continue
        for pos in range(len(label) - mlen + 1):
            if label[pos: pos + mlen] == marker_ids:
                assist_starts.append(pos + mlen)

    # assistant 内容结束位置：close marker 的起始处
    close_positions = []
    for marker_ids in assistant_close_markers:
        mlen = len(marker_ids)
        if not mlen:
            continue
        for pos in range(len(label) - mlen + 1):
            if label[pos: pos + mlen] == marker_ids:
                close_positions.append(pos)

    assist_starts.sort()
    close_positions.sort()

    if not assist_starts:
        # 没找到任何 assistant 标记，回退到原始单轮逻辑：仅掩码首个标记前内容
        return

    # 保存原始 token id，以便恢复 assistant 片段
    original = list(label)

    # 第一步：全部掩码
    for i in range(len(label)):
        label[i] = -100

    # 第二步：对每个 assistant 起始位置，找到其 turn 的结束位置并恢复
    for assist_start in assist_starts:
        # 找第一个在 assist_start 之后的 close 位置
        assist_end = next(
            (p for p in close_positions if p > assist_start),
            len(label),
        )
        for k in range(assist_start, assist_end):
            label[k] = original[k]
