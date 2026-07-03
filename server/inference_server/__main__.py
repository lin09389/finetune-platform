from __future__ import annotations

import uvicorn

from core.config import settings


def main() -> None:
    uvicorn.run(
        "server.inference_server.app:app",
        host=settings.inference_service_host,
        port=settings.inference_service_port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
