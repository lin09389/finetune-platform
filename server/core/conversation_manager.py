"""
对话管理�?- 支持对话分支、分享、导出和统计
"""
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum
import json
import os
from pathlib import Path
import uuid
import hashlib
import secrets
import logging

logger = logging.getLogger(__name__)


class BranchStatus(str, Enum):
    ACTIVE = "active"
    MERGED = "merged"
    ARCHIVED = "archived"


class ShareStatus(str, Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"


@dataclass
class MessageNode:
    id: str
    role: str
    content: str
    timestamp: str
    parent_id: Optional[str] = None
    children: List[str] = field(default_factory=list)
    branch_id: Optional[str] = None
    token_count: int = 0
    importance: float = 0.5
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
            "parent_id": self.parent_id,
            "children": self.children,
            "branch_id": self.branch_id,
            "token_count": self.token_count,
            "importance": self.importance,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MessageNode":
        return cls(
            id=data.get("id", ""),
            role=data.get("role", "user"),
            content=data.get("content", ""),
            timestamp=data.get("timestamp", datetime.now().isoformat()),
            parent_id=data.get("parent_id"),
            children=data.get("children", []),
            branch_id=data.get("branch_id"),
            token_count=data.get("token_count", 0),
            importance=data.get("importance", 0.5),
            metadata=data.get("metadata", {})
        )


@dataclass
class ConversationBranch:
    id: str
    session_id: str
    name: str
    parent_branch_id: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    status: BranchStatus = BranchStatus.ACTIVE
    root_message_id: Optional[str] = None
    leaf_message_ids: List[str] = field(default_factory=list)
    message_count: int = 0
    total_tokens: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "name": self.name,
            "parent_branch_id": self.parent_branch_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "status": self.status.value,
            "root_message_id": self.root_message_id,
            "leaf_message_ids": self.leaf_message_ids,
            "message_count": self.message_count,
            "total_tokens": self.total_tokens,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConversationBranch":
        return cls(
            id=data.get("id", ""),
            session_id=data.get("session_id", ""),
            name=data.get("name", ""),
            parent_branch_id=data.get("parent_branch_id"),
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
            status=BranchStatus(data.get("status", "active")),
            root_message_id=data.get("root_message_id"),
            leaf_message_ids=data.get("leaf_message_ids", []),
            message_count=data.get("message_count", 0),
            total_tokens=data.get("total_tokens", 0),
            metadata=data.get("metadata", {})
        )


@dataclass
class ShareLink:
    id: str
    session_id: str
    branch_id: Optional[str] = None
    short_code: str = ""
    password: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    expires_at: Optional[str] = None
    max_views: int = 0
    current_views: int = 0
    status: ShareStatus = ShareStatus.ACTIVE
    created_by: str = "default"
    allow_export: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "branch_id": self.branch_id,
            "short_code": self.short_code,
            "password": self.password,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "max_views": self.max_views,
            "current_views": self.current_views,
            "status": self.status.value,
            "created_by": self.created_by,
            "allow_export": self.allow_export,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ShareLink":
        return cls(
            id=data.get("id", ""),
            session_id=data.get("session_id", ""),
            branch_id=data.get("branch_id"),
            short_code=data.get("short_code", ""),
            password=data.get("password"),
            created_at=data.get("created_at", datetime.now().isoformat()),
            expires_at=data.get("expires_at"),
            max_views=data.get("max_views", 0),
            current_views=data.get("current_views", 0),
            status=ShareStatus(data.get("status", "active")),
            created_by=data.get("created_by", "default"),
            allow_export=data.get("allow_export", True),
            metadata=data.get("metadata", {})
        )
    
    def is_expired(self) -> bool:
        if self.expires_at:
            return datetime.fromisoformat(self.expires_at) < datetime.now()
        return False
    
    def is_view_limit_reached(self) -> bool:
        return self.max_views > 0 and self.current_views >= self.max_views


@dataclass
class ConversationGroup:
    id: str
    name: str
    description: str = ""
    color: str = "#1890ff"
    icon: str = "folder"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    session_ids: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "color": self.color,
            "icon": self.icon,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "session_ids": self.session_ids,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConversationGroup":
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            description=data.get("description", ""),
            color=data.get("color", "#1890ff"),
            icon=data.get("icon", "folder"),
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
            session_ids=data.get("session_ids", []),
            metadata=data.get("metadata", {})
        )


class ConversationManager:
    """对话管理�?- 支持分支、分享、导出和统计"""
    
    def __init__(self, storage_path: Optional[str] = None):
        self.storage_path = Path(storage_path) if storage_path else Path(__file__).parent.parent / "data" / "conversations"
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        self._messages: Dict[str, MessageNode] = {}
        self._branches: Dict[str, ConversationBranch] = {}
        self._shares: Dict[str, ShareLink] = {}
        self._groups: Dict[str, ConversationGroup] = {}
        
        self._session_branches: Dict[str, List[str]] = {}
        self._session_messages: Dict[str, List[str]] = {}
        
        self._load_data()
    
    def _load_data(self):
        """加载所有数�?""
        self._load_messages()
        self._load_branches()
        self._load_shares()
        self._load_groups()
    
    def _load_messages(self):
        """加载消息数据"""
        messages_file = self.storage_path / "messages.json"
        if messages_file.exists():
            try:
                with open(messages_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for msg_id, msg_data in data.items():
                        self._messages[msg_id] = MessageNode.from_dict(msg_data)
                logger.info(f"加载 {len(self._messages)} 条消�?)
            except Exception as e:
                logger.error(f"加载消息数据失败: {e}")
    
    def _save_messages(self):
        """保存消息数据"""
        messages_file = self.storage_path / "messages.json"
        try:
            data = {msg_id: msg.to_dict() for msg_id, msg in self._messages.items()}
            with open(messages_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存消息数据失败: {e}")
    
    def _load_branches(self):
        """加载分支数据"""
        branches_file = self.storage_path / "branches.json"
        if branches_file.exists():
            try:
                with open(branches_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for branch_id, branch_data in data.items():
                        branch = ConversationBranch.from_dict(branch_data)
                        self._branches[branch_id] = branch
                        
                        session_id = branch.session_id
                        if session_id not in self._session_branches:
                            self._session_branches[session_id] = []
                        self._session_branches[session_id].append(branch_id)
                logger.info(f"加载 {len(self._branches)} 个分�?)
            except Exception as e:
                logger.error(f"加载分支数据失败: {e}")
    
    def _save_branches(self):
        """保存分支数据"""
        branches_file = self.storage_path / "branches.json"
        try:
            data = {branch_id: branch.to_dict() for branch_id, branch in self._branches.items()}
            with open(branches_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存分支数据失败: {e}")
    
    def _load_shares(self):
        """加载分享链接数据"""
        shares_file = self.storage_path / "shares.json"
        if shares_file.exists():
            try:
                with open(shares_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for share_id, share_data in data.items():
                        self._shares[share_id] = ShareLink.from_dict(share_data)
                logger.info(f"加载 {len(self._shares)} 个分享链�?)
            except Exception as e:
                logger.error(f"加载分享链接数据失败: {e}")
    
    def _save_shares(self):
        """保存分享链接数据"""
        shares_file = self.storage_path / "shares.json"
        try:
            data = {share_id: share.to_dict() for share_id, share in self._shares.items()}
            with open(shares_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存分享链接数据失败: {e}")
    
    def _load_groups(self):
        """加载分组数据"""
        groups_file = self.storage_path / "groups.json"
        if groups_file.exists():
            try:
                with open(groups_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for group_id, group_data in data.items():
                        self._groups[group_id] = ConversationGroup.from_dict(group_data)
                logger.info(f"加载 {len(self._groups)} 个分�?)
            except Exception as e:
                logger.error(f"加载分组数据失败: {e}")
    
    def _save_groups(self):
        """保存分组数据"""
        groups_file = self.storage_path / "groups.json"
        try:
            data = {group_id: group.to_dict() for group_id, group in self._groups.items()}
            with open(groups_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存分组数据失败: {e}")
    
    def _generate_short_code(self, length: int = 8) -> str:
        """生成短码"""
        chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        return ''.join(secrets.choice(chars) for _ in range(length))
    
    def _generate_id(self, prefix: str = "") -> str:
        """生成唯一 ID"""
        return f"{prefix}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"
    
    def create_branch(
        self,
        session_id: str,
        from_message_id: Optional[str] = None,
        name: Optional[str] = None,
        parent_branch_id: Optional[str] = None
    ) -> ConversationBranch:
        """创建新分�?        
        Args:
            session_id: 会话 ID
            from_message_id: 从哪条消息开始分支（如果�?None，则从头开始）
            name: 分支名称
            parent_branch_id: 父分�?ID
        
        Returns:
            新创建的分支
        """
        branch_id = self._generate_id("branch")
        
        branch = ConversationBranch(
            id=branch_id,
            session_id=session_id,
            name=name or f"分支 {datetime.now().strftime('%m/%d %H:%M')}",
            parent_branch_id=parent_branch_id,
            root_message_id=from_message_id
        )
        
        self._branches[branch_id] = branch
        
        if session_id not in self._session_branches:
            self._session_branches[session_id] = []
        self._session_branches[session_id].append(branch_id)
        
        self._save_branches()
        logger.info(f"创建分支: {branch_id} (session: {session_id})")
        
        return branch
    
    def get_branch(self, branch_id: str) -> Optional[ConversationBranch]:
        """获取分支"""
        return self._branches.get(branch_id)
    
    def get_session_branches(self, session_id: str) -> List[ConversationBranch]:
        """获取会话的所有分�?""
        branch_ids = self._session_branches.get(session_id, [])
        return [self._branches[bid] for bid in branch_ids if bid in self._branches]
    
    def add_message_to_branch(
        self,
        branch_id: str,
        role: str,
        content: str,
        parent_message_id: Optional[str] = None,
        token_count: int = 0,
        metadata: Optional[Dict[str, Any]] = None
    ) -> MessageNode:
        """向分支添加消�?""
        branch = self._branches.get(branch_id)
        if not branch:
            raise ValueError(f"分支不存�? {branch_id}")
        
        message_id = self._generate_id("msg")
        
        message = MessageNode(
            id=message_id,
            role=role,
            content=content,
            timestamp=datetime.now().isoformat(),
            parent_id=parent_message_id,
            branch_id=branch_id,
            token_count=token_count,
            metadata=metadata or {}
        )
        
        if parent_message_id and parent_message_id in self._messages:
            self._messages[parent_message_id].children.append(message_id)
        
        self._messages[message_id] = message
        
        if branch.root_message_id is None:
            branch.root_message_id = message_id
        
        branch.leaf_message_ids = [message_id]
        branch.message_count += 1
        branch.total_tokens += token_count
        branch.updated_at = datetime.now().isoformat()
        
        session_id = branch.session_id
        if session_id not in self._session_messages:
            self._session_messages[session_id] = []
        self._session_messages[session_id].append(message_id)
        
        self._save_messages()
        self._save_branches()
        
        return message
    
    def get_branch_messages(
        self,
        branch_id: str,
        include_context: bool = True
    ) -> List[MessageNode]:
        """获取分支的消息列�?        
        Args:
            branch_id: 分支 ID
            include_context: 是否包含父分支的上下文消�?        
        Returns:
            消息列表（按时间顺序�?        """
        branch = self._branches.get(branch_id)
        if not branch:
            return []
        
        messages = []
        
        if include_context and branch.parent_branch_id:
            parent_messages = self.get_branch_messages(branch.parent_branch_id, include_context=True)
            messages.extend(parent_messages)
        
        if branch.root_message_id:
            current_id = branch.root_message_id
            visited = set()
            
            while current_id and current_id not in visited:
                visited.add(current_id)
                msg = self._messages.get(current_id)
                if msg and msg.branch_id == branch_id:
                    messages.append(msg)
                
                if msg and msg.children:
                    current_id = msg.children[0]
                else:
                    break
        
        return messages
    
    def switch_branch(
        self,
        session_id: str,
        from_branch_id: str,
        to_branch_id: str
    ) -> List[MessageNode]:
        """切换分支
        
        Args:
            session_id: 会话 ID
            from_branch_id: 当前分支 ID
            to_branch_id: 目标分支 ID
        
        Returns:
            目标分支的消息列�?        """
        to_branch = self._branches.get(to_branch_id)
        if not to_branch or to_branch.session_id != session_id:
            raise ValueError(f"目标分支不存在或不属于该会话: {to_branch_id}")
        
        return self.get_branch_messages(to_branch_id)
    
    def merge_branch(
        self,
        source_branch_id: str,
        target_branch_id: str
    ) -> bool:
        """合并分支
        
        Args:
            source_branch_id: 源分�?ID
            target_branch_id: 目标分支 ID
        
        Returns:
            是否成功
        """
        source = self._branches.get(source_branch_id)
        target = self._branches.get(target_branch_id)
        
        if not source or not target:
            return False
        
        if source.session_id != target.session_id:
            return False
        
        source.status = BranchStatus.MERGED
        source.updated_at = datetime.now().isoformat()
        
        self._save_branches()
        logger.info(f"合并分支: {source_branch_id} -> {target_branch_id}")
        
        return True
    
    def delete_branch(self, branch_id: str, soft_delete: bool = True) -> bool:
        """删除分支"""
        branch = self._branches.get(branch_id)
        if not branch:
            return False
        
        if soft_delete:
            branch.status = BranchStatus.ARCHIVED
            branch.updated_at = datetime.now().isoformat()
        else:
            del self._branches[branch_id]
            if branch.session_id in self._session_branches:
                self._session_branches[branch.session_id] = [
                    bid for bid in self._session_branches[branch.session_id] if bid != branch_id
                ]
        
        self._save_branches()
        return True
    
    def create_share_link(
        self,
        session_id: str,
        branch_id: Optional[str] = None,
        expires_in_hours: int = 24,
        max_views: int = 0,
        password: Optional[str] = None,
        allow_export: bool = True
    ) -> ShareLink:
        """创建分享链接
        
        Args:
            session_id: 会话 ID
            branch_id: 分支 ID（可选，不指定则分享整个会话�?            expires_in_hours: 过期时间（小时）�? 表示永不过期
            max_views: 最大查看次数，0 表示无限�?            password: 访问密码（可选）
            allow_export: 是否允许导出
        
        Returns:
            分享链接
        """
        share_id = self._generate_id("share")
        short_code = self._generate_short_code(8)
        
        expires_at = None
        if expires_in_hours > 0:
            expires_at = (datetime.now() + timedelta(hours=expires_in_hours)).isoformat()
        
        share = ShareLink(
            id=share_id,
            session_id=session_id,
            branch_id=branch_id,
            short_code=short_code,
            password=password,
            expires_at=expires_at,
            max_views=max_views,
            allow_export=allow_export
        )
        
        self._shares[share_id] = share
        self._save_shares()
        
        logger.info(f"创建分享链接: {share_id} (session: {session_id})")
        return share
    
    def get_share_by_code(self, short_code: str) -> Optional[ShareLink]:
        """通过短码获取分享链接"""
        for share in self._shares.values():
            if share.short_code == short_code:
                if share.is_expired() or share.is_view_limit_reached():
                    share.status = ShareStatus.EXPIRED
                    self._save_shares()
                    return None
                return share
        return None
    
    def access_share(self, short_code: str, password: Optional[str] = None) -> Dict[str, Any]:
        """访问分享内容
        
        Args:
            short_code: 短码
            password: 访问密码
        
        Returns:
            分享内容
        """
        share = self.get_share_by_code(short_code)
        if not share:
            return {"error": "分享链接不存在或已过�?}
        
        if share.password and share.password != password:
            return {"error": "密码错误"}
        
        share.current_views += 1
        self._save_shares()
        
        messages = []
        if share.branch_id:
            messages = [m.to_dict() for m in self.get_branch_messages(share.branch_id)]
        else:
            message_ids = self._session_messages.get(share.session_id, [])
            messages = [self._messages[mid].to_dict() for mid in message_ids if mid in self._messages]
        
        return {
            "share": share.to_dict(),
            "messages": messages,
            "allow_export": share.allow_export
        }
    
    def revoke_share(self, share_id: str) -> bool:
        """撤销分享链接"""
        share = self._shares.get(share_id)
        if not share:
            return False
        
        share.status = ShareStatus.REVOKED
        self._save_shares()
        return True
    
    def export_to_markdown(
        self,
        session_id: str,
        branch_id: Optional[str] = None,
        title: Optional[str] = None
    ) -> str:
        """导出�?Markdown 格式"""
        if branch_id:
            messages = self.get_branch_messages(branch_id)
        else:
            message_ids = self._session_messages.get(session_id, [])
            messages = [self._messages[mid] for mid in message_ids if mid in self._messages]
        
        lines = [f"# {title or '对话记录'}", ""]
        lines.append(f"导出时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")
        lines.append("---")
        lines.append("")
        
        for msg in messages:
            role_emoji = "👤" if msg.role == "user" else "🤖" if msg.role == "assistant" else "⚙️"
            role_name = "用户" if msg.role == "user" else "助手" if msg.role == "assistant" else "系统"
            
            lines.append(f"## {role_emoji} {role_name}")
            lines.append("")
            lines.append(f"*{msg.timestamp}*")
            lines.append("")
            lines.append(msg.content)
            lines.append("")
            lines.append("---")
            lines.append("")
        
        return "\n".join(lines)
    
    def export_to_pdf_data(
        self,
        session_id: str,
        branch_id: Optional[str] = None,
        title: Optional[str] = None
    ) -> Dict[str, Any]:
        """导出�?PDF 数据（供前端生成 PDF�?""
        if branch_id:
            messages = self.get_branch_messages(branch_id)
        else:
            message_ids = self._session_messages.get(session_id, [])
            messages = [self._messages[mid] for mid in message_ids if mid in self._messages]
        
        return {
            "title": title or "对话记录",
            "exported_at": datetime.now().isoformat(),
            "messages": [msg.to_dict() for msg in messages],
            "total_messages": len(messages),
            "total_tokens": sum(msg.token_count for msg in messages)
        }
    
    def search_messages(
        self,
        query: str,
        session_ids: Optional[List[str]] = None,
        branch_ids: Optional[List[str]] = None,
        roles: Optional[List[str]] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """搜索消息
        
        Args:
            query: 搜索关键�?            session_ids: 会话 ID 列表（可选）
            branch_ids: 分支 ID 列表（可选）
            roles: 角色过滤（可选）
            start_date: 开始日期（可选）
            end_date: 结束日期（可选）
            limit: 返回数量限制
            offset: 偏移�?        
        Returns:
            匹配的消息列�?        """
        results = []
        query_lower = query.lower()
        
        for msg_id, msg in self._messages.items():
            if query_lower not in msg.content.lower():
                continue
            
            if roles and msg.role not in roles:
                continue
            
            if start_date and msg.timestamp < start_date:
                continue
            
            if end_date and msg.timestamp > end_date:
                continue
            
            if branch_ids and msg.branch_id not in branch_ids:
                continue
            
            if session_ids:
                branch = self._branches.get(msg.branch_id) if msg.branch_id else None
                if not branch or branch.session_id not in session_ids:
                    continue
            
            results.append({
                "message": msg.to_dict(),
                "branch_id": msg.branch_id,
                "session_id": self._branches.get(msg.branch_id).session_id if msg.branch_id else None,
                "highlight": self._highlight_text(msg.content, query)
            })
        
        results.sort(key=lambda x: x["message"]["timestamp"], reverse=True)
        
        return results[offset:offset + limit]
    
    def _highlight_text(self, text: str, query: str, max_length: int = 200) -> str:
        """高亮搜索关键�?""
        if len(text) <= max_length:
            return text.replace(query, f"**{query}**")
        
        idx = text.lower().find(query.lower())
        if idx == -1:
            return text[:max_length] + "..."
        
        start = max(0, idx - 50)
        end = min(len(text), idx + len(query) + 50)
        
        snippet = text[start:end]
        if start > 0:
            snippet = "..." + snippet
        if end < len(text):
            snippet = snippet + "..."
        
        return snippet.replace(query, f"**{query}**")
    
    def create_group(
        self,
        name: str,
        description: str = "",
        color: str = "#1890ff",
        icon: str = "folder",
        session_ids: Optional[List[str]] = None
    ) -> ConversationGroup:
        """创建分组"""
        group_id = self._generate_id("group")
        
        group = ConversationGroup(
            id=group_id,
            name=name,
            description=description,
            color=color,
            icon=icon,
            session_ids=session_ids or []
        )
        
        self._groups[group_id] = group
        self._save_groups()
        
        logger.info(f"创建分组: {group_id}")
        return group
    
    def get_group(self, group_id: str) -> Optional[ConversationGroup]:
        """获取分组"""
        return self._groups.get(group_id)
    
    def get_all_groups(self) -> List[ConversationGroup]:
        """获取所有分�?""
        return list(self._groups.values())
    
    def update_group(
        self,
        group_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        color: Optional[str] = None,
        session_ids: Optional[List[str]] = None
    ) -> Optional[ConversationGroup]:
        """更新分组"""
        group = self._groups.get(group_id)
        if not group:
            return None
        
        if name is not None:
            group.name = name
        if description is not None:
            group.description = description
        if color is not None:
            group.color = color
        if session_ids is not None:
            group.session_ids = session_ids
        
        group.updated_at = datetime.now().isoformat()
        self._save_groups()
        
        return group
    
    def delete_group(self, group_id: str) -> bool:
        """删除分组"""
        if group_id not in self._groups:
            return False
        
        del self._groups[group_id]
        self._save_groups()
        return True
    
    def add_session_to_group(self, group_id: str, session_id: str) -> bool:
        """添加会话到分�?""
        group = self._groups.get(group_id)
        if not group:
            return False
        
        if session_id not in group.session_ids:
            group.session_ids.append(session_id)
            group.updated_at = datetime.now().isoformat()
            self._save_groups()
        
        return True
    
    def remove_session_from_group(self, group_id: str, session_id: str) -> bool:
        """从分组移除会�?""
        group = self._groups.get(group_id)
        if not group:
            return False
        
        if session_id in group.session_ids:
            group.session_ids.remove(session_id)
            group.updated_at = datetime.now().isoformat()
            self._save_groups()
        
        return True
    
    def batch_delete_sessions(self, session_ids: List[str]) -> Dict[str, Any]:
        """批量删除会话"""
        deleted_count = 0
        failed_count = 0
        
        for session_id in session_ids:
            branch_ids = self._session_branches.get(session_id, [])
            
            for branch_id in branch_ids:
                self.delete_branch(branch_id, soft_delete=False)
            
            if session_id in self._session_branches:
                del self._session_branches[session_id]
            
            if session_id in self._session_messages:
                del self._session_messages[session_id]
            
            deleted_count += 1
        
        self._save_branches()
        self._save_messages()
        
        return {
            "deleted": deleted_count,
            "failed": failed_count,
            "total": len(session_ids)
        }
    
    def batch_archive_sessions(self, session_ids: List[str]) -> Dict[str, Any]:
        """批量归档会话"""
        archived_count = 0
        
        for session_id in session_ids:
            branch_ids = self._session_branches.get(session_id, [])
            
            for branch_id in branch_ids:
                branch = self._branches.get(branch_id)
                if branch:
                    branch.status = BranchStatus.ARCHIVED
                    branch.updated_at = datetime.now().isoformat()
                    archived_count += 1
        
        self._save_branches()
        
        return {
            "archived": archived_count,
            "total": len(session_ids)
        }
    
    def batch_add_tags(
        self,
        session_ids: List[str],
        tags: List[str]
    ) -> Dict[str, Any]:
        """批量添加标签"""
        updated_count = 0
        
        for session_id in session_ids:
            branch_ids = self._session_branches.get(session_id, [])
            
            for branch_id in branch_ids:
                branch = self._branches.get(branch_id)
                if branch:
                    current_tags = branch.metadata.get("tags", [])
                    for tag in tags:
                        if tag not in current_tags:
                            current_tags.append(tag)
                    branch.metadata["tags"] = current_tags
                    branch.updated_at = datetime.now().isoformat()
                    updated_count += 1
        
        self._save_branches()
        
        return {
            "updated": updated_count,
            "total": len(session_ids)
        }
    
    def get_statistics(
        self,
        session_ids: Optional[List[str]] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """获取统计信息
        
        Args:
            session_ids: 会话 ID 列表（可选，不指定则统计全部�?            start_date: 开始日期（可选）
            end_date: 结束日期（可选）
        
        Returns:
            统计信息
        """
        total_messages = 0
        total_tokens = 0
        total_branches = 0
        role_counts: Dict[str, int] = {}
        daily_counts: Dict[str, int] = {}
        hourly_counts: Dict[int, int] = {}
        
        branches_to_count = []
        if session_ids:
            for sid in session_ids:
                branches_to_count.extend(self._session_branches.get(sid, []))
        else:
            branches_to_count = list(self._branches.keys())
        
        for branch_id in branches_to_count:
            branch = self._branches.get(branch_id)
            if not branch:
                continue
            
            if start_date and branch.created_at < start_date:
                continue
            if end_date and branch.created_at > end_date:
                continue
            
            total_branches += 1
            total_messages += branch.message_count
            total_tokens += branch.total_tokens
            
            try:
                date_str = branch.created_at[:10]
                daily_counts[date_str] = daily_counts.get(date_str, 0) + 1
                
                hour = int(branch.created_at[11:13])
                hourly_counts[hour] = hourly_counts.get(hour, 0) + 1
            except (ValueError, IndexError):
                pass
        
        for msg in self._messages.values():
            if msg.branch_id not in branches_to_count:
                continue
            
            role_counts[msg.role] = role_counts.get(msg.role, 0) + 1
        
        return {
            "total_branches": total_branches,
            "total_messages": total_messages,
            "total_tokens": total_tokens,
            "role_distribution": role_counts,
            "daily_activity": daily_counts,
            "hourly_distribution": hourly_counts,
            "average_messages_per_branch": total_messages / total_branches if total_branches > 0 else 0,
            "average_tokens_per_message": total_tokens / total_messages if total_messages > 0 else 0
        }
    
    def get_conversation_tree(
        self,
        session_id: str,
        max_depth: int = 10
    ) -> Dict[str, Any]:
        """获取对话树结�?        
        Args:
            session_id: 会话 ID
            max_depth: 最大深�?        
        Returns:
            对话树结�?        """
        branch_ids = self._session_branches.get(session_id, [])
        branches = [self._branches[bid] for bid in branch_ids if bid in self._branches]
        
        tree = {
            "session_id": session_id,
            "branches": [],
            "root_branches": []
        }
        
        branch_map = {b.id: b for b in branches}
        
        for branch in branches:
            branch_data = {
                "id": branch.id,
                "name": branch.name,
                "parent_id": branch.parent_branch_id,
                "status": branch.status.value,
                "message_count": branch.message_count,
                "created_at": branch.created_at,
                "children": []
            }
            tree["branches"].append(branch_data)
            
            if not branch.parent_branch_id or branch.parent_branch_id not in branch_map:
                tree["root_branches"].append(branch.id)
        
        for branch_data in tree["branches"]:
            parent_id = branch_data["parent_id"]
            if parent_id:
                for bd in tree["branches"]:
                    if bd["id"] == parent_id:
                        bd["children"].append(branch_data["id"])
                        break
        
        return tree


_conversation_manager: Optional[ConversationManager] = None


def get_conversation_manager() -> ConversationManager:
    """获取对话管理器单�?""
    global _conversation_manager
    if _conversation_manager is None:
        _conversation_manager = ConversationManager()
    return _conversation_manager
