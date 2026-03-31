import asyncio
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from .exceptions import (
    VisionError,
)
from .models import Coordinate, Region
from .screen import ScreenCapture


class VisionRecognizer:
    def __init__(self, debug_dir: str | None = None):
        self._screen_capture = ScreenCapture()
        self._debug_dir = Path(debug_dir) if debug_dir else None
        if self._debug_dir:
            self._debug_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def pil_to_cv2(image: Image.Image) -> np.ndarray:
        if image.mode != "RGB":
            image = image.convert("RGB")
        return cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)

    @staticmethod
    def cv2_to_pil(image: np.ndarray) -> Image.Image:
        return Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))

    def save_debug_image(self, image: Image.Image, name: str) -> None:
        if self._debug_dir is None:
            return
        debug_path = self._debug_dir / f"{name}.png"
        image.save(debug_path)

    def find_template(
        self, image: Image.Image, template: Image.Image, threshold: float = 0.8
    ) -> list[Coordinate]:
        try:
            img_cv = self.pil_to_cv2(image)
            template_cv = self.pil_to_cv2(template)

            if template_cv.shape[0] > img_cv.shape[0] or template_cv.shape[1] > img_cv.shape[1]:
                raise VisionError(
                    "Template is larger than source image",
                    operation="find_template"
                )

            result = cv2.matchTemplate(img_cv, template_cv, cv2.TM_CCOEFF_NORMED)
            locations = np.where(result >= threshold)

            coordinates: list[Coordinate] = []
            template_h, template_w = template_cv.shape[:2]

            for pt in zip(*locations[::-1]):
                center_x = int(pt[0] + template_w / 2)
                center_y = int(pt[1] + template_h / 2)
                coordinates.append(Coordinate(x=center_x, y=center_y))

            return coordinates
        except VisionError:
            raise
        except Exception as e:
            raise VisionError(
                "Failed to find template",
                operation="find_template",
                details=str(e)
            )

    def find_template_file(
        self, image: Image.Image, template_path: str, threshold: float = 0.8
    ) -> list[Coordinate]:
        try:
            template = Image.open(template_path)
            return self.find_template(image, template, threshold)
        except FileNotFoundError:
            raise VisionError(
                "Template file not found",
                operation="find_template_file",
                details=template_path
            )
        except Exception as e:
            raise VisionError(
                "Failed to load template file",
                operation="find_template_file",
                details=str(e)
            )

    def match_template(self, image: Image.Image, template: Image.Image) -> float:
        try:
            img_cv = self.pil_to_cv2(image)
            template_cv = self.pil_to_cv2(template)

            if template_cv.shape[0] > img_cv.shape[0] or template_cv.shape[1] > img_cv.shape[1]:
                return 0.0

            result = cv2.matchTemplate(img_cv, template_cv, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, _ = cv2.minMaxLoc(result)
            return float(max_val)
        except Exception as e:
            raise VisionError(
                "Failed to match template",
                operation="match_template",
                details=str(e)
            )

    def find_icon(
        self, image: Image.Image, icon: Image.Image, threshold: float = 0.8
    ) -> list[Coordinate]:
        return self.find_template(image, icon, threshold)

    def find_button(self, image: Image.Image, button_text: str) -> list[Region]:
        try:
            import pytesseract

            img_cv = self.pil_to_cv2(image)
            gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
            data = pytesseract.image_to_data(gray, output_type=pytesseract.Output.DICT)

            regions: list[Region] = []
            n_boxes = len(data["text"])

            for i in range(n_boxes):
                text = data["text"][i]
                if button_text.lower() in text.lower():
                    x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
                    padding = 5
                    regions.append(Region(
                        x=max(0, x - padding),
                        y=max(0, y - padding),
                        width=w + 2 * padding,
                        height=h + 2 * padding
                    ))

            return regions
        except ImportError:
            raise VisionError(
                "pytesseract not installed",
                operation="find_button",
                details="Install with: pip install pytesseract"
            )
        except Exception as e:
            raise VisionError(
                "Failed to find button",
                operation="find_button",
                details=str(e)
            )

    def find_color(
        self, image: Image.Image, color: tuple, tolerance: int = 10
    ) -> list[Coordinate]:
        try:
            img_cv = self.pil_to_cv2(image)
            hsv = cv2.cvtColor(img_cv, cv2.COLOR_BGR2HSV)

            target_bgr = np.uint8([[list(color)[::-1]]])
            target_hsv = cv2.cvtColor(target_bgr, cv2.COLOR_BGR2HSV)[0][0]

            lower = np.array([max(0, target_hsv[0] - tolerance), 50, 50])
            upper = np.array([min(179, target_hsv[0] + tolerance), 255, 255])

            mask = cv2.inRange(hsv, lower, upper)
            locations = np.where(mask > 0)

            coordinates: list[Coordinate] = []
            for x, y in zip(*locations[::-1]):
                coordinates.append(Coordinate(x=int(x), y=int(y)))

            return coordinates
        except Exception as e:
            raise VisionError(
                "Failed to find color",
                operation="find_color",
                details=str(e)
            )

    def get_dominant_color(self, image: Image.Image) -> tuple:
        try:
            img_cv = self.pil_to_cv2(image)
            img_cv = cv2.cvtColor(img_cv, cv2.COLOR_BGR2RGB)

            pixels = np.float32(img_cv.reshape(-1, 3))

            n_colors = 5
            criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 200, 0.1)
            flags = cv2.KMEANS_RANDOM_CENTERS

            _, labels, centers = cv2.kmeans(pixels, n_colors, None, criteria, 10, flags)

            _, counts = np.unique(labels, return_counts=True)
            dominant = centers[np.argmax(counts)]

            return tuple(int(c) for c in dominant)
        except Exception as e:
            raise VisionError(
                "Failed to get dominant color",
                operation="get_dominant_color",
                details=str(e)
            )

    def compare_images(self, image1: Image.Image, image2: Image.Image) -> float:
        try:
            img1_cv = self.pil_to_cv2(image1)
            img2_cv = self.pil_to_cv2(image2)

            if img1_cv.shape != img2_cv.shape:
                img2_cv = cv2.resize(img2_cv, (img1_cv.shape[1], img1_cv.shape[0]))

            gray1 = cv2.cvtColor(img1_cv, cv2.COLOR_BGR2GRAY)
            gray2 = cv2.cvtColor(img2_cv, cv2.COLOR_BGR2GRAY)

            score = cv2.matchTemplate(gray1, gray2, cv2.TM_CCOEFF_NORMED)[0][0]
            return float(score)
        except Exception as e:
            raise VisionError(
                "Failed to compare images",
                operation="compare_images",
                details=str(e)
            )

    def find_difference(
        self, image1: Image.Image, image2: Image.Image, threshold: float = 0.1
    ) -> list[Region]:
        try:
            img1_cv = self.pil_to_cv2(image1)
            img2_cv = self.pil_to_cv2(image2)

            if img1_cv.shape != img2_cv.shape:
                img2_cv = cv2.resize(img2_cv, (img1_cv.shape[1], img1_cv.shape[0]))

            gray1 = cv2.cvtColor(img1_cv, cv2.COLOR_BGR2GRAY)
            gray2 = cv2.cvtColor(img2_cv, cv2.COLOR_BGR2GRAY)

            diff = cv2.absdiff(gray1, gray2)
            _, thresh = cv2.threshold(diff, int(threshold * 255), 255, cv2.THRESH_BINARY)

            contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            regions: list[Region] = []
            for contour in contours:
                x, y, w, h = cv2.boundingRect(contour)
                if w > 5 and h > 5:
                    regions.append(Region(x=int(x), y=int(y), width=int(w), height=int(h)))

            return regions
        except Exception as e:
            raise VisionError(
                "Failed to find difference",
                operation="find_difference",
                details=str(e)
            )

    def detect_edges(self, image: Image.Image) -> Image.Image:
        try:
            img_cv = self.pil_to_cv2(image)
            gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
            edges = cv2.Canny(gray, 100, 200)
            return self.cv2_to_pil(edges)
        except Exception as e:
            raise VisionError(
                "Failed to detect edges",
                operation="detect_edges",
                details=str(e)
            )

    def find_contours(self, image: Image.Image) -> list[Region]:
        try:
            img_cv = self.pil_to_cv2(image)
            gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
            _, binary = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY)

            contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            regions: list[Region] = []
            for contour in contours:
                x, y, w, h = cv2.boundingRect(contour)
                if w > 5 and h > 5:
                    regions.append(Region(x=int(x), y=int(y), width=int(w), height=int(h)))

            return regions
        except Exception as e:
            raise VisionError(
                "Failed to find contours",
                operation="find_contours",
                details=str(e)
            )

    async def wait_for_template(
        self,
        template: Image.Image,
        timeout: float = 10.0,
        interval: float = 0.5,
        threshold: float = 0.8
    ) -> Coordinate:
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                screenshot_result = await self._screen_capture.capture_screen_async()
                image = Image.open(__import__("io").BytesIO(screenshot_result.image_data))

                coordinates = self.find_template(image, template, threshold)
                if coordinates:
                    return coordinates[0]

                await asyncio.sleep(interval)
            except VisionError:
                await asyncio.sleep(interval)

        raise TimeoutError(f"Template not found within {timeout} seconds")

    async def wait_for_color(
        self,
        color: tuple,
        timeout: float = 10.0,
        interval: float = 0.5,
        tolerance: int = 10
    ) -> Coordinate:
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                screenshot_result = await self._screen_capture.capture_screen_async()
                image = Image.open(__import__("io").BytesIO(screenshot_result.image_data))

                coordinates = self.find_color(image, color, tolerance)
                if coordinates:
                    return coordinates[0]

                await asyncio.sleep(interval)
            except VisionError:
                await asyncio.sleep(interval)

        raise TimeoutError(f"Color {color} not found within {timeout} seconds")

    def find_all_templates(
        self,
        image: Image.Image,
        template: Image.Image,
        threshold: float = 0.8,
        min_distance: int = 10
    ) -> list[Coordinate]:
        try:
            all_coords = self.find_template(image, template, threshold)

            if not all_coords:
                return []

            filtered: list[Coordinate] = []
            for coord in all_coords:
                is_duplicate = False
                for existing in filtered:
                    distance = ((coord.x - existing.x) ** 2 + (coord.y - existing.y) ** 2) ** 0.5
                    if distance < min_distance:
                        is_duplicate = True
                        break
                if not is_duplicate:
                    filtered.append(coord)

            return filtered
        except Exception as e:
            raise VisionError(
                "Failed to find all templates",
                operation="find_all_templates",
                details=str(e)
            )

    def get_image_hash(self, image: Image.Image) -> str:
        try:
            img_cv = self.pil_to_cv2(image)
            resized = cv2.resize(img_cv, (16, 16))
            gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
            avg = gray.mean()
            binary = (gray > avg).flatten()
            return "".join(["1" if b else "0" for b in binary])
        except Exception as e:
            raise VisionError(
                "Failed to get image hash",
                operation="get_image_hash",
                details=str(e)
            )

    def calculate_ssim(self, image1: Image.Image, image2: Image.Image) -> float:
        try:
            img1_cv = self.pil_to_cv2(image1)
            img2_cv = self.pil_to_cv2(image2)

            if img1_cv.shape != img2_cv.shape:
                img2_cv = cv2.resize(img2_cv, (img1_cv.shape[1], img1_cv.shape[0]))

            gray1 = cv2.cvtColor(img1_cv, cv2.COLOR_BGR2GRAY)
            gray2 = cv2.cvtColor(img2_cv, cv2.COLOR_BGR2GRAY)

            C1 = (0.01 * 255) ** 2
            C2 = (0.03 * 255) ** 2

            mu1 = cv2.GaussianBlur(gray1, (11, 11), 1.5)
            mu2 = cv2.GaussianBlur(gray2, (11, 11), 1.5)

            mu1_sq = mu1 ** 2
            mu2_sq = mu2 ** 2
            mu1_mu2 = mu1 * mu2

            sigma1_sq = cv2.GaussianBlur(gray1 ** 2, (11, 11), 1.5) - mu1_sq
            sigma2_sq = cv2.GaussianBlur(gray2 ** 2, (11, 11), 1.5) - mu2_sq
            sigma12 = cv2.GaussianBlur(gray1 * gray2, (11, 11), 1.5) - mu1_mu2

            ssim_map = ((2 * mu1_mu2 + C1) * (2 * sigma12 + C2)) / \
                       ((mu1_sq + mu2_sq + C1) * (sigma1_sq + sigma2_sq + C2))

            return float(ssim_map.mean())
        except Exception as e:
            raise VisionError(
                "Failed to calculate SSIM",
                operation="calculate_ssim",
                details=str(e)
            )
