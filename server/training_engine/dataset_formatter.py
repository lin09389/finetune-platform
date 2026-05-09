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
        instruction = example.get("instruction", "")
        input_text = example.get("input", "")
        output = example.get("output", "")
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

    if mask_until <= 1:
        return

    for j in range(1, mask_until):
        label[j] = -100


def _mask_before_assistant(label: list[int], text: str, tokenizer):
    """Mask all tokens before the assistant's first response for messages format."""
    markers = [
        tokenizer.encode(" Assistant:", add_special_tokens=False),
        tokenizer.encode("Assistant:", add_special_tokens=False),
        tokenizer.encode("[/INST]", add_special_tokens=False),
        tokenizer.encode("[INST]", add_special_tokens=False),
        tokenizer.encode("> ", add_special_tokens=False),
        tokenizer.encode("### Response", add_special_tokens=False),
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

    if mask_until <= 1:
        return

    for j in range(1, mask_until):
        label[j] = -100
