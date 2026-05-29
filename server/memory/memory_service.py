"""Filesystem-backed long-term memory service.

DeepAgents treats durable memory as files. This module mirrors that model for
the local platform while keeping a small compatibility surface for context
retrieval and chat auto-extraction.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import re
import threading
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.storage import MemoryRepository

from .models import MEMORY_IMPORTANCE, MEMORY_TYPE_LABELS, MemoryScope, MemorySearchResult, MemoryType

logger = logging.getLogger(__name__)


DEFAULT_USER_ID = "default"
DEFAULT_AGENT_ID = "build"
DEFAULT_ORG_ID = "default-org"
DEFAULT_MEMORY_ROOT = Path("data/deep_memory")

USER_MEMORY_FILES = {
    "preferences.md": "# Preferences\n\n",
    "facts.md": "# Facts\n\n",
    "projects.md": "# Projects\n\n",
}
AGENT_MEMORY_FILES = {"AGENTS.md": "# Agent Memory\n\n"}
ORG_POLICY_FILES = {"compliance.md": "# Compliance Policies\n\n"}

TYPE_TO_FILE = {
    MemoryType.PERSONAL.value: "preferences.md",
    MemoryType.PREFERENCE.value: "preferences.md",
    MemoryType.HABIT.value: "preferences.md",
    MemoryType.PROJECT.value: "projects.md",
    MemoryType.SKILL.value: "projects.md",
    MemoryType.KNOWLEDGE.value: "facts.md",
    MemoryType.HISTORY.value: "facts.md",
}


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _checksum(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _safe_segment(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value or "").strip())
    return cleaned.strip(".-") or "default"


def encode_file_id(scope: str, namespace: str, relative_path: str) -> str:
    raw = json.dumps([scope, namespace, relative_path], ensure_ascii=False, separators=(",", ":"))
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")


def decode_file_id(file_id: str) -> tuple[MemoryScope, str, str]:
    padded = file_id + "=" * (-len(file_id) % 4)
    try:
        scope, namespace, relative_path = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
        return MemoryScope(scope), _safe_segment(namespace), str(relative_path)
    except Exception as exc:
        raise ValueError("Invalid memory file id") from exc


class MemoryNamespaceResolver:
    """Resolve scope/namespace pairs into local filesystem directories."""

    def __init__(self, root_dir: str | Path = DEFAULT_MEMORY_ROOT):
        self.root_dir = Path(root_dir)

    def root_for(self, scope: str | MemoryScope, namespace: str) -> Path:
        scope_value = MemoryScope(scope)
        namespace = _safe_segment(namespace)
        if scope_value == MemoryScope.USER:
            return self.root_dir / "users" / namespace
        if scope_value == MemoryScope.AGENT:
            return self.root_dir / "agents" / namespace
        if scope_value == MemoryScope.ORG:
            return self.root_dir / "orgs" / namespace
        raise ValueError(f"Unsupported memory scope: {scope}")

    def files_dir_for(self, scope: str | MemoryScope, namespace: str) -> Path:
        base = self.root_for(scope, namespace)
        scope_value = MemoryScope(scope)
        if scope_value == MemoryScope.USER:
            return base / "memories"
        if scope_value == MemoryScope.AGENT:
            return base / "memories"
        return base / "policies"

    def episodes_dir_for(self, user_id: str) -> Path:
        return self.root_for(MemoryScope.USER, user_id) / "episodes"


class MemoryFileStore:
    """Manage memory files and sidecar metadata."""

    def __init__(self, root_dir: str | Path = DEFAULT_MEMORY_ROOT):
        self.resolver = MemoryNamespaceResolver(root_dir)
        self._lock = threading.RLock()

    @property
    def root_dir(self) -> Path:
        return self.resolver.root_dir

    def ensure_namespace(self, scope: str | MemoryScope, namespace: str) -> None:
        scope_value = MemoryScope(scope)
        files = self._default_files(scope_value)
        with self._lock:
            files_dir = self.resolver.files_dir_for(scope_value, namespace)
            files_dir.mkdir(parents=True, exist_ok=True)
            if scope_value == MemoryScope.USER:
                self.resolver.episodes_dir_for(namespace).mkdir(parents=True, exist_ok=True)
            for name, seed in files.items():
                path = files_dir / name
                if not path.exists():
                    path.write_text(seed, encoding="utf-8")
                self._write_meta_if_missing(path, scope_value, _safe_segment(namespace), writable=scope_value != MemoryScope.ORG)

    def list_files(self, scope: str | MemoryScope, namespace: str) -> list[dict[str, Any]]:
        scope_value = MemoryScope(scope)
        namespace = _safe_segment(namespace)
        self.ensure_namespace(scope_value, namespace)
        files_dir = self.resolver.files_dir_for(scope_value, namespace)
        files = sorted(path for path in files_dir.rglob("*.md") if path.is_file() and not path.name.endswith(".meta.md"))
        return [self.read_file_by_path(scope_value, namespace, path.relative_to(files_dir).as_posix()) for path in files]

    def read_file(self, file_id: str) -> dict[str, Any]:
        scope, namespace, relative_path = decode_file_id(file_id)
        return self.read_file_by_path(scope, namespace, relative_path)

    def read_file_by_path(self, scope: str | MemoryScope, namespace: str, relative_path: str) -> dict[str, Any]:
        scope_value = MemoryScope(scope)
        namespace = _safe_segment(namespace)
        path = self._resolve_file_path(scope_value, namespace, relative_path)
        self.ensure_namespace(scope_value, namespace)
        if not path.exists():
            raise FileNotFoundError(relative_path)
        content = path.read_text(encoding="utf-8")
        meta = self._read_or_repair_meta(path, scope_value, namespace)
        return {
            "id": encode_file_id(scope_value.value, namespace, relative_path),
            "path": self._virtual_path(scope_value, relative_path),
            "relative_path": relative_path,
            "scope": scope_value.value,
            "namespace": namespace,
            "content": content,
            "writable": bool(meta.get("writable", scope_value != MemoryScope.ORG)),
            "version": int(meta.get("version", 1) or 1),
            "updated_at": meta.get("updated_at") or _utcnow(),
            "metadata": meta.get("metadata", {}) or {},
        }

    def write_file(self, file_id: str, content: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        scope, namespace, relative_path = decode_file_id(file_id)
        return self.write_file_by_path(scope, namespace, relative_path, content, metadata=metadata)

    def write_file_by_path(
        self,
        scope: str | MemoryScope,
        namespace: str,
        relative_path: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        scope_value = MemoryScope(scope)
        if scope_value == MemoryScope.ORG:
            raise PermissionError("Organization memory is read-only")
        namespace = _safe_segment(namespace)
        with self._lock:
            self.ensure_namespace(scope_value, namespace)
            path = self._resolve_file_path(scope_value, namespace, relative_path)
            old_meta = self._read_or_repair_meta(path, scope_value, namespace) if path.exists() else {}
            if old_meta and old_meta.get("writable") is False:
                raise PermissionError("Memory file is read-only")
            path.parent.mkdir(parents=True, exist_ok=True)
            previous = path.read_text(encoding="utf-8") if path.exists() else ""
            path.write_text(content, encoding="utf-8")
            merged_metadata = dict(old_meta.get("metadata", {}) or {})
            if metadata:
                merged_metadata.update(metadata)
            version = int(old_meta.get("version", 0) or 0) + (0 if _checksum(previous) == _checksum(content) else 1)
            meta = self._write_meta(path, scope_value, namespace, writable=True, version=max(1, version), metadata=merged_metadata)
            return self.read_file_by_path(scope_value, namespace, relative_path) | {"version": meta["version"]}

    def append_bullet(
        self,
        user_id: str,
        memory_type: str,
        content: str,
        *,
        source: str = "hot_path",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        target = TYPE_TO_FILE.get(memory_type, "facts.md")
        current = self.read_file_by_path(MemoryScope.USER, user_id, target)
        bullet = f"- {content.strip()}"
        existing = {line.strip() for line in current["content"].splitlines()}
        if bullet in existing:
            return current
        body = current["content"].rstrip() + "\n" + bullet + "\n"
        return self.write_file_by_path(
            MemoryScope.USER,
            user_id,
            target,
            body,
            metadata={"last_source": source, **(metadata or {})},
        )

    def _default_files(self, scope: MemoryScope) -> dict[str, str]:
        if scope == MemoryScope.USER:
            return USER_MEMORY_FILES
        if scope == MemoryScope.AGENT:
            return AGENT_MEMORY_FILES
        return ORG_POLICY_FILES

    def _resolve_file_path(self, scope: MemoryScope, namespace: str, relative_path: str) -> Path:
        if ".." in Path(relative_path).parts or Path(relative_path).is_absolute():
            raise ValueError("Invalid memory path")
        if not relative_path.endswith(".md"):
            raise ValueError("Memory files must be Markdown")
        root = self.resolver.files_dir_for(scope, namespace).resolve()
        path = (root / relative_path).resolve()
        if root != path and root not in path.parents:
            raise ValueError("Memory path escapes namespace")
        return path

    def _meta_path(self, path: Path) -> Path:
        return path.with_name(f"{path.name}.meta.json")

    def _virtual_path(self, scope: MemoryScope, relative_path: str) -> str:
        if scope == MemoryScope.USER:
            return f"/memories/{relative_path}"
        if scope == MemoryScope.AGENT:
            return f"/agent-memory/{relative_path}"
        return f"/policies/{relative_path}"

    def _write_meta_if_missing(self, path: Path, scope: MemoryScope, namespace: str, writable: bool) -> None:
        if not self._meta_path(path).exists():
            self._write_meta(path, scope, namespace, writable=writable, version=1)

    def _read_or_repair_meta(self, path: Path, scope: MemoryScope, namespace: str) -> dict[str, Any]:
        meta_path = self._meta_path(path)
        if meta_path.exists():
            try:
                return json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                logger.warning("Invalid memory metadata, repairing: %s", meta_path)
        return self._write_meta(path, scope, namespace, writable=scope != MemoryScope.ORG, version=1)

    def _write_meta(
        self,
        path: Path,
        scope: MemoryScope,
        namespace: str,
        *,
        writable: bool,
        version: int,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        content = path.read_text(encoding="utf-8") if path.exists() else ""
        meta = {
            "scope": scope.value,
            "namespace": namespace,
            "path": self._virtual_path(scope, path.name),
            "writable": writable,
            "updated_at": _utcnow(),
            "version": version,
            "checksum": _checksum(content),
            "metadata": metadata or {},
        }
        self._meta_path(path).write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        return meta


class MemorySearchService:
    def __init__(self, store: MemoryFileStore):
        self.store = store

    def search(
        self,
        query: str,
        *,
        scope: str | None = None,
        namespace: str | None = None,
        user_id: str = DEFAULT_USER_ID,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        query = (query or "").strip()
        if not query:
            return []
        scopes = [MemoryScope(scope)] if scope else [MemoryScope.USER, MemoryScope.AGENT, MemoryScope.ORG]
        matches: list[MemorySearchResult] = []
        for scope_value in scopes:
            ns = namespace or self._default_namespace(scope_value, user_id)
            for file in self.store.list_files(scope_value, ns):
                score, snippet = self._score_file(query, file["content"])
                if score > 0:
                    matches.append(
                        MemorySearchResult(
                            file_id=file["id"],
                            path=file["path"],
                            scope=scope_value,
                            namespace=file["namespace"],
                            snippet=snippet,
                            score=score,
                            updated_at=file["updated_at"],
                            metadata=file["metadata"],
                        )
                    )
        matches.sort(key=lambda item: item.score, reverse=True)
        return [{**asdict(item), "scope": item.scope.value} for item in matches[:top_k]]

    def _default_namespace(self, scope: MemoryScope, user_id: str) -> str:
        if scope == MemoryScope.USER:
            return user_id
        if scope == MemoryScope.AGENT:
            return DEFAULT_AGENT_ID
        return DEFAULT_ORG_ID

    def _score_file(self, query: str, content: str) -> tuple[float, str]:
        lowered = content.lower()
        terms = [term for term in re.split(r"\s+", query.lower()) if term]
        hits = sum(1 for term in terms if term in lowered)
        if query.lower() in lowered:
            hits += 3
        if hits <= 0:
            return 0.0, ""
        first_index = min((lowered.find(term) for term in terms if term in lowered), default=0)
        start = max(0, first_index - 80)
        end = min(len(content), first_index + 180)
        snippet = content[start:end].strip()
        return min(1.0, hits / max(1, len(terms) + 3)), snippet


class MemoryConsolidator:
    def __init__(self, store: MemoryFileStore):
        self.store = store

    def consolidate(self, user_id: str = DEFAULT_USER_ID, session_id: str | None = None) -> dict[str, Any]:
        events = self.list_episodes(user_id=user_id, session_id=session_id)
        learned = 0
        for event in events:
            content = str(event.get("content") or "")
            extracted = extract_hot_path_memories(content)
            for memory in extracted:
                self.store.append_bullet(user_id, memory["type"], memory["content"], source="consolidation", metadata={"session_id": event.get("session_id")})
                learned += 1
        return {"user_id": user_id, "session_id": session_id, "episodes_scanned": len(events), "memories_written": learned}

    def record_episode(
        self,
        user_id: str,
        session_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        events_dir = self.store.resolver.episodes_dir_for(user_id)
        events_dir.mkdir(parents=True, exist_ok=True)
        event = {
            "session_id": session_id,
            "role": role,
            "content": content,
            "created_at": _utcnow(),
            "metadata": metadata or {},
        }
        with (events_dir / f"{_safe_segment(session_id)}.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")
        return event

    def list_episodes(self, user_id: str = DEFAULT_USER_ID, session_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        events_dir = self.store.resolver.episodes_dir_for(user_id)
        if not events_dir.exists():
            return []
        files = [events_dir / f"{_safe_segment(session_id)}.jsonl"] if session_id else sorted(events_dir.glob("*.jsonl"))
        events: list[dict[str, Any]] = []
        for path in files:
            if not path.exists():
                continue
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        events.sort(key=lambda item: item.get("created_at", ""))
        return events[-limit:]


def extract_hot_path_memories(message: str) -> list[dict[str, Any]]:
    text = (message or "").strip()
    if not text:
        return []
    triggers = ("记住", "记得", "别忘了", "以后", "我偏好", "我喜欢", "我习惯", "remember", "prefer")
    if not any(trigger.lower() in text.lower() for trigger in triggers):
        return []
    memory_type = MemoryType.KNOWLEDGE.value
    if any(token in text for token in ("偏好", "喜欢", "习惯", "以后")) or "prefer" in text.lower():
        memory_type = MemoryType.PREFERENCE.value
    if "项目" in text or "开发" in text:
        memory_type = MemoryType.PROJECT.value
    cleaned = re.sub(r"^(请)?(帮我)?(记住|记得|别忘了)[:：,，\s]*", "", text, flags=re.IGNORECASE).strip()
    return [
        {
            "id": f"mem_{uuid.uuid4().hex[:8]}",
            "content": cleaned[:300],
            "type": memory_type,
            "importance": MEMORY_IMPORTANCE.get(MemoryType(memory_type), 0.5),
            "source": "hot_path",
        }
    ]


class MemoryService:
    """Facade for file-backed memory with compatibility methods."""

    def __init__(self, root_dir: str | Path = DEFAULT_MEMORY_ROOT, vector_db_path: str | None = None):
        _ = vector_db_path
        self.store = MemoryFileStore(root_dir)
        self.search_service = MemorySearchService(self.store)
        self.consolidator = MemoryConsolidator(self.store)
        self.repository = MemoryRepository()
        self.store.ensure_namespace(MemoryScope.USER, DEFAULT_USER_ID)
        self.store.ensure_namespace(MemoryScope.AGENT, DEFAULT_AGENT_ID)
        self.store.ensure_namespace(MemoryScope.ORG, DEFAULT_ORG_ID)
        logger.info("File-backed memory service initialized at %s", self.store.root_dir)

    def list_files(self, scope: str = "user", namespace: str = DEFAULT_USER_ID) -> list[dict[str, Any]]:
        return self.store.list_files(scope, namespace)

    def get_file(self, file_id: str) -> dict[str, Any]:
        return self.store.read_file(file_id)

    def update_file(self, file_id: str, content: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.store.write_file(file_id, content, metadata=metadata)

    def search_files(
        self,
        query: str,
        *,
        scope: str | None = None,
        namespace: str | None = None,
        user_id: str = DEFAULT_USER_ID,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        return self.search_service.search(query, scope=scope, namespace=namespace, user_id=user_id, top_k=top_k)

    def consolidate(self, user_id: str = DEFAULT_USER_ID, session_id: str | None = None) -> dict[str, Any]:
        return self.consolidator.consolidate(user_id=user_id, session_id=session_id)

    def list_episodes(self, user_id: str = DEFAULT_USER_ID, session_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        return self.consolidator.list_episodes(user_id=user_id, session_id=session_id, limit=limit)

    def migrate_from_items(self, user_id: str = DEFAULT_USER_ID) -> dict[str, Any]:
        migrated: list[dict[str, Any]] = []
        skipped = 0
        for item in self.repository.list(user_id=user_id, limit=100000):
            before = {file["relative_path"]: file["content"] for file in self.list_files("user", user_id)}
            target = TYPE_TO_FILE.get(str(item.get("type") or ""), "facts.md")
            self.store.append_bullet(
                user_id,
                str(item.get("type") or MemoryType.KNOWLEDGE.value),
                str(item.get("content") or ""),
                source="migration",
                metadata={"migrated_from": "memory_items"},
            )
            after = self.store.read_file_by_path(MemoryScope.USER, user_id, target)["content"]
            if before.get(target) == after:
                skipped += 1
            else:
                migrated.append({"id": item.get("id"), "type": item.get("type"), "target": target})
        return {"user_id": user_id, "migrated": len(migrated), "skipped": skipped, "items": migrated}

    # Internal compatibility methods.
    def extract_and_store(self, message: str, role: str, user_id: str = DEFAULT_USER_ID) -> list[dict[str, Any]]:
        if role != "user":
            return []
        stored = []
        session_id = f"hot_path_{datetime.now(timezone.utc).strftime('%Y%m%d')}"
        self.consolidator.record_episode(user_id, session_id, role, message, {"source": "chat"})
        for memory in extract_hot_path_memories(message):
            file_record = self.store.append_bullet(user_id, memory["type"], memory["content"], source=memory.get("source", "hot_path"))
            stored.append({"id": file_record["id"], "content": memory["content"], "type": memory["type"]})
        return stored

    def recall(
        self,
        query: str,
        user_id: str = DEFAULT_USER_ID,
        top_k: int = 5,
        memory_type: str | None = None,
    ) -> list[dict[str, Any]]:
        scope = "user"
        results = self.search_files(query, scope=scope, namespace=user_id, user_id=user_id, top_k=top_k)
        if memory_type:
            target = TYPE_TO_FILE.get(memory_type)
            results = [result for result in results if not target or result["path"].endswith(target)]
        memories = []
        for result in results:
            memories.append(
                {
                    "id": result["file_id"],
                    "user_id": user_id,
                    "content": result["snippet"],
                    "type": memory_type or self._type_from_path(result["path"]),
                    "importance": 0.5,
                    "source": "file_memory",
                    "created_at": result["updated_at"],
                    "updated_at": result["updated_at"],
                    "access_count": 0,
                    "metadata": {"path": result["path"], **(result.get("metadata") or {})},
                    "vector_state": "not_applicable",
                    "storage_mode": "file",
                    "relevance": result["score"],
                }
            )
        return memories

    def list_memories(self, user_id: str = DEFAULT_USER_ID, memory_type: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        files = self.list_files("user", user_id)
        if memory_type:
            target = TYPE_TO_FILE.get(memory_type)
            files = [file for file in files if not target or file["relative_path"] == target]
        return [
            {
                "id": file["id"],
                "user_id": user_id,
                "content": file["content"],
                "type": self._type_from_path(file["path"]),
                "importance": 0.5,
                "source": "file_memory",
                "created_at": file["updated_at"],
                "updated_at": file["updated_at"],
                "access_count": 0,
                "metadata": file["metadata"],
                "vector_state": "not_applicable",
                "storage_mode": "file",
            }
            for file in files[:limit]
        ]

    def get_stats(self, user_id: str = DEFAULT_USER_ID) -> dict[str, Any]:
        files = self.list_files("user", user_id)
        episodes = self.list_episodes(user_id=user_id, limit=100000)
        return {
            "total_files": len(files),
            "total_memories": len(files),
            "episode_events": len(episodes),
            "storage_mode": "filesystem",
            "root": str(self.store.root_dir),
        }

    def get_user_summary(self, user_id: str = DEFAULT_USER_ID) -> dict[str, Any]:
        files = self.list_files("user", user_id)
        return {
            "total_count": len(files),
            "files": [{"path": file["path"], "updated_at": file["updated_at"], "version": file["version"]} for file in files],
            "recent_memories": files,
        }

    def get_context_with_memory(self, query: str, user_id: str = DEFAULT_USER_ID, max_memories: int = 5) -> str:
        memories = self.recall(query, user_id=user_id, top_k=max_memories)
        if not memories:
            return ""
        return "\n".join(["【相关记忆】", *[f"- {memory['content']}" for memory in memories]])

    def reconcile_vectors(self, limit: int = 100) -> dict[str, Any]:
        _ = limit
        return {"enabled": False, "attempted": 0, "ready": 0, "failed": 0, "deleted": 0}

    def _store_memory(self, user_id: str, memory: dict[str, Any]) -> str:
        file_record = self.store.append_bullet(
            user_id,
            str(memory.get("type") or MemoryType.KNOWLEDGE.value),
            str(memory.get("content") or ""),
            source=str(memory.get("source") or "compat"),
            metadata=memory.get("metadata") or {},
        )
        return file_record["id"]

    def get_memory(self, memory_id: str, user_id: str = DEFAULT_USER_ID, increment_access: bool = True) -> dict[str, Any] | None:
        _ = user_id, increment_access
        try:
            file = self.get_file(memory_id)
        except Exception:
            return None
        return {
            "id": file["id"],
            "content": file["content"],
            "type": self._type_from_path(file["path"]),
            "importance": 0.5,
            "source": "file_memory",
            "created_at": file["updated_at"],
            "updated_at": file["updated_at"],
            "access_count": 0,
            "metadata": file["metadata"],
            "vector_state": "not_applicable",
            "storage_mode": "file",
        }

    def update_memory(
        self,
        memory_id: str,
        user_id: str = DEFAULT_USER_ID,
        content: str | None = None,
        importance: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        _ = user_id, importance
        if content is None:
            return self.get_memory(memory_id, user_id=user_id, increment_access=False)
        try:
            file = self.update_file(memory_id, content, metadata=metadata)
        except Exception:
            return None
        return self.get_memory(file["id"], user_id=user_id, increment_access=False)

    def forget(self, user_id: str, memory_id: str) -> bool:
        _ = user_id
        try:
            scope, namespace, relative_path = decode_file_id(memory_id)
            if scope == MemoryScope.ORG:
                return False
            path = self.store._resolve_file_path(scope, namespace, relative_path)
            if path.exists():
                path.unlink()
            meta = self.store._meta_path(path)
            if meta.exists():
                meta.unlink()
            return True
        except Exception:
            return False

    def clear_all(self, user_id: str = DEFAULT_USER_ID) -> bool:
        for file in self.list_files("user", user_id):
            self.update_file(file["id"], USER_MEMORY_FILES.get(file["relative_path"], f"# {file['relative_path']}\n\n"))
        return True

    def _type_from_path(self, path: str) -> str:
        if path.endswith("preferences.md"):
            return MemoryType.PREFERENCE.value
        if path.endswith("projects.md"):
            return MemoryType.PROJECT.value
        return MemoryType.KNOWLEDGE.value


_memory_service: MemoryService | None = None


def get_memory_service() -> MemoryService:
    global _memory_service
    if _memory_service is None:
        _memory_service = MemoryService()
    return _memory_service


def reset_memory_service(root_dir: str | Path = DEFAULT_MEMORY_ROOT, vector_db_path: str | None = None) -> MemoryService:
    global _memory_service
    _memory_service = MemoryService(root_dir=root_dir, vector_db_path=vector_db_path)
    return _memory_service
