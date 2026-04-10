import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

from pydantic import BaseModel

from ..types import IntentType, ParseResult


class SeparatorType(str, Enum):
    COMMA = "comma"
    PERIOD = "period"
    CONJUNCTION = "conjunction"
    NEWLINE = "newline"
    SEMICOLON = "semicolon"


@dataclass
class IntentSegment:
    text: str
    start: int
    end: int
    separator: SeparatorType | None = None
    confidence: float = 0.0


class MultiIntentResult(BaseModel):
    has_multiple: bool = False
    intents: list[ParseResult] = []
    segments: list[str] = []
    separators_used: list[str] = []
    confidence: float = 0.0


class MultiIntentParser:
    SEPARATORS = [
        (r'[，,]\s*(?:然后|接着|再)?', SeparatorType.COMMA),
        (r'[。]\s*', SeparatorType.PERIOD),
        (r'[；;]\s*', SeparatorType.SEMICOLON),
        (r'\s+然后\s+', SeparatorType.CONJUNCTION),
        (r'\s+接着\s+', SeparatorType.CONJUNCTION),
        (r'\s+再\s+', SeparatorType.CONJUNCTION),
        (r'\s+之后\s+', SeparatorType.CONJUNCTION),
        (r'\s+同时\s+', SeparatorType.CONJUNCTION),
        (r'\s+并且\s+', SeparatorType.CONJUNCTION),
        (r'\n+', SeparatorType.NEWLINE),
    ]

    CONTEXT_INDICATORS = [
        r'先\s*',
        r'首先\s*',
        r'然后\s*',
        r'接着\s*',
        r'最后\s*',
        r'再\s*',
        r'之后\s*',
    ]

    def __init__(self):
        self._compiled_separators = [
            (re.compile(p, re.IGNORECASE), t) for p, t in self.SEPARATORS
        ]
        self._compiled_context = [
            re.compile(p, re.IGNORECASE) for p in self.CONTEXT_INDICATORS
        ]

    def detect_multi_intent(self, message: str) -> MultiIntentResult:
        if not message or not message.strip():
            return MultiIntentResult()

        segments = self._split_message(message)

        if len(segments) <= 1:
            return MultiIntentResult(
                has_multiple=False,
                segments=[message.strip()]
            )

        cleaned_segments = []

        for seg in segments:
            cleaned = self._clean_segment(seg)
            if cleaned:
                cleaned_segments.append(cleaned)

        separators = self._extract_separators(message)

        return MultiIntentResult(
            has_multiple=len(cleaned_segments) > 1,
            segments=cleaned_segments,
            separators_used=separators,
            confidence=self._calculate_split_confidence(cleaned_segments)
        )

    def split_and_parse(
        self,
        message: str,
        parser_func
    ) -> MultiIntentResult:
        split_result = self.detect_multi_intent(message)

        if not split_result.has_multiple:
            single_result = parser_func(message)
            return MultiIntentResult(
                has_multiple=False,
                intents=[single_result],
                segments=[message.strip()]
            )

        intents = []
        for segment in split_result.segments:
            try:
                result = parser_func(segment)
                intents.append(result)
            except Exception:
                intents.append(ParseResult(
                    intent=IntentType.UNKNOWN,
                    action="",
                    raw_message=segment,
                    confidence=0.0
                ))

        return MultiIntentResult(
            has_multiple=True,
            intents=intents,
            segments=split_result.segments,
            separators_used=split_result.separators_used,
            confidence=split_result.confidence
        )

    def merge_results(
        self,
        results: list[ParseResult],
        original_message: str
    ) -> ParseResult:
        if not results:
            return ParseResult(
                intent=IntentType.UNKNOWN,
                action="",
                raw_message=original_message
            )

        if len(results) == 1:
            return results[0]

        best_result = max(results, key=lambda r: r.confidence)

        all_params = {}
        for result in results:
            all_params.update(result.params)

        return ParseResult(
            intent=best_result.intent,
            action="multi_action",
            params=all_params,
            confidence=sum(r.confidence for r in results) / len(results),
            raw_message=original_message,
            alternatives=results,
            metadata={"multi_intent": True, "intent_count": len(results)}
        )

    def _split_message(self, message: str) -> list[str]:
        segments = [message]

        for pattern, _ in self._compiled_separators:
            new_segments = []
            for seg in segments:
                parts = pattern.split(seg)
                new_segments.extend([p.strip() for p in parts if p and p.strip()])
            segments = new_segments

        return segments

    def _clean_segment(self, segment: str) -> str:
        for pattern in self._compiled_context:
            segment = pattern.sub('', segment)

        return segment.strip()

    def _extract_separators(self, message: str) -> list[str]:
        separators = []

        for pattern, sep_type in self._compiled_separators:
            matches = pattern.findall(message)
            for _match in matches:
                separators.append(sep_type.value)

        return separators

    def _calculate_split_confidence(self, segments: list[str]) -> float:
        if len(segments) <= 1:
            return 0.0

        valid_segments = sum(1 for s in segments if len(s) >= 2)
        ratio = valid_segments / len(segments)

        length_variance = sum(len(s) for s in segments) / len(segments)
        balance_score = min(1.0, length_variance / 10)

        return min(1.0, ratio * 0.6 + balance_score * 0.4)

    def detect_sequence(self, message: str) -> list[IntentSegment]:
        segments = []

        split_positions = []
        for pattern, sep_type in self._compiled_separators:
            for match in pattern.finditer(message):
                split_positions.append((match.start(), match.end(), sep_type))

        split_positions.sort(key=lambda x: x[0])

        prev_end = 0
        for start, end, _sep_type in split_positions:
            if start > prev_end:
                segment_text = message[prev_end:start].strip()
                if segment_text:
                    segments.append(IntentSegment(
                        text=segment_text,
                        start=prev_end,
                        end=start,
                        confidence=0.8
                    ))
            prev_end = end

        if prev_end < len(message):
            segment_text = message[prev_end:].strip()
            if segment_text:
                segments.append(IntentSegment(
                    text=segment_text,
                    start=prev_end,
                    end=len(message),
                    confidence=0.8
                ))

        return segments

    def is_sequential_intent(self, message: str) -> bool:
        sequence_indicators = [
            r'先\s*.+[，,]?\s*然后',
            r'首先\s*.+[，,]?\s*接着',
            r'第一步\s*.+[，,]?\s*第二步',
            r'先\s*.+[，,]?\s*再',
        ]

        return any(re.search(pattern, message) for pattern in sequence_indicators)

    def extract_order_hints(self, message: str) -> list[dict[str, Any]]:
        hints = []

        order_patterns = [
            (r'第([一二三四五六七八九十]+)步[:：]?\s*', 'step'),
            (r'([一二三四五六七八九十]+)[、.]\s*', 'numbered'),
            (r'(\d+)[、.]\s*', 'numbered'),
            (r'首先\s*', 'first'),
            (r'然后\s*', 'then'),
            (r'接着\s*', 'then'),
            (r'最后\s*', 'last'),
            (r'再\s*', 'then'),
        ]

        for pattern, hint_type in order_patterns:
            for match in re.finditer(pattern, message):
                hints.append({
                    'type': hint_type,
                    'position': match.start(),
                    'text': match.group(0),
                    'value': match.group(1) if match.groups() else None
                })

        return sorted(hints, key=lambda x: x['position'])
