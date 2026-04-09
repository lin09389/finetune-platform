"""
CUA OCR 识别模块
"""
import asyncio
import hashlib
import re
from typing import Any

from PIL import Image

from core.tesseract import configure_tesseract

from .exceptions import OCRError, OCRProcessingError, TesseractNotInstalledError
from .types import Coordinate, Region

try:
    import pytesseract
except ImportError:
    pytesseract = None

TESSERACT_AVAILABLE, TESSERACT_PATH, TESSERACT_ERROR = configure_tesseract()

try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    cv2 = None
    np = None


SUPPORTED_LANGUAGES = {
    "chi_sim": "中文简体",
    "chi_tra": "中文繁体",
    "eng": "English",
    "jpn": "日本語",
    "kor": "한국어",
    "chi_sim+eng": "中文简体+English",
    "chi_tra+eng": "中文繁体+English",
}


class OCRRecognizer:
    def __init__(self, tesseract_path: str | None = None):
        self._tesseract_path = tesseract_path
        self._current_lang = "chi_sim+eng"
        self._cache: dict[str, Any] = {}
        self._cache_max_size = 100

        if tesseract_path and pytesseract is not None:
            pytesseract.pytesseract.tesseract_cmd = tesseract_path

        self._check_tesseract()

    def _check_tesseract(self) -> None:
        if not TESSERACT_AVAILABLE:
            raise TesseractNotInstalledError(
                details="pytesseract 库未安装，请运行: pip install pytesseract"
            )
        try:
            pytesseract.get_tesseract_version()
        except Exception as e:
            raise TesseractNotInstalledError(
                details=f"Tesseract 可执行文件未找到或无法运行: {e}"
            )

    def _get_image_hash(self, image: Image.Image) -> str:
        img_bytes = image.tobytes()
        return hashlib.md5(img_bytes + self._current_lang.encode()).hexdigest()

    def _cache_get(self, key: str) -> Any | None:
        return self._cache.get(key)

    def _cache_set(self, key: str, value: Any) -> None:
        if len(self._cache) >= self._cache_max_size:
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]
        self._cache[key] = value

    def set_language(self, lang: str) -> None:
        if lang not in SUPPORTED_LANGUAGES:
            available = ", ".join(SUPPORTED_LANGUAGES.keys())
            raise OCRError(
                f"不支持的语言: {lang}",
                operation="set_language",
                details=f"可用语言: {available}"
            )
        self._current_lang = lang

    def get_available_languages(self) -> list[str]:
        try:
            langs = pytesseract.get_languages()
            return langs
        except Exception:
            return list(SUPPORTED_LANGUAGES.keys())

    def preprocess_image(self, image: Image.Image) -> Image.Image:
        if not CV2_AVAILABLE:
            return image.convert("L")

        img_array = np.array(image)

        if len(img_array.shape) == 3:
            gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
        else:
            gray = img_array

        blurred = cv2.GaussianBlur(gray, (3, 3), 0)

        _, binary = cv2.threshold(
            blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )

        kernel = np.ones((1, 1), np.uint8)
        processed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)

        return Image.fromarray(processed)

    def enhance_for_ocr(self, image: Image.Image) -> Image.Image:
        if not CV2_AVAILABLE:
            enhanced = image.convert("L")
            return enhanced.point(lambda x: 0 if x < 128 else 255)

        img_array = np.array(image)

        if len(img_array.shape) == 3:
            gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
        else:
            gray = img_array

        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)

        denoised = cv2.fastNlMeansDenoising(enhanced, None, 10, 7, 21)

        _, binary = cv2.threshold(
            denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )

        return Image.fromarray(binary)

    def recognize(
        self,
        image: Image.Image,
        lang: str | None = None,
        preprocess: bool = True
    ) -> str:
        if not TESSERACT_AVAILABLE:
            raise TesseractNotInstalledError()

        lang = lang or self._current_lang

        cache_key = f"{self._get_image_hash(image)}_{lang}_{preprocess}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        try:
            if preprocess:
                processed_image = self.enhance_for_ocr(image)
            else:
                processed_image = image

            text = pytesseract.image_to_string(processed_image, lang=lang)
            result = text.strip()

            self._cache_set(cache_key, result)
            return result

        except Exception as e:
            raise OCRProcessingError(
                f"OCR 识别失败: {str(e)}",
                original_error=e
            )

    async def recognize_async(
        self,
        image: Image.Image,
        lang: str | None = None,
        preprocess: bool = True
    ) -> str:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.recognize(image, lang, preprocess)
        )

    def recognize_region(
        self,
        image: Image.Image,
        region: Region,
        lang: str | None = None,
        preprocess: bool = True
    ) -> str:
        cropped = image.crop((
            region.x,
            region.y,
            region.x + region.width,
            region.y + region.height
        ))
        return self.recognize(cropped, lang, preprocess)

    async def recognize_region_async(
        self,
        image: Image.Image,
        region: Region,
        lang: str | None = None,
        preprocess: bool = True
    ) -> str:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.recognize_region(image, region, lang, preprocess)
        )

    def get_text_boxes(
        self,
        image: Image.Image,
        lang: str | None = None,
        preprocess: bool = True
    ) -> list[dict[str, Any]]:
        if not TESSERACT_AVAILABLE:
            raise TesseractNotInstalledError()

        lang = lang or self._current_lang

        try:
            if preprocess:
                processed_image = self.enhance_for_ocr(image)
            else:
                processed_image = image

            data = pytesseract.image_to_data(
                processed_image,
                lang=lang,
                output_type=pytesseract.Output.DICT
            )

            boxes = []
            n_boxes = len(data["text"])

            for i in range(n_boxes):
                text = data["text"][i].strip()
                if not text:
                    continue

                boxes.append({
                    "text": text,
                    "x": data["left"][i],
                    "y": data["top"][i],
                    "width": data["width"][i],
                    "height": data["height"][i],
                    "confidence": float(data["conf"][i]) if data["conf"][i] != "-1" else 0.0,
                    "block_num": data["block_num"][i],
                    "line_num": data["line_num"][i],
                })

            return boxes

        except Exception as e:
            raise OCRProcessingError(
                f"获取文本框失败: {str(e)}",
                original_error=e
            )

    def find_text(
        self,
        image: Image.Image,
        text: str,
        lang: str | None = None,
        fuzzy: bool = False,
        use_regex: bool = False
    ) -> list[Coordinate]:
        boxes = self.get_text_boxes(image, lang)

        matches = []

        for box in boxes:
            box_text = box["text"]
            matched = False

            if use_regex:
                try:
                    if re.search(text, box_text):
                        matched = True
                except re.error:
                    pass
            elif fuzzy:
                if text.lower() in box_text.lower() or box_text.lower() in text.lower():
                    matched = True
            else:
                if text == box_text:
                    matched = True

            if matched:
                center_x = box["x"] + box["width"] // 2
                center_y = box["y"] + box["height"] // 2
                matches.append(Coordinate(x=center_x, y=center_y))

        return matches

    def find_text_regions(
        self,
        image: Image.Image,
        text: str,
        lang: str | None = None,
        fuzzy: bool = False,
        use_regex: bool = False
    ) -> list[Region]:
        boxes = self.get_text_boxes(image, lang)

        matches = []

        for box in boxes:
            box_text = box["text"]
            matched = False

            if use_regex:
                try:
                    if re.search(text, box_text):
                        matched = True
                except re.Error:
                    pass
            elif fuzzy:
                if text.lower() in box_text.lower() or box_text.lower() in text.lower():
                    matched = True
            else:
                if text == box_text:
                    matched = True

            if matched:
                matches.append(Region(
                    x=box["x"],
                    y=box["y"],
                    width=box["width"],
                    height=box["height"]
                ))

        return matches

    def find_all_text(
        self,
        image: Image.Image,
        text: str,
        lang: str | None = None,
        fuzzy: bool = False,
        use_regex: bool = False
    ) -> list[dict[str, Any]]:
        boxes = self.get_text_boxes(image, lang)

        matches = []

        for box in boxes:
            box_text = box["text"]
            matched = False

            if use_regex:
                try:
                    if re.search(text, box_text):
                        matched = True
                except re.error:
                    pass
            elif fuzzy:
                if text.lower() in box_text.lower() or box_text.lower() in text.lower():
                    matched = True
            else:
                if text == box_text:
                    matched = True

            if matched:
                matches.append({
                    "text": box_text,
                    "coordinate": Coordinate(
                        x=box["x"] + box["width"] // 2,
                        y=box["y"] + box["height"] // 2
                    ),
                    "region": Region(
                        x=box["x"],
                        y=box["y"],
                        width=box["width"],
                        height=box["height"]
                    ),
                    "confidence": box["confidence"]
                })

        return matches

    def get_text_confidence(
        self,
        image: Image.Image,
        lang: str | None = None
    ) -> float:
        boxes = self.get_text_boxes(image, lang)

        if not boxes:
            return 0.0

        total_confidence = sum(box["confidence"] for box in boxes)
        return total_confidence / len(boxes)

    def clear_cache(self) -> None:
        self._cache.clear()

    @staticmethod
    def is_tesseract_available() -> bool:
        return TESSERACT_AVAILABLE

    @staticmethod
    def is_opencv_available() -> bool:
        return CV2_AVAILABLE

    @staticmethod
    def get_supported_languages() -> dict[str, str]:
        return SUPPORTED_LANGUAGES.copy()
