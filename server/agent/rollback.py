"""
操作回滚管理器 - 支持操作快照和回滚
"""
import json
import logging
import shutil
import uuid
from contextlib import suppress
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class RollbackStatus(str, Enum):
    PENDING = "pending"
    EXECUTED = "executed"
    ROLLED_BACK = "rolled_back"
    EXPIRED = "expired"
    FAILED = "failed"


@dataclass
class RollbackOperation:
    operation_type: str
    params: dict[str, Any]
    description: str


@dataclass
class OperationSnapshot:
    id: str
    action: str
    params: dict[str, Any]
    timestamp: str
    before_state: dict[str, Any]
    after_state: dict[str, Any] | None
    rollback_operations: list[dict[str, Any]]
    rollback_deadline: str
    status: str
    is_reversible: bool
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OperationSnapshot":
        return cls(**data)


class RollbackManager:
    ROLLBACK_WINDOW_HOURS = 24
    MAX_SNAPSHOTS = 100
    SNAPSHOT_DIR = "data/snapshots"

    NON_REVERSIBLE_ACTIONS = {
        "file_delete_permanent",
        "format_disk",
        "system_shutdown",
    }

    def __init__(self, snapshot_dir: str | None = None):
        self.snapshot_dir = Path(snapshot_dir or self.SNAPSHOT_DIR)
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        self.index_file = self.snapshot_dir / "index.json"
        self._index: dict[str, dict[str, Any]] = {}
        self._load_index()

    def _load_index(self):
        if self.index_file.exists():
            try:
                with open(self.index_file, encoding="utf-8") as f:
                    self._index = json.load(f)
            except Exception as e:
                logger.warning(f"加载快照索引失败: {e}")
                self._index = {}

    def _save_index(self):
        try:
            with open(self.index_file, "w", encoding="utf-8") as f:
                json.dump(self._index, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存快照索引失败: {e}")

    def _generate_id(self) -> str:
        return f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"

    def _get_snapshot_path(self, snapshot_id: str) -> Path:
        return self.snapshot_dir / f"{snapshot_id}.json"

    def is_reversible(self, action: str) -> bool:
        return action not in self.NON_REVERSIBLE_ACTIONS

    async def create_snapshot(
        self,
        action: str,
        params: dict[str, Any],
        before_state: dict[str, Any] | None = None,
    ) -> OperationSnapshot:
        snapshot_id = self._generate_id()
        deadline = datetime.now() + timedelta(hours=self.ROLLBACK_WINDOW_HOURS)

        rollback_ops = self._generate_rollback_operations(action, params)

        if before_state is None:
            before_state = await self._capture_before_state(action, params)

        snapshot = OperationSnapshot(
            id=snapshot_id,
            action=action,
            params=params,
            timestamp=datetime.now().isoformat(),
            before_state=before_state,
            after_state=None,
            rollback_operations=rollback_ops,
            rollback_deadline=deadline.isoformat(),
            status=RollbackStatus.PENDING.value,
            is_reversible=self.is_reversible(action),
        )

        await self._save_snapshot(snapshot)
        self._index[snapshot_id] = {
            "action": action,
            "timestamp": snapshot.timestamp,
            "status": snapshot.status,
            "is_reversible": snapshot.is_reversible,
        }
        self._save_index()
        self._cleanup_old_snapshots()

        logger.info(f"创建操作快照: {snapshot_id}, 操作: {action}")
        return snapshot

    async def _capture_before_state(
        self, action: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        state = {}

        try:
            if action in ["file_write", "file_delete", "file_move", "file_rename"]:
                file_path = params.get("file_path") or params.get("source")
                if file_path and Path(file_path).exists():
                    state["file_exists"] = True
                    state["file_path"] = str(file_path)
                    stat = Path(file_path).stat()
                    state["file_size"] = stat.st_size
                    state["file_modified"] = datetime.fromtimestamp(
                        stat.st_mtime
                    ).isoformat()

                    if action == "file_write" and Path(file_path).is_file():
                        backup_path = self.snapshot_dir / f"backup_{uuid.uuid4().hex[:8]}_{Path(file_path).name}"
                        shutil.copy2(file_path, backup_path)
                        state["backup_path"] = str(backup_path)

            elif action in ["directory_delete", "directory_move"]:
                dir_path = params.get("directory") or params.get("source")
                if dir_path and Path(dir_path).exists():
                    state["dir_exists"] = True
                    state["dir_path"] = str(dir_path)
                    items = list(Path(dir_path).iterdir())
                    state["item_count"] = len(items)

            elif action == "clipboard_write":
                try:
                    import pyperclip
                    state["previous_clipboard"] = pyperclip.paste()
                except Exception:
                    pass

        except Exception as e:
            logger.warning(f"捕获操作前状态失败: {e}")

        return state

    def _generate_rollback_operations(
        self, action: str, params: dict[str, Any]
    ) -> list[dict[str, Any]]:
        ops = []

        if action == "file_write":
            file_path = params.get("file_path")
            if file_path:
                ops.append({
                    "type": "file_restore",
                    "params": {"file_path": file_path},
                    "description": f"恢复文件: {file_path}",
                })

        elif action == "file_delete":
            file_path = params.get("file_path")
            if file_path:
                ops.append({
                    "type": "file_restore_from_backup",
                    "params": {"file_path": file_path},
                    "description": f"从备份恢复文件: {file_path}",
                })

        elif action == "file_move":
            source = params.get("source")
            destination = params.get("destination")
            if source and destination:
                ops.append({
                    "type": "file_move",
                    "params": {"source": destination, "destination": source},
                    "description": f"移动回原位置: {destination} -> {source}",
                })

        elif action == "file_rename":
            source = params.get("source")
            new_name = params.get("new_name")
            if source and new_name:
                old_name = Path(source).name
                new_path = Path(source).parent / new_name
                ops.append({
                    "type": "file_rename",
                    "params": {"source": str(new_path), "new_name": old_name},
                    "description": f"重命名回原名: {new_name} -> {old_name}",
                })

        elif action == "clipboard_write":
            ops.append({
                "type": "clipboard_write",
                "params": {"content": "{previous_clipboard}"},
                "description": "恢复剪贴板内容",
            })

        elif action == "directory_delete":
            dir_path = params.get("directory")
            if dir_path:
                ops.append({
                    "type": "directory_restore_from_backup",
                    "params": {"directory": dir_path},
                    "description": f"从备份恢复目录: {dir_path}",
                })

        return ops

    async def _save_snapshot(self, snapshot: OperationSnapshot):
        path = self._get_snapshot_path(snapshot.id)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(snapshot.to_dict(), f, ensure_ascii=False, indent=2)

    async def update_after_state(
        self, snapshot_id: str, after_state: dict[str, Any], success: bool = True
    ):
        snapshot = await self.get_snapshot(snapshot_id)
        if snapshot:
            snapshot.after_state = after_state
            snapshot.status = RollbackStatus.EXECUTED.value if success else RollbackStatus.FAILED.value
            await self._save_snapshot(snapshot)
            self._index[snapshot_id]["status"] = snapshot.status
            self._save_index()

    async def get_snapshot(self, snapshot_id: str) -> OperationSnapshot | None:
        path = self._get_snapshot_path(snapshot_id)
        if path.exists():
            with open(path, encoding="utf-8") as f:
                return OperationSnapshot.from_dict(json.load(f))
        return None

    async def get_rollbackable_operations(self) -> list[OperationSnapshot]:
        snapshots = []
        now = datetime.now()

        for snapshot_id, meta in self._index.items():
            if meta.get("status") == RollbackStatus.EXECUTED.value and meta.get(
                "is_reversible", True
            ):
                snapshot = await self.get_snapshot(snapshot_id)
                if snapshot:
                    deadline = datetime.fromisoformat(snapshot.rollback_deadline)
                    if deadline > now:
                        snapshots.append(snapshot)

        return sorted(snapshots, key=lambda s: s.timestamp, reverse=True)

    async def rollback(self, snapshot_id: str) -> dict[str, Any]:
        snapshot = await self.get_snapshot(snapshot_id)
        if not snapshot:
            return {"success": False, "error": "快照不存在"}

        if not snapshot.is_reversible:
            return {"success": False, "error": "此操作不可回滚"}

        deadline = datetime.fromisoformat(snapshot.rollback_deadline)
        if datetime.now() > deadline:
            snapshot.status = RollbackStatus.EXPIRED.value
            await self._save_snapshot(snapshot)
            return {"success": False, "error": "回滚窗口已过期"}

        if snapshot.status != RollbackStatus.EXECUTED.value:
            return {"success": False, "error": f"操作状态不允许回滚: {snapshot.status}"}

        results = []
        errors = []

        for rollback_op in reversed(snapshot.rollback_operations):
            try:
                result = await self._execute_rollback_operation(
                    rollback_op, snapshot.before_state
                )
                results.append({"operation": rollback_op["type"], "success": True, "result": result})
            except Exception as e:
                errors.append({"operation": rollback_op["type"], "error": str(e)})
                logger.error(f"回滚操作失败: {rollback_op['type']}, 错误: {e}")

        snapshot.status = RollbackStatus.ROLLED_BACK.value
        await self._save_snapshot(snapshot)
        self._index[snapshot_id]["status"] = snapshot.status
        self._save_index()

        logger.info(f"操作已回滚: {snapshot_id}")

        return {
            "success": len(errors) == 0,
            "snapshot_id": snapshot_id,
            "results": results,
            "errors": errors,
        }

    async def _execute_rollback_operation(
        self, rollback_op: dict[str, Any], before_state: dict[str, Any]
    ) -> dict[str, Any]:
        op_type = rollback_op["type"]
        params = rollback_op["params"].copy()

        for key, value in params.items():
            if isinstance(value, str) and value.startswith("{") and value.endswith("}"):
                state_key = value[1:-1]
                if state_key in before_state:
                    params[key] = before_state[state_key]

        if op_type == "file_restore":
            file_path = params.get("file_path")
            backup_path = before_state.get("backup_path")

            if backup_path and Path(backup_path).exists():
                shutil.copy2(backup_path, file_path)
                return {"restored_from": backup_path}
            elif not before_state.get("file_exists"):
                if Path(file_path).exists():
                    Path(file_path).unlink()
                return {"action": "deleted", "reason": "file did not exist before"}
            else:
                return {"action": "skipped", "reason": "no backup available"}

        elif op_type == "file_move":
            source = params.get("source")
            destination = params.get("destination")
            if source and destination and Path(source).exists():
                shutil.move(source, destination)
                return {"moved": f"{source} -> {destination}"}
            return {"action": "skipped", "reason": "source not found"}

        elif op_type == "file_rename":
            source = params.get("source")
            new_name = params.get("new_name")
            if source and new_name and Path(source).exists():
                new_path = Path(source).parent / new_name
                Path(source).rename(new_path)
                return {"renamed": f"{Path(source).name} -> {new_name}"}
            return {"action": "skipped", "reason": "source not found"}

        elif op_type == "clipboard_write":
            content = params.get("content", "")
            try:
                import pyperclip
                pyperclip.copy(content)
                return {"action": "clipboard_restored"}
            except Exception:
                return {"action": "skipped", "reason": "pyperclip not available"}

        elif op_type == "directory_restore_from_backup":
            return {"action": "skipped", "reason": "directory restore not implemented"}

        return {"action": "unknown", "type": op_type}

    def _cleanup_old_snapshots(self):
        if len(self._index) <= self.MAX_SNAPSHOTS:
            return

        sorted_ids = sorted(
            self._index.keys(),
            key=lambda x: self._index[x].get("timestamp", ""),
        )

        for old_id in sorted_ids[: len(sorted_ids) - self.MAX_SNAPSHOTS]:
            self._delete_snapshot(old_id)

    def _delete_snapshot(self, snapshot_id: str):
        path = self._get_snapshot_path(snapshot_id)
        if path.exists():
            path.unlink()

        snapshot = self._index.get(snapshot_id, {})
        backup_path = snapshot.get("before_state", {}).get("backup_path")
        if backup_path and Path(backup_path).exists():
            with suppress(Exception):
                Path(backup_path).unlink()

        if snapshot_id in self._index:
            del self._index[snapshot_id]

        self._save_index()
        logger.info(f"清理过期快照: {snapshot_id}")


_rollback_manager: RollbackManager | None = None


def get_rollback_manager() -> RollbackManager:
    global _rollback_manager
    if _rollback_manager is None:
        _rollback_manager = RollbackManager()
    return _rollback_manager
