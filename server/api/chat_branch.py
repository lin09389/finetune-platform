"""Chat branch management API backed by canonical chat session storage."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from api.chat.session import Session, get_session_manager

router = APIRouter(prefix="/chat", tags=["chat-branch"])

BRANCHES_METADATA_KEY = "branches"
CURRENT_BRANCH_METADATA_KEY = "current_branch_id"
MERGE_STATUS_NOT_IMPLEMENTED = "Branch merge is not implemented yet for canonical chat sessions."


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


def _build_message_tree(session: Session, branches: dict[str, ChatBranch]) -> tuple[dict[str, MessageNode], str | None]:
    if not session.messages:
        return {}, None

    branch_names = {
        branch.root_message_id: branch.name
        for branch in branches.values()
        if branch.root_message_id
    }

    nodes: dict[str, MessageNode] = {}
    previous_id: str | None = None
    root_id: str | None = None

    for message in session.messages:
        node = MessageNode(
            id=message.id,
            role=message.role,
            content=message.content,
            timestamp=message.created_at.isoformat(),
            parent_id=previous_id,
            children_ids=[],
            branch_name=branch_names.get(message.id),
        )
        nodes[message.id] = node

        if previous_id and previous_id in nodes:
            nodes[previous_id].children_ids.append(message.id)

        if root_id is None:
            root_id = message.id
        previous_id = message.id

    return nodes, root_id


@router.post("/branch", response_model=BranchResponse)
async def create_branch(request: CreateBranchRequest):
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
        message_count=len(session.messages),
    )

    branches[branch_id] = branch
    current_branch_id = session.metadata.get(CURRENT_BRANCH_METADATA_KEY) or branch_id
    _save_branch_state(session, branches, current_branch_id=current_branch_id)

    return BranchResponse(success=True, branch=branch, message="Branch created successfully")


@router.get("/{session_id}/branches", response_model=BranchesListResponse)
async def list_branches(session_id: str):
    session = _get_session_or_404(session_id)
    branches = _load_branches(session)
    return BranchesListResponse(branches=list(branches.values()))


@router.get("/{session_id}/tree", response_model=MessageTreeResponse)
async def get_message_tree(session_id: str):
    session = _get_session_or_404(session_id)
    branches = _load_branches(session)
    nodes, root_id = _build_message_tree(session, branches)
    current_branch_id = session.metadata.get(CURRENT_BRANCH_METADATA_KEY)

    return MessageTreeResponse(
        nodes=nodes,
        root_id=root_id,
        current_branch_id=current_branch_id,
    )


@router.post("/{session_id}/switch-branch/{branch_id}")
async def switch_branch(session_id: str, branch_id: str):
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


@router.delete("/{session_id}/branch/{branch_id}")
async def delete_branch(session_id: str, branch_id: str):
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


@router.post("/{session_id}/merge-branch/{branch_id}")
async def merge_branch(session_id: str, branch_id: str):
    session = _get_session_or_404(session_id)
    branches = _load_branches(session)
    if branch_id not in branches:
        raise HTTPException(status_code=404, detail="Branch not found")

    raise HTTPException(status_code=409, detail=MERGE_STATUS_NOT_IMPLEMENTED)
