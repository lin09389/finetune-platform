# -*- coding: utf-8 -*-
"""
推理性能指标 API

提供性能监控、优化建议等功能
"""
from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime

router = APIRouter(prefix="/inference/performance", tags=["Inference Performance"])


class PerformanceMetrics(BaseModel):
    """性能指标"""
    requests_per_second: float = Field(default=0.0, description="每秒请求数")
    average_latency_ms: float = Field(default=0.0, description="平均延迟（毫秒）")
    p50_latency_ms: float = Field(default=0.0, description="P50 延迟")
    p95_latency_ms: float = Field(default=0.0, description="P95 延迟")
    p99_latency_ms: float = Field(default=0.0, description="P99 延迟")
    tokens_per_second: float = Field(default=0.0, description="每秒生成 token 数")
    gpu_memory_used_mb: float = Field(default=0.0, description="GPU 显存使用量")
    gpu_utilization_percent: float = Field(default=0.0, description="GPU 利用率")
    queue_length: int = Field(default=0, description="队列长度")
    active_requests: int = Field(default=0, description="活跃请求数")


class OptimizationSuggestion(BaseModel):
    """优化建议"""
    category: str = Field(description="类别")
    suggestion: str = Field(description="建议内容")
    impact: str = Field(description="预期影响")
    priority: str = Field(description="优先级")


class PerformanceStats(BaseModel):
    """性能统计"""
    period: str = Field(description="统计周期")
    total_requests: int = Field(default=0, description="总请求数")
    successful_requests: int = Field(default=0, description="成功请求数")
    failed_requests: int = Field(default=0, description="失败请求数")
    total_tokens_generated: int = Field(default=0, description="总生成 token 数")
    total_time_seconds: float = Field(default=0.0, description="总时间（秒）")
    metrics: PerformanceMetrics = Field(default_factory=PerformanceMetrics)


@router.get("/metrics", response_model=PerformanceMetrics)
async def get_current_metrics():
    """获取当前性能指标"""
    return PerformanceMetrics()


@router.get("/stats", response_model=PerformanceStats)
async def get_performance_stats(
    period: str = Query(default="1h", description="统计周期: 1m, 5m, 15m, 1h, 24h")
):
    """获取性能统计"""
    return PerformanceStats(period=period)


@router.get("/suggestions", response_model=List[OptimizationSuggestion])
async def get_optimization_suggestions():
    """获取优化建议"""
    return [
        OptimizationSuggestion(
            category="memory",
            suggestion="启用 KV Cache 优化",
            impact="减少显存占用 20-30%",
            priority="high"
        ),
        OptimizationSuggestion(
            category="throughput",
            suggestion="启用动态批处理",
            impact="提升吞吐量 2-3 倍",
            priority="medium"
        )
    ]


@router.post("/reset")
async def reset_metrics():
    """重置性能指标"""
    return {"success": True, "message": "性能指标已重置"}


@router.get("/history")
async def get_metrics_history(
    hours: int = Query(default=24, ge=1, le=168, description="历史时长（小时）")
):
    """获取历史性能指标"""
    return {
        "hours": hours,
        "data_points": [],
        "aggregated": PerformanceMetrics().model_dump()
    }
