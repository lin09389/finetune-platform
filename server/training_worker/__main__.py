from __future__ import annotations

import argparse
import logging
import signal

from core.config import get_settings
from core.storage import APP_DB_PATH, init_storage

from .repository import TrainingEventRepositoryHub, TrainingJobRepository
from .worker import TrainingWorker


def main() -> int:
    parser = argparse.ArgumentParser(description="Finetune Platform isolated training worker")
    parser.add_argument("--db", default=APP_DB_PATH, help="SQLite application database path")
    parser.add_argument("--worker-id", default=None)
    parser.add_argument("--once", action="store_true", help="Claim at most one job and exit")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    init_storage(args.db)
    repository = TrainingJobRepository(args.db)
    worker = TrainingWorker(repository, settings=get_settings(), worker_id=args.worker_id)

    def request_stop(_signum, _frame) -> None:
        worker.stop()

    signal.signal(signal.SIGINT, request_stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, request_stop)

    if args.once:
        repository.register_worker(worker.worker_id)
        configure = TrainingEventRepositoryHub(repository)
        from core.training_events_v2 import (
            configure_training_event_hub_v2,
            reset_training_event_hub_v2,
        )
        configure_training_event_hub_v2(configure)
        try:
            worker.run_once()
        finally:
            repository.stop_worker(worker.worker_id)
            reset_training_event_hub_v2()
        return 0

    worker.run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
