"""Compatibility shim for HuggingFace datasets.

The project stores user datasets under ``server/datasets``. When tests or the
API run with ``server`` on ``sys.path``, this directory shadows the external
``datasets`` package. Prefer the real package when it is installed; otherwise
provide a tiny in-memory fallback that supports the training loader tests and
small local workflows.
"""
from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import random
import sys
import types
from pathlib import Path
from typing import Any, Callable, Iterable


def _load_external_package() -> bool:
    current_file = Path(__file__).resolve()
    shadow_parent = current_file.parent.parent
    search_paths: list[str] = []
    for entry in sys.path:
        if not entry:
            continue
        try:
            if Path(entry).resolve() == shadow_parent:
                continue
        except OSError:
            pass
        search_paths.append(entry)

    spec = importlib.machinery.PathFinder.find_spec(__name__, search_paths)
    if spec is None or spec.loader is None or spec.origin in {None, str(current_file)}:
        return False

    module = importlib.util.module_from_spec(spec)
    sys.modules[__name__] = module
    spec.loader.exec_module(module)
    globals().update(module.__dict__)
    return True


if not _load_external_package():

    class Dataset:
        def __init__(self, rows: Iterable[dict[str, Any]]):
            self._rows = [dict(row) for row in rows]

        @classmethod
        def from_list(cls, rows: list[dict[str, Any]]) -> "Dataset":
            return cls(rows)

        @property
        def column_names(self) -> list[str]:
            names: list[str] = []
            for row in self._rows:
                for key in row:
                    if key not in names:
                        names.append(key)
            return names

        def __len__(self) -> int:
            return len(self._rows)

        def __iter__(self):
            return iter(self._rows)

        def __getitem__(self, index: int) -> dict[str, Any]:
            return self._rows[index]

        def map(
            self,
            function: Callable[..., Any],
            *,
            batched: bool = False,
            remove_columns: list[str] | None = None,
            **_: Any,
        ) -> "Dataset":
            if batched:
                batch = {name: [row.get(name) for row in self._rows] for name in self.column_names}
                mapped = function(batch)
                row_count = len(next(iter(mapped.values()), [])) if isinstance(mapped, dict) else 0
                rows = [
                    {key: values[idx] for key, values in mapped.items()}
                    for idx in range(row_count)
                ]
                return Dataset(rows)

            rows = []
            for row in self._rows:
                mapped = function(dict(row))
                if remove_columns:
                    for column in remove_columns:
                        mapped.pop(column, None)
                rows.append(mapped)
            return Dataset(rows)

        def select(self, indices: Iterable[int]) -> "Dataset":
            return Dataset([self._rows[index] for index in indices])

        def train_test_split(self, *, test_size: int | float = 0.1, seed: int = 42) -> "DatasetDict":
            count = len(self._rows)
            if isinstance(test_size, float):
                test_count = max(1, int(round(count * test_size))) if count else 0
            else:
                test_count = int(test_size)
            test_count = min(max(test_count, 0), max(count - 1, 0))
            indices = list(range(count))
            random.Random(seed).shuffle(indices)
            test_indices = set(indices[:test_count])
            train = [row for idx, row in enumerate(self._rows) if idx not in test_indices]
            test = [row for idx, row in enumerate(self._rows) if idx in test_indices]
            return DatasetDict({"train": Dataset(train), "test": Dataset(test)})


    class DatasetDict(dict):
        pass


    def load_dataset(format_name: str, *, data_files: str, split: str = "train", **_: Any) -> Dataset:
        if format_name != "json":
            raise ValueError(f"Unsupported fallback dataset format: {format_name}")
        path = Path(data_files)
        if path.suffix == ".jsonl":
            rows = [
                json.loads(line)
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        else:
            raw = json.loads(path.read_text(encoding="utf-8"))
            rows = raw if isinstance(raw, list) else [raw]
        return Dataset.from_list(rows)


    def interleave_datasets(
        datasets: list[Dataset],
        probabilities: list[float] | None = None,
        seed: int = 42,
        **_: Any,
    ) -> Dataset:
        del probabilities, seed
        rows: list[dict[str, Any]] = []
        for dataset in datasets:
            rows.extend(list(dataset))
        return Dataset(rows)


    def _disable_progress_bar() -> None:
        return None


    utils = types.ModuleType("datasets.utils")
    logging = types.ModuleType("datasets.utils.logging")
    logging.disable_progress_bar = _disable_progress_bar
    utils.logging = logging
    sys.modules.setdefault("datasets.utils", utils)
    sys.modules.setdefault("datasets.utils.logging", logging)

    __all__ = ["Dataset", "DatasetDict", "load_dataset", "interleave_datasets"]
