"""
Heartbeat 综合测试
"""
import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch
import json

from heartbeat import HeartbeatScheduler, TaskExecutor
from heartbeat.task_executor import TaskType, TaskPriority, TaskResult


class TestHeartbeatScheduler:
    """心跳调度器测试"""
    
    def test_create_scheduler(self):
        """测试创建调度器"""
        scheduler = HeartbeatScheduler()
        
        assert scheduler is not None
    
    def test_register_task(self):
        """测试注册任务"""
        scheduler = HeartbeatScheduler()
        
        async def test_task():
            return {"status": "ok"}
        
        task_id = scheduler.register_task(
            name="test_task",
            task_func=test_task,
            interval_seconds=60
        )
        
        assert task_id is not None
    
    def test_unregister_task(self):
        """测试取消注册任务"""
        scheduler = HeartbeatScheduler()
        
        async def test_task():
            return {"status": "ok"}
        
        task_id = scheduler.register_task(
            name="test_task_2",
            task_func=test_task,
            interval_seconds=60
        )
        
        result = scheduler.unregister_task(task_id)
        
        assert result is True
    
    @pytest.mark.asyncio
    async def test_execute_task(self):
        """测试执行任务"""
        scheduler = HeartbeatScheduler()
        
        executed = False
        
        async def test_task():
            nonlocal executed
            executed = True
            return {"status": "ok"}
        
        task_id = scheduler.register_task(
            name="test_task_3",
            task_func=test_task,
            interval_seconds=60
        )
        
        await scheduler.execute_task(task_id)
        
        assert executed is True


class TestTaskExecutor:
    """任务执行器测试"""
    
    def test_create_executor(self):
        """测试创建执行器"""
        executor = TaskExecutor()
        
        assert executor is not None
    
    @pytest.mark.asyncio
    async def test_execute_simple_task(self):
        """测试执行简单任务"""
        executor = TaskExecutor()
        
        result = await executor.execute(
            task_type=TaskType.CHECK,
            params={"target": "system"}
        )
        
        assert result is not None
    
    @pytest.mark.asyncio
    async def test_execute_report_task(self):
        """测试执行报告任务"""
        executor = TaskExecutor()
        
        result = await executor.execute(
            task_type=TaskType.REPORT,
            params={"report_type": "daily"}
        )
        
        assert result is not None
    
    @pytest.mark.asyncio
    async def test_execute_reminder_task(self):
        """测试执行提醒任务"""
        executor = TaskExecutor()
        
        result = await executor.execute(
            task_type=TaskType.REMINDER,
            params={"message": "Test reminder"}
        )
        
        assert result is not None


class TestTaskPriority:
    """任务优先级测试"""
    
    def test_priority_order(self):
        """测试优先级顺序"""
        assert TaskPriority.HIGH.value < TaskPriority.NORMAL.value
        assert TaskPriority.NORMAL.value < TaskPriority.LOW.value
    
    def test_priority_comparison(self):
        """测试优先级比较"""
        high = TaskPriority.HIGH
        normal = TaskPriority.NORMAL
        low = TaskPriority.LOW
        
        assert high < normal
        assert normal < low
        assert high < low


class TestTaskResult:
    """任务结果测试"""
    
    def test_success_result(self):
        """测试成功结果"""
        result = TaskResult(
            success=True,
            data={"key": "value"},
            message="Task completed"
        )
        
        assert result.success is True
        assert result.data["key"] == "value"
    
    def test_failure_result(self):
        """测试失败结果"""
        result = TaskResult(
            success=False,
            error="Task failed",
            message="Error occurred"
        )
        
        assert result.success is False
        assert result.error == "Task failed"


class TestHeartbeatIntegration:
    """心跳集成测试"""
    
    @pytest.mark.asyncio
    async def test_full_task_lifecycle(self):
        """测试完整任务生命周期"""
        scheduler = HeartbeatScheduler()
        executor = TaskExecutor()
        
        call_count = 0
        
        async def counting_task():
            nonlocal call_count
            call_count += 1
            return TaskResult(
                success=True,
                data={"count": call_count}
            )
        
        task_id = scheduler.register_task(
            name="counting_task",
            task_func=counting_task,
            interval_seconds=1
        )
        
        await scheduler.execute_task(task_id)
        await scheduler.execute_task(task_id)
        
        assert call_count == 2
        
        scheduler.unregister_task(task_id)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
