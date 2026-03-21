# -*- coding: utf-8 -*-
"""
知识库数据模型
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class DocumentStatus(str, Enum):
    """文档状态"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class KnowledgeBase(BaseModel):
    """知识库"""
    id: str = Field(..., description="知识库ID")
    name: str = Field(..., description="知识库名称")
    description: Optional[str] = Field(default=None, description="描述")
    document_count: int = Field(default=0, description="文档数量")
    chunk_count: int = Field(default=0, description="分块数量")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    updated_at: datetime = Field(default_factory=datetime.now, description="更新时间")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数据")


class Document(BaseModel):
    """文档"""
    id: str = Field(..., description="文档ID")
    knowledge_base_id: str = Field(..., description="知识库ID")
    filename: str = Field(..., description="文件名")
    file_path: str = Field(..., description="文件路径")
    file_size: int = Field(default=0, description="文件大小")
    file_type: str = Field(default="", description="文件类型")
    status: DocumentStatus = Field(default=DocumentStatus.PENDING, description="状态")
    chunk_count: int = Field(default=0, description="分块数量")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    updated_at: datetime = Field(default_factory=datetime.now, description="更新时间")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数据")
    error: Optional[str] = Field(default=None, description="错误信息")


class Chunk(BaseModel):
    """文档分块"""
    id: str = Field(..., description="分块ID")
    document_id: str = Field(..., description="文档ID")
    knowledge_base_id: str = Field(..., description="知识库ID")
    content: str = Field(..., description="内容")
    chunk_index: int = Field(default=0, description="分块索引")
    start_char: int = Field(default=0, description="起始字符位置")
    end_char: int = Field(default=0, description="结束字符位置")
    embedding: Optional[List[float]] = Field(default=None, description="嵌入向量")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数据")


class SearchResult(BaseModel):
    """搜索结果"""
    chunk_id: str = Field(..., description="分块ID")
    document_id: str = Field(..., description="文档ID")
    knowledge_base_id: str = Field(..., description="知识库ID")
    content: str = Field(..., description="内容")
    score: float = Field(default=0.0, description="相关性分数")
    filename: Optional[str] = Field(default=None, description="文件名")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数据")
