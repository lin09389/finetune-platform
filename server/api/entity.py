"""
实体识别 API
"""
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from core.entity_recognition import entity_highlighter

router = APIRouter(prefix="/entity", tags=["entity"])


class RecognizeRequest(BaseModel):
    text: str
    highlight: bool = True
    link_memory: bool = False
    memory_entities: dict[str, Any] | None = None


class EntityResponse(BaseModel):
    text: str
    label: str
    label_zh: str
    start: int
    end: int
    confidence: float
    color: str


class RecognizeResponse(BaseModel):
    original_text: str
    highlighted_text: str
    entities: list[EntityResponse]
    entity_count: int
    entity_stats: dict[str, int]


class BatchRecognizeRequest(BaseModel):
    texts: list[str]
    highlight: bool = True


class BatchRecognizeResponse(BaseModel):
    results: list[RecognizeResponse]


@router.post("/recognize", response_model=RecognizeResponse)
async def recognize_entities(request: RecognizeRequest):
    result = entity_highlighter.process_message(
        text=request.text,
        highlight=request.highlight,
        link_memory=request.link_memory,
        memory_entities=request.memory_entities,
    )

    entities = [
        EntityResponse(
            text=e["text"],
            label=e["label"],
            label_zh=e["metadata"].get("label_zh", e["label"]),
            start=e["start"],
            end=e["end"],
            confidence=e["confidence"],
            color=e["metadata"].get("color", "#999"),
        )
        for e in result["entities"]
    ]

    return RecognizeResponse(
        original_text=result["original_text"],
        highlighted_text=result["highlighted_text"],
        entities=entities,
        entity_count=result["entity_count"],
        entity_stats=result["entity_stats"],
    )


@router.post("/batch", response_model=BatchRecognizeResponse)
async def batch_recognize(request: BatchRecognizeRequest):
    results = []
    for text in request.texts:
        result = entity_highlighter.process_message(text, highlight=request.highlight)

        entities = [
            EntityResponse(
                text=e["text"],
                label=e["label"],
                label_zh=e["metadata"].get("label_zh", e["label"]),
                start=e["start"],
                end=e["end"],
                confidence=e["confidence"],
                color=e["metadata"].get("color", "#999"),
            )
            for e in result["entities"]
        ]

        results.append(
            RecognizeResponse(
                original_text=result["original_text"],
                highlighted_text=result["highlighted_text"],
                entities=entities,
                entity_count=result["entity_count"],
                entity_stats=result["entity_stats"],
            )
        )

    return BatchRecognizeResponse(results=results)


@router.get("/types")
async def get_entity_types():
    return {
        "types": [
            {"label": "PERSON", "label_zh": "人物", "color": "#1890ff"},
            {"label": "ORGANIZATION", "label_zh": "组织", "color": "#722ed1"},
            {"label": "LOCATION", "label_zh": "地点", "color": "#13c2c2"},
            {"label": "DATE", "label_zh": "日期", "color": "#fa8c16"},
            {"label": "TIME", "label_zh": "时间", "color": "#faad14"},
            {"label": "MONEY", "label_zh": "金额", "color": "#52c41a"},
            {"label": "PHONE", "label_zh": "电话", "color": "#eb2f96"},
            {"label": "EMAIL", "label_zh": "邮箱", "color": "#2f54eb"},
            {"label": "URL", "label_zh": "网址", "color": "#1890ff"},
            {"label": "FILE_PATH", "label_zh": "文件", "color": "#fa541c"},
            {"label": "CODE", "label_zh": "代码", "color": "#595959"},
            {"label": "IP_ADDRESS", "label_zh": "IP地址", "color": "#f5222d"},
        ]
    }
