"""Chat branch management API backed by canonical chat session storage."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from api.chat.session import Session, get_session_manager
from core.db_manager import run_sync

router = APIRouter(prefix="/chat", tags=["chat-branch"])

BRANCHES_METADATA_KEY = "branches"
CURRENT_BRANCH_METADATA_KEY = "current_branch_id"
MESSAGE_PARENT_ID_METADATA_KEY = "parent_id"
MESSAGE_BRANCH_ID_METADATA_KEY = "branch_id"
MESSAGE_MERGED_FROM_BRANCH_METADATA_KEY = "merged_from_branch_id"
MESSAGE_MERGED_AT_METADATA_KEY = "merged_at"


class MessageNode(BaseModel):
    id: str
    role: str
    content: str
    timestamp: str
    parent_id: str | None = None
    children_ids: list[str] = Field(default_factory=list)
    branch_name: str | None = None


class ChatBranch(BaseModel):
    id: str
    session_id: str
    name: str
    created_at: str
    root_message_id: str | None = None
    last_message_id: str | None = None
    message_count: int = 0


class CreateBranchRequest(BaseModel):
    session_id: str
    from_message_id: str
    branch_name: str | None = None


class BranchResponse(BaseModel):
    success: bool
    branch: ChatBranch | None = None
    message: str = ""


class BranchesListResponse(BaseModel):
    branches: list[ChatBranch]


class MessageTreeResponse(BaseModel):
    nodes: dict[str, MessageNode]
    root_id: str | None = None
    current_branch_id: str | None = None


def _get_session_or_404(session_id: str) -> Session:
    session = get_session_manager().get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


def _coerce_branch(branch_id: str, session_id: str, payload: dict[str, Any]) -> ChatBranch:
    return ChatBranch(
        id=branch_id,
        session_id=session_id,
        name=payload.get("name", "Branch"),
        created_at=payload.get("created_at", datetime.now().isoformat()),
        root_message_id=payload.get("root_message_id"),
        last_message_id=payload.get("last_message_id"),
        message_count=payload.get("message_count", 0),
    )


def _load_branches(session: Session) -> dict[str, ChatBranch]:
    raw = session.metadata.get(BRANCHES_METADATA_KEY, {})
    if not isinstance(raw, dict):
        return {}
    branches: dict[str, ChatBranch] = {}
    for branch_id, payload in raw.items():
        if isinstance(payload, dict):
            branches[branch_id] = _coerce_branch(branch_id, session.id, payload)
    return branches


def _save_branch_state(
    session: Session,
    branches: dict[str, ChatBranch],
    current_branch_id: str | None = None,
) -> None:
    metadata: dict[str, Any] = {
        BRANCHES_METADATA_KEY: {branch_id: branch.model_dump() for branch_id, branch in branches.items()},
        CURRENT_BRANCH_METADATA_KEY: current_branch_id,
    }
    get_session_manager().update_session_metadata(session.id, metadata)


def get_message_parent_id(message: Any) -> str | None:
    metadata = getattr(message, "metadata", {}) or {}
    parent_id = metadata.get(MESSAGE_PARENT_ID_METADATA_KEY)
    return parent_id if isinstance(parent_id, str) and parent_id else None


def get_message_branch_id(message: Any) -> str | None:
    metadata = getattr(message, "metadata", {}) or {}
    branch_id = metadata.get(MESSAGE_BRANCH_ID_METADATA_KEY)
    return branch_id if isinstance(branch_id, str) and branch_id else None


def set_message_tree_metadata(message: Any, parent_id: str | None, branch_id: str | None) -> None:
    metadata = dict(getattr(message, "metadata", {}) or {})
    if parent_id:
        metadata[MESSAGE_PARENT_ID_METADATA_KEY] = parent_id
    else:
        metadata.pop(MESSAGE_PARENT_ID_METADATA_KEY, None)

    if branch_id:
        metadata[MESSAGE_BRANCH_ID_METADATA_KEY] = branch_id
    else:
        metadata.pop(MESSAGE_BRANCH_ID_METADATA_KEY, None)

    message.metadata = metadata


def _build_message_lookup(session: Session) -> dict[str, Any]:
    return {message.id: message for message in session.messages}


def _get_branch_tip(session: Session, branch_id: str | None, branches: dict[str, ChatBranch]) -> str | None:
    if branch_id:
        branch = branches.get(branch_id)
        if branch:
            return branch.last_message_id or branch.root_message_id

    for message in reversed(session.messages):
        if not get_message_branch_id(message):
            return message.id

    return session.messages[-1].id if session.messages else None


def _count_branch_messages(session: Session, branch_id: str) -> int:
    return sum(1 for message in session.messages if get_message_branch_id(message) == branch_id)


def get_next_message_tree_metadata(
    session: Session,
    metadata: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], str | None]:
    branches = _load_branches(session)
    current_branch_id = session.metadata.get(CURRENT_BRANCH_METADATA_KEY)
    if current_branch_id not in branches:
        current_branch_id = None

    message_metadata = dict(metadata or {})
    parent_id = _get_branch_tip(session, current_branch_id, branches)
    if parent_id:
        message_metadata[MESSAGE_PARENT_ID_METADATA_KEY] = parent_id
    else:
        message_metadata.pop(MESSAGE_PARENT_ID_METADATA_KEY, None)

    if current_branch_id:
        message_metadata[MESSAGE_BRANCH_ID_METADATA_KEY] = current_branch_id
    else:
        message_metadata.pop(MESSAGE_BRANCH_ID_METADATA_KEY, None)

    return message_metadata, current_branch_id


def register_branch_message(session: Session, branch_id: str | None, message_id: str) -> None:
    if not branch_id:
        return

    branches = _load_branches(session)
    branch = branches.get(branch_id)
    if not branch:
        return

    branch.last_message_id = message_id
    branch.message_count = _count_branch_messages(session, branch_id)
    _save_branch_state(session, branches, current_branch_id=branch_id)


def _build_message_tree(session: Session, branches: dict[str, ChatBranch]) -> tuple[dict[str, MessageNode], str | None]:
    if not session.messages:
        return {}, None

    branch_names = {branch_id: branch.name for branch_id, branch in branches.items()}

    nodes: dict[str, MessageNode] = {}
    for message in session.messages:
        parent_id = get_message_parent_id(message)
        branch_id = get_message_branch_id(message)
        node = MessageNode(
            id=message.id,
            role=message.role,
            content=message.content,
            timestamp=message.created_at.isoformat(),
            parent_id=parent_id,
            children_ids=[],
            branch_name=branch_names.get(branch_id),
        )
        nodes[message.id] = node

    root_id: str | None = None
    for message in session.messages:
        parent_id = nodes[message.id].parent_id
        if parent_id and parent_id in nodes:
            nodes[parent_id].children_ids.append(message.id)
        elif root_id is None:
            root_id = message.id

    if root_id is None and session.messages:
        root_id = session.messages[0].id

    return nodes, root_id


@router.post("/branch", response_model=BranchResponse)
async def create_branch(request: CreateBranchRequest):
    def _create():
        session = _get_session_or_404(request.session_id)
        message_ids = {message.id for message in session.messages}
        if request.from_message_id not in message_ids:
            raise HTTPException(status_code=404, detail="Message not found")

        branches = _load_branches(session)
        branch_id = f"branch_{uuid.uuid4().hex[:8]}"
        branch = ChatBranch(
            id=branch_id,
            session_id=request.session_id,
            name=request.branch_name or f"Branch {datetime.now().strftime('%H:%M')}",
            created_at=datetime.now().isoformat(),
            root_message_id=request.from_message_id,
            last_message_id=request.from_message_id,
            message_count=0,
        )

        branches[branch_id] = branch
        current_branch_id = session.metadata.get(CURRENT_BRANCH_METADATA_KEY) or branch_id
        _save_branch_state(session, branches, current_branch_id=current_branch_id)

        return BranchResponse(success=True, branch=branch, message="Branch created successfully")
    return await run_sync(_create)


@router.get("/{session_id}/branches", response_model=BranchesListResponse)
async def list_branches(session_id: str):
    def _list():
        session = _get_session_or_404(session_id)
        branches = _load_branches(session)
        for branch in branches.values():
            branch.message_count = _count_branch_messages(session, branch.id)
        return BranchesListResponse(branches=list(branches.values()))
    return await run_sync(_list)


@router.get("/{session_id}/tree", response_model=MessageTreeResponse)
async def get_message_tree(session_id: str):
    def _tree():
        session = _get_session_or_404(session_id)
        branches = _load_branches(session)
        nodes, root_id = _build_message_tree(session, branches)
        current_branch_id = session.metadata.get(CURRENT_BRANCH_METADATA_KEY)

        return MessageTreeResponse(
            nodes=nodes,
            root_id=root_id,
            current_branch_id=current_branch_id,
        )
    return await run_sync(_tree)


@router.post("/{session_id}/switch-branch/{branch_id}")
async def switch_branch(session_id: str, branch_id: str):
    def _switch():
        session = _get_session_or_404(session_id)
        branches = _load_branches(session)
        if branch_id not in branches:
            raise HTTPException(status_code=404, detail="Branch not found")

        _save_branch_state(session, branches, current_branch_id=branch_id)
        return {
            "success": True,
            "message": "Branch switched successfully",
            "branch": branches[branch_id].model_dump(),
        }
    return await run_sync(_switch)


@router.delete("/{session_id}/branch/{branch_id}")
async def delete_branch(session_id: str, branch_id: str):
    def _delete():
        session = _get_session_or_404(session_id)
        branches = _load_branches(session)
        if branch_id not in branches:
            raise HTTPException(status_code=404, detail="Branch not found")

        del branches[branch_id]
        current_branch_id = session.metadata.get(CURRENT_BRANCH_METADATA_KEY)
        if current_branch_id == branch_id:
            current_branch_id = None

        _save_branch_state(session, branches, current_branch_id=current_branch_id)
        return {"success": True, "message": "Branch deleted successfully"}
    return await run_sync(_delete)


@router.post("/{session_id}/merge-branch/{branch_id}")
async def merge_branch(session_id: str, branch_id: str):
    def _merge():
        session = _get_session_or_404(session_id)
        branches = _load_branches(session)
        if branch_id not in branches:
            raise HTTPException(status_code=404, detail="Branch not found")
        source_branch = branches[branch_id]
        current_branch_id = session.metadata.get(CURRENT_BRANCH_METADATA_KEY)

        if current_branch_id == branch_id:
            raise HTTPException(status_code=409, detail="Cannot merge the current branch into itself")

        message_lookup = _build_message_lookup(session)
        source_root_id = source_branch.root_message_id
        if not source_root_id or source_root_id not in message_lookup:
            raise HTTPException(status_code=409, detail="Branch root message is missing")

        source_messages = [
            message for message in session.messages
            if get_message_branch_id(message) == branch_id
        ]
        if not source_messages:
            del branches[branch_id]
            _save_branch_state(session, branches, current_branch_id=current_branch_id)
            get_session_manager().save_session(session.id)
            return {
                "success": True,
                "message": "Branch metadata removed because the branch had no branch-specific messages",
                "merged_count": 0,
                "target_branch_id": current_branch_id,
            }

        source_entry_messages = [
            message for message in source_messages
            if get_message_parent_id(message) == source_root_id
        ]
        if not source_entry_messages:
            raise HTTPException(status_code=409, detail="Branch entry point could not be determined")

        target_tip_id = _get_branch_tip(session, current_branch_id, branches)
        if target_tip_id is None:
            target_tip_id = source_root_id

        merged_at = datetime.now().isoformat()
        target_branch_id = current_branch_id if current_branch_id in branches else None

        for entry_message in source_entry_messages:
            set_message_tree_metadata(entry_message, target_tip_id, target_branch_id)

        for message in source_messages:
            metadata = dict(message.metadata or {})
            if message not in source_entry_messages:
                metadata[MESSAGE_BRANCH_ID_METADATA_KEY] = target_branch_id
                if target_branch_id is None:
                    metadata.pop(MESSAGE_BRANCH_ID_METADATA_KEY, None)
            metadata[MESSAGE_MERGED_FROM_BRANCH_METADATA_KEY] = branch_id
            metadata[MESSAGE_MERGED_AT_METADATA_KEY] = merged_at
            message.metadata = metadata

        if target_branch_id:
            target_branch = branches[target_branch_id]
            target_branch.last_message_id = source_messages[-1].id
            target_branch.message_count = _count_branch_messages(session, target_branch_id)

        del branches[branch_id]
        _save_branch_state(session, branches, current_branch_id=target_branch_id)
        get_session_manager().save_session(session.id)

        return {
            "success": True,
            "message": "Branch merged successfully",
            "merged_count": len(source_messages),
            "target_branch_id": target_branch_id,
        }
    return await run_sync(_merge)
