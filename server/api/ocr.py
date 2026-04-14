"""OCR API backed by Tesseract."""

from __future__ import annotations

import asyncio
import base64
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from io import BytesIO
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core.tesseract import configure_tesseract, refresh_tesseract

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ocr", tags=["ocr"])

_ocr_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="ocr-")

try:
    import pytesseract
    from PIL import Image, ImageFilter, ImageOps
except ImportError:
    pytesseract = None
    Image = None
    ImageFilter = None
    ImageOps = None

try:
    import cv2
    import numpy as np
    from rapidocr_onnxruntime import RapidOCR
except ImportError:
    cv2 = None
    np = None
    RapidOCR = None

TESSERACT_AVAILABLE, TESSERACT_PATH, TESSERACT_ERROR = configure_tesseract()
if TESSERACT_AVAILABLE:
    logger.info("Tesseract OCR ready: %s", TESSERACT_PATH)
else:
    logger.warning("Tesseract OCR unavailable: %s", TESSERACT_ERROR)

RAPIDOCR_AVAILABLE = RapidOCR is not None and cv2 is not None and np is not None
_rapidocr_engine = None

LANGUAGE_MAP = {
    "ch": "chi_sim+eng",
    "ch_tra": "chi_tra+eng",
    "en": "eng",
    "ja": "jpn",
    "ko": "kor",
    "de": "deu",
    "fr": "fra",
    "es": "spa",
    "ru": "rus",
}

LANGUAGE_CANDIDATES = {
    "ch": ["chi_sim", "chi_sim+eng"],
    "ch_tra": ["chi_tra", "chi_tra+eng"],
    "en": ["eng"],
    "ja": ["jpn"],
    "ko": ["kor"],
    "de": ["deu"],
    "fr": ["fra"],
    "es": ["spa"],
    "ru": ["rus"],
}


class OCRRequest(BaseModel):
    image_base64: str = Field(..., description="Base64-encoded image")
    language: str = Field(default="ch", description="Language code")
    detect_language: bool = Field(default=False, description="Reserved for future use")
    preserve_interword_spaces: bool = Field(default=True, description="Reserved for future use")


class OCRRegion(BaseModel):
    bounding_box: str = Field(..., description="x,y,width,height")
    text: str = Field(..., description="Recognized text")
    confidence: float = Field(..., description="Confidence from 0 to 1")


class OCRResponse(BaseModel):
    text: str = Field(..., description="Recognized text")
    confidence: float = Field(default=0.0, description="Average confidence")
    regions: list[OCRRegion] = Field(default_factory=list, description="Recognized regions")
    language: str = Field(default="", description="Requested language code")
    processing_time: float = Field(default=0.0, description="Processing time in seconds")
    engine: str = Field(default="tesseract", description="OCR engine")
    available: bool = Field(default=True, description="Whether an OCR engine is currently available")
    status: str = Field(default="ok", description="Availability status")
    error_code: str | None = Field(default=None, description="Machine-readable error code when OCR is unavailable")


class BatchOCRRequest(BaseModel):
    images: list[str] = Field(..., description="List of Base64-encoded images")
    language: str = Field(default="ch", description="Language code")


class BatchOCRResponse(BaseModel):
    results: list[OCRResponse] = Field(default_factory=list)
    total_processing_time: float = Field(default=0.0)


class LanguageInfo(BaseModel):
    code: str
    name: str
    tesseract_code: str
    available: bool


def _unavailable_response(language: str) -> dict:
    return {
        "text": "",
        "confidence": 0.0,
        "regions": [],
        "language": language,
        "processing_time": 0.0,
        "engine": "unavailable",
        "available": False,
        "status": "unavailable",
        "error_code": "dependency_missing",
    }


def _ocr_is_available() -> bool:
    return RAPIDOCR_AVAILABLE or (TESSERACT_AVAILABLE and pytesseract is not None and Image is not None)


def _get_rapidocr_engine():
    global _rapidocr_engine
    if not RAPIDOCR_AVAILABLE:
        return None
    if _rapidocr_engine is None:
        _rapidocr_engine = RapidOCR()
    return _rapidocr_engine


def _normalize_image(image: Image.Image) -> Image.Image:
    if image.mode not in ("RGB", "L"):
        return image.convert("RGB")
    return image


def _preprocess_variants(image: Image.Image) -> list[tuple[str, Image.Image]]:
    image = _normalize_image(image)
    variants: list[tuple[str, Image.Image]] = [("original", image)]

    if ImageOps is None or ImageFilter is None:
        return variants

    gray = ImageOps.grayscale(image)
    large_gray = gray.resize((gray.width * 2, gray.height * 2), Image.Resampling.LANCZOS)
    sharp_large = large_gray.filter(ImageFilter.SHARPEN)
    binary = sharp_large.point(lambda px: 255 if px > 180 else 0, mode="1").convert("L")

    variants.extend(
        [
            ("gray", gray),
            ("large_gray", large_gray),
            ("sharp_large", sharp_large),
            ("binary", binary),
        ]
    )
    return variants


def _language_configs(language: str) -> list[str]:
    if language in {"ch", "ch_tra"}:
        return [
            "--oem 3 --psm 6",
            "--oem 3 --psm 7",
            "--oem 1 --psm 6",
        ]
    return [
        "--oem 3 --psm 6",
        "--oem 3 --psm 11",
    ]


def _language_targets(language: str) -> list[str]:
    return LANGUAGE_CANDIDATES.get(language, [LANGUAGE_MAP.get(language, "eng")])


def _extract_regions(data: dict[str, list[Any]]) -> tuple[list[OCRRegion], float]:
    regions: list[OCRRegion] = []
    confidences: list[float] = []

    for i, raw_text in enumerate(data["text"]):
        text = str(raw_text).strip()
        conf_raw = str(data["conf"][i]).strip()
        try:
            conf_value = float(conf_raw)
        except ValueError:
            conf_value = -1

        if not text or conf_value <= 0:
            continue

        confidence = conf_value / 100.0
        confidences.append(confidence)
        regions.append(
            OCRRegion(
                bounding_box=(
                    f"{data['left'][i]},{data['top'][i]},"
                    f"{data['width'][i]},{data['height'][i]}"
                ),
                text=text,
                confidence=confidence,
            )
        )

    avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    return regions, avg_confidence


def _score_candidate(
    text: str,
    avg_confidence: float,
    regions: list[OCRRegion],
    variant_name: str,
    language: str,
) -> float:
    normalized = "".join(text.split())
    cjk_count = sum(1 for ch in normalized if "\u4e00" <= ch <= "\u9fff")
    alnum_count = sum(1 for ch in normalized if ch.isalnum())
    digit_count = sum(1 for ch in normalized if ch.isdigit())
    region_bonus = min(len(regions), 8) * 0.05
    variant_bonus = 0.08 if variant_name in {"sharp_large", "binary"} else 0.0
    score = (avg_confidence * 2.5) + (cjk_count * 0.9) + (alnum_count * 0.12) + region_bonus + variant_bonus

    if language in {"ch", "ch_tra"}:
        if cjk_count == 0:
            score -= 1.2
        if digit_count == len(normalized) and digit_count > 0:
            score -= 0.8

    return score


def _perform_ocr(image_data: bytes, language: str = "ch") -> dict:
    if not _ocr_is_available():
        return _unavailable_response(language)

    start_time = datetime.now()
    try:
        image = Image.open(BytesIO(image_data))
        if language in {"ch", "ch_tra"}:
            rapid_result = _perform_rapidocr(image_data, language)
            if rapid_result and rapid_result["text"].strip():
                rapid_result["processing_time"] = round((datetime.now() - start_time).total_seconds(), 3)
                return rapid_result

        best_text = ""
        best_regions: list[OCRRegion] = []
        best_confidence = 0.0
        best_score = -1.0

        for variant_name, variant_image in _preprocess_variants(image):
            for tess_lang in _language_targets(language):
                for config in _language_configs(language):
                    data = pytesseract.image_to_data(
                        variant_image,
                        lang=tess_lang,
                        config=config,
                        output_type=pytesseract.Output.DICT,
                    )
                    text = pytesseract.image_to_string(
                        variant_image,
                        lang=tess_lang,
                        config=config,
                    ).strip()
                    regions, avg_confidence = _extract_regions(data)
                    score = _score_candidate(text, avg_confidence, regions, variant_name, language)

                    if score > best_score:
                        best_score = score
                        best_text = text
                        best_regions = regions
                        best_confidence = avg_confidence

        processing_time = (datetime.now() - start_time).total_seconds()
        return {
            "text": best_text,
            "confidence": round(best_confidence, 3),
            "regions": best_regions,
            "language": language,
            "processing_time": round(processing_time, 3),
            "engine": "tesseract",
            "available": True,
            "status": "ok",
            "error_code": None,
        }
    except Exception as exc:
        logger.error("OCR processing failed: %s", exc)
        return {
            "text": f"OCR processing failed: {exc}",
            "confidence": 0.0,
            "regions": [],
            "language": language,
            "processing_time": 0.0,
            "engine": "error",
            "available": False,
            "status": "error",
            "error_code": "processing_failed",
        }


def _perform_rapidocr(image_data: bytes, language: str) -> dict | None:
    engine = _get_rapidocr_engine()
    if engine is None or cv2 is None or np is None:
        return None

    try:
        array = np.frombuffer(image_data, dtype=np.uint8)
        image = cv2.imdecode(array, cv2.IMREAD_COLOR)
        if image is None:
            return None

        result, _ = engine(image)
        if not result:
            return None

        regions: list[OCRRegion] = []
        texts: list[str] = []
        confidences: list[float] = []

        for item in result:
            points, text, confidence = item
            xs = [int(point[0]) for point in points]
            ys = [int(point[1]) for point in points]
            left = min(xs)
            top = min(ys)
            width = max(xs) - left
            height = max(ys) - top
            text = str(text).strip()
            if not text:
                continue
            conf_value = float(confidence)
            texts.append(text)
            confidences.append(conf_value)
            regions.append(
                OCRRegion(
                    bounding_box=f"{left},{top},{width},{height}",
                    text=text,
                    confidence=conf_value,
                )
            )

        if not texts:
            return None

        avg_confidence = sum(confidences) / len(confidences)
        return {
            "text": "\n".join(texts),
            "confidence": round(avg_confidence, 3),
            "regions": regions,
            "language": language,
            "processing_time": 0.0,
            "engine": "rapidocr",
            "available": True,
            "status": "ok",
            "error_code": None,
        }
    except Exception as exc:
        logger.warning("RapidOCR processing failed, falling back to Tesseract: %s", exc)
        return None


@router.post("", response_model=OCRResponse)
async def ocr_image(request: OCRRequest):
    try:
        if not _ocr_is_available():
            raise HTTPException(
                status_code=503,
                detail={
                    "message": "OCR engine is unavailable",
                    "error_code": "dependency_missing",
                    "available": False,
                    "status": "unavailable",
                },
            )
        image_data = base64.b64decode(request.image_base64)
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(_ocr_executor, _perform_ocr, image_data, request.language)
        return OCRResponse(**result)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("OCR API failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"OCR processing failed: {exc}")


@router.post("/batch", response_model=BatchOCRResponse)
async def batch_ocr(request: BatchOCRRequest):
    if len(request.images) > 10:
        raise HTTPException(status_code=400, detail="At most 10 images are supported per request")

    start_time = datetime.now()
    loop = asyncio.get_event_loop()
    results: list[OCRResponse] = []

    for image_base64 in request.images:
        try:
            image_data = base64.b64decode(image_base64)
            result = await loop.run_in_executor(_ocr_executor, _perform_ocr, image_data, request.language)
            results.append(OCRResponse(**result))
        except Exception as exc:
            logger.error("Batch OCR item failed: %s", exc)
            results.append(
                OCRResponse(
                    text="",
                    confidence=0.0,
                    regions=[],
                    engine="error",
                    available=False,
                    status="error",
                    error_code="processing_failed",
                )
            )

    total_time = (datetime.now() - start_time).total_seconds()
    return BatchOCRResponse(results=results, total_processing_time=round(total_time, 3))


@router.get("/languages", response_model=list[LanguageInfo])
async def get_supported_languages():
    languages = []
    available_langs: set[str] = set()

    if TESSERACT_AVAILABLE and pytesseract is not None:
        try:
            available_langs = set(pytesseract.get_languages(config=""))
        except Exception:
            available_langs = set()

    for code, name in [
        ("ch", "Chinese Simplified"),
        ("ch_tra", "Chinese Traditional"),
        ("en", "English"),
        ("ja", "Japanese"),
        ("ko", "Korean"),
        ("de", "German"),
        ("fr", "French"),
        ("es", "Spanish"),
        ("ru", "Russian"),
    ]:
        tess_code = LANGUAGE_MAP[code]
        if code in {"ch", "ch_tra"}:
            available = RAPIDOCR_AVAILABLE
        else:
            available = all(part in available_langs for part in tess_code.split("+"))
        languages.append(
            LanguageInfo(
                code=code,
                name=name,
                tesseract_code=tess_code,
                available=available,
            )
        )
    return languages


@router.get("/status")
async def get_ocr_status():
    global TESSERACT_AVAILABLE, TESSERACT_PATH, TESSERACT_ERROR
    TESSERACT_AVAILABLE, TESSERACT_PATH, TESSERACT_ERROR = refresh_tesseract()

    supported_languages: list[str] = []
    if TESSERACT_AVAILABLE and pytesseract is not None:
        try:
            supported_languages = list(pytesseract.get_languages(config=""))
        except Exception:
            supported_languages = []

    return {
        "engine": "rapidocr+tesseract" if RAPIDOCR_AVAILABLE and TESSERACT_AVAILABLE else (
            "rapidocr" if RAPIDOCR_AVAILABLE else ("tesseract" if TESSERACT_AVAILABLE else "unavailable")
        ),
        "available": _ocr_is_available(),
        "status": "ok" if _ocr_is_available() else "unavailable",
        "error_code": None if _ocr_is_available() else "dependency_missing",
        "message": "OCR engine ready" if _ocr_is_available() else "OCR engine is not installed or not configured",
        "tesseract_path": TESSERACT_PATH,
        "error": TESSERACT_ERROR,
        "rapidocr_available": RAPIDOCR_AVAILABLE,
        "tesseract_available": TESSERACT_AVAILABLE and pytesseract is not None and Image is not None,
        "supported_languages": supported_languages,
    }
