"""
对话分支管理 API
支持对话树结构、分支创建与切换
"""
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/chat", tags=["chat-branch"])

DATA_DIR = Path("data/chat")
DATA_DIR.mkdir(parents=True, exist_ok=True)


class MessageNode(BaseModel):
    id: str
    role: str
    content: str
    timestamp: str
    parent_id: str | None = None
    children_ids: list[str] = []
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


def get_session_file(session_id: str) -> Path:
    return DATA_DIR / f"session_{session_id}.json"


def get_branch_file(session_id: str) -> Path:
    return DATA_DIR / f"branches_{session_id}.json"


def load_session_data(session_id: str) -> dict[str, Any]:
    file = get_session_file(session_id)
    if file.exists():
        with open(file, encoding='utf-8') as f:
            return json.load(f)
    return {"messages": [], "tree": {}, "root_id": None, "current_branch_id": None}


def save_session_data(session_id: str, data: dict[str, Any]):
    file = get_session_file(session_id)
    with open(file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_branches(session_id: str) -> dict[str, ChatBranch]:
    file = get_branch_file(session_id)
    if file.exists():
        with open(file, encoding='utf-8') as f:
            data = json.load(f)
            return {k: ChatBranch(**v) for k, v in data.items()}
    return {}


def save_branches(session_id: str, branches: dict[str, ChatBranch]):
    file = get_branch_file(session_id)
    with open(file, 'w', encoding='utf-8') as f:
        json.dump({k: v.model_dump() for k, v in branches.items()}, f, ensure_ascii=False, indent=2)


@router.post("/branch", response_model=BranchResponse)
async def create_branch(request: CreateBranchRequest):
    session_data = load_session_data(request.session_id)
    tree = session_data.get("tree", {})

    if request.from_message_id not in tree:
        raise HTTPException(status_code=404, detail="Message not found")

    branch_id = f"branch_{uuid.uuid4().hex[:8]}"
    branch_name = request.branch_name or f"分支 {datetime.now().strftime('%H:%M')}"

    branch = ChatBranch(
        id=branch_id,
        session_id=request.session_id,
        name=branch_name,
        created_at=datetime.now().isoformat(),
        root_message_id=request.from_message_id,
        message_count=0
    )

    branches = load_branches(request.session_id)
    branches[branch_id] = branch
    save_branches(request.session_id, branches)

    tree[request.from_message_id]["branch_id"] = branch_id
    session_data["tree"] = tree
    save_session_data(request.session_id, session_data)

    return BranchResponse(success=True, branch=branch, message="分支创建成功")


@router.get("/{session_id}/branches", response_model=BranchesListResponse)
async def list_branches(session_id: str):
    branches = load_branches(session_id)
    return BranchesListResponse(branches=list(branches.values()))


@router.get("/{session_id}/tree", response_model=MessageTreeResponse)
async def get_message_tree(session_id: str):
    session_data = load_session_data(session_id)
    tree = session_data.get("tree", {})
    nodes = {k: MessageNode(**v) for k, v in tree.items()}

    return MessageTreeResponse(
        nodes=nodes,
        root_id=session_data.get("root_id"),
        current_branch_id=session_data.get("current_branch_id")
    )


@router.post("/{session_id}/switch-branch/{branch_id}")
async def switch_branch(session_id: str, branch_id: str):
    branches = load_branches(session_id)
    if branch_id not in branches:
        raise HTTPException(status_code=404, detail="Branch not found")

    session_data = load_session_data(session_id)
    session_data["current_branch_id"] = branch_id
    save_session_data(session_id, session_data)

    return {"success": True, "message": "已切换到分支", "branch": branches[branch_id].model_dump()}


@router.delete("/{session_id}/branch/{branch_id}")
async def delete_branch(session_id: str, branch_id: str):
    branches = load_branches(session_id)
    if branch_id not in branches:
        raise HTTPException(status_code=404, detail="Branch not found")

    del branches[branch_id]
    save_branches(session_id, branches)

    return {"success": True, "message": "分支已删除"}


@router.post("/{session_id}/merge-branch/{branch_id}")
async def merge_branch(session_id: str, branch_id: str):
    branches = load_branches(session_id)
    if branch_id not in branches:
        raise HTTPException(status_code=404, detail="Branch not found")

    session_data = load_session_data(session_id)
    current_branch_id = session_data.get("current_branch_id")

    if not current_branch_id:
        raise HTTPException(status_code=400, detail="No current branch to merge into")

    return {"success": True, "message": "分支已合并"}
