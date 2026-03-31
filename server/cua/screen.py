import base64
import io

import mss
from PIL import Image

from .exceptions import MonitorNotFoundError, ScreenshotError
from .models import Coordinate, Region, ScreenshotResult


class ScreenCapture:
    def __init__(self):
        self._mss = None

    def _get_mss(self):
        if self._mss is None:
            self._mss = mss.mss()
        return self._mss

    def _close_mss(self):
        if self._mss is not None:
            self._mss.close()
            self._mss = None

    def get_monitor_count(self) -> int:
        with mss.mss() as sct:
            return len(sct.monitors) - 1

    def get_screen_size(self, monitor: int = 0) -> Coordinate:
        with mss.mss() as sct:
            if monitor < 0 or monitor >= len(sct.monitors) - 1:
                raise MonitorNotFoundError(monitor, len(sct.monitors) - 1)
            mon = sct.monitors[monitor + 1]
            return Coordinate(x=mon["width"], y=mon["height"])

    def capture_screen(self, monitor: int = 0) -> ScreenshotResult:
        try:
            with mss.mss() as sct:
                if monitor < 0 or monitor >= len(sct.monitors) - 1:
                    raise MonitorNotFoundError(monitor, len(sct.monitors) - 1)

                monitor_config = sct.monitors[monitor + 1]
                screenshot = sct.grab(monitor_config)

                image = Image.frombytes(
                    "RGB", screenshot.size, screenshot.bgra, "raw", "BGRX"
                )

                image_data = self.to_bytes(image)
                base64_data = self.to_base64(image)

                return ScreenshotResult(
                    image_data=image_data,
                    width=screenshot.size[0],
                    height=screenshot.size[1],
                    format="PNG",
                    base64=base64_data,
                    monitor_index=monitor,
                    region=None,
                )
        except mss.ScreenShotError as e:
            raise ScreenshotError(f"Failed to capture screen {monitor}", e)
        except MonitorNotFoundError:
            raise
        except Exception as e:
            raise ScreenshotError("Unexpected error during screen capture", e)

    def capture_region(self, region: Region) -> ScreenshotResult:
        try:
            with mss.mss() as sct:
                mss_region = region.to_mss_dict()
                screenshot = sct.grab(mss_region)

                image = Image.frombytes(
                    "RGB", screenshot.size, screenshot.bgra, "raw", "BGRX"
                )

                image_data = self.to_bytes(image)
                base64_data = self.to_base64(image)

                return ScreenshotResult(
                    image_data=image_data,
                    width=screenshot.size[0],
                    height=screenshot.size[1],
                    format="PNG",
                    base64=base64_data,
                    monitor_index=0,
                    region=region,
                )
        except mss.ScreenShotError as e:
            raise ScreenshotError(
                f"Failed to capture region {region.x},{region.y}", e
            )
        except Exception as e:
            raise ScreenshotError(
                "Unexpected error during region capture", e
            )

    def capture_all_monitors(self) -> list[ScreenshotResult]:
        results: list[ScreenshotResult] = []
        monitor_count = self.get_monitor_count()

        for i in range(monitor_count):
            try:
                result = self.capture_screen(i)
                results.append(result)
            except ScreenshotError:
                continue

        return results

    def to_base64(
        self, image: Image.Image, format: str = "PNG", quality: int = 85
    ) -> str:
        buffer = io.BytesIO()
        save_kwargs = {"format": format}
        if format.upper() == "JPEG":
            save_kwargs["quality"] = quality

        image.save(buffer, **save_kwargs)
        buffer.seek(0)
        return base64.b64encode(buffer.read()).decode("utf-8")

    def to_bytes(
        self, image: Image.Image, format: str = "PNG", quality: int = 85
    ) -> bytes:
        buffer = io.BytesIO()
        save_kwargs = {"format": format}
        if format.upper() == "JPEG":
            save_kwargs["quality"] = quality

        image.save(buffer, **save_kwargs)
        buffer.seek(0)
        return buffer.read()

    async def capture_screen_async(self, monitor: int = 0) -> ScreenshotResult:
        return self.capture_screen(monitor)

    async def capture_region_async(self, region: Region) -> ScreenshotResult:
        return self.capture_region(region)

    async def capture_all_monitors_async(self) -> list[ScreenshotResult]:
        return self.capture_all_monitors()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._close_mss()
        return False
