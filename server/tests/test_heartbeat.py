"""
Heartbeat 模块单元测试
"""
from datetime import datetime, timedelta

import pytest
from heartbeat import HeartbeatScheduler, HeartbeatTask
from heartbeat.task_executor import (
    ProactiveTask,
    TaskExecutor,
    TaskResult,
    TaskStatus,
    TaskType,
)


class TestHeartbeatScheduler:
    """Heartbeat 调度器测试"""

    @pytest.fixture
    def scheduler(self):
        return HeartbeatScheduler()

    @pytest.fixture
    def sample_task(self):
        return HeartbeatTask(
            id="task_1",
            name="Test Task",
            description="A test task",
            schedule="3600",
            enabled=True,
        )

    def test_add_task(self, scheduler, sample_task):
        """测试添加任务"""
        scheduler.add_task(sample_task)

        assert "task_1" in scheduler._tasks
        assert scheduler._tasks["task_1"].name == "Test Task"

    def test_remove_task(self, scheduler, sample_task):
        """测试移除任务"""
        scheduler.add_task(sample_task)
        scheduler.remove_task("task_1")

        assert "task_1" not in scheduler._tasks

    def test_enable_task(self, scheduler, sample_task):
        """测试启用任务"""
        sample_task.enabled = False
        scheduler.add_task(sample_task)
        scheduler.enable_task("task_1")

        assert scheduler._tasks["task_1"].enabled is True

    def test_disable_task(self, scheduler, sample_task):
        """测试禁用任务"""
        scheduler.add_task(sample_task)
        scheduler.disable_task("task_1")

        assert scheduler._tasks["task_1"].enabled is False

    def test_parse_heartbeat_file(self, scheduler):
        """测试解析 HEARTBEAT.md 文件"""
        content = """
# Heartbeat Tasks

- [ ] Check email | 1800
- [x] Generate report | 3600
- [ ] Send reminder | 60
"""

        tasks = scheduler.parse_heartbeat_file(content)

        assert len(tasks) == 3
        assert tasks[0].name == "Check email"
        assert tasks[0].schedule == "1800"
        assert tasks[0].enabled is True
        assert tasks[1].enabled is False

    def test_calculate_next_run_interval(self, scheduler, sample_task):
        """测试计算下次运行时间 - 间隔模式"""
        sample_task.schedule = "3600"
        sample_task.last_run = datetime.now()

        scheduler.add_task(sample_task)

        assert sample_task.next_run is not None
        expected = sample_task.last_run + timedelta(seconds=3600)
        assert abs((sample_task.next_run - expected).total_seconds()) < 1

    def test_get_due_tasks(self, scheduler):
        """测试获取到期任务"""
        task1 = HeartbeatTask(
            id="task_1",
            name="Due Task",
            description="A due task",
            schedule="0",
            enabled=True,
            next_run=datetime.now() - timedelta(seconds=10),
        )
        task2 = HeartbeatTask(
            id="task_2",
            name="Future Task",
            description="A future task",
            schedule="3600",
            enabled=True,
            next_run=datetime.now() + timedelta(seconds=3600),
        )

        scheduler.add_task(task1)
        scheduler.add_task(task2)

        due_tasks = scheduler._get_due_tasks()

        assert len(due_tasks) == 1
        assert due_tasks[0].id == "task_1"

    def test_get_stats(self, scheduler, sample_task):
        """测试获取统计信息"""
        scheduler.add_task(sample_task)

        stats = scheduler.get_stats()

        assert stats["total_tasks"] == 1
        assert stats["enabled_tasks"] == 1

    @pytest.mark.asyncio
    async def test_start_stop(self, scheduler):
        """测试启动和停止"""
        await scheduler.start()

        assert scheduler._is_running is True

        await scheduler.stop()

        assert scheduler._is_running is False

    @pytest.mark.asyncio
    async def test_execute_typed_task_with_executor(self, scheduler):
        """测试调度器将任务类型和配置传递给执行器"""
        executor = TaskExecutor()
        scheduler.set_task_executor(executor)

        task = HeartbeatTask(
            id="resource_check",
            name="Resource Check",
            description="Check local resource usage",
            schedule="60",
            enabled=True,
            metadata={
                "type": "check",
                "config": {"check_type": "resource_usage", "target": "local"},
            },
        )
        scheduler.add_task(task)

        result = await scheduler.execute_task("resource_check")

        assert result["status"] == "ok"
        assert result["metrics"]["cpu_percent"] >= 0
        assert executor.get_result("resource_check") is not None


class TestTaskExecutor:
    """任务执行器测试"""

    @pytest.fixture
    def executor(self):
        return TaskExecutor()

    @pytest.fixture
    def sample_task(self):
        return ProactiveTask(
            id="task_1",
            name="Test Task",
            task_type=TaskType.CHECK,
            description="A test task",
            schedule="3600",
            enabled=True,
        )

    def test_add_task(self, executor, sample_task):
        """测试添加任务"""
        executor.add_task(sample_task)

        assert "task_1" in executor._tasks

    def test_remove_task(self, executor, sample_task):
        """测试移除任务"""
        executor.add_task(sample_task)
        executor.remove_task("task_1")

        assert "task_1" not in executor._tasks

    @pytest.mark.asyncio
    async def test_execute_check_task(self, executor, sample_task):
        """测试执行检查任务"""
        executor.add_task(sample_task)

        result = await executor.execute_task("task_1")

        assert result.status == TaskStatus.COMPLETED
        assert result.task_id == "task_1"

    @pytest.mark.asyncio
    async def test_execute_disabled_task(self, executor, sample_task):
        """测试执行禁用任务"""
        sample_task.enabled = False
        executor.add_task(sample_task)

        result = await executor.execute_task("task_1")

        assert result.status == TaskStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_execute_nonexistent_task(self, executor):
        """测试执行不存在的任务"""
        result = await executor.execute_task("nonexistent")

        assert result.status == TaskStatus.FAILED
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_report_task(self, executor):
        """测试执行汇报任务"""
        task = ProactiveTask(
            id="report_task",
            name="Daily Report",
            task_type=TaskType.REPORT,
            description="Generate daily report",
            schedule="86400",
            enabled=True,
            config={"report_type": "daily"},
        )
        executor.add_task(task)

        result = await executor.execute_task("report_task")

        assert result.status == TaskStatus.COMPLETED
        assert "content" in result.result

    @pytest.mark.asyncio
    async def test_execute_reminder_task(self, executor):
        """测试执行提醒任务"""
        task = ProactiveTask(
            id="reminder_task",
            name="Meeting Reminder",
            task_type=TaskType.REMINDER,
            description="Send meeting reminder",
            schedule="60",
            enabled=True,
            config={"reminder_type": "meeting"},
        )
        executor.add_task(task)

        result = await executor.execute_task("reminder_task")

        assert result.status == TaskStatus.COMPLETED
        assert result.result["delivered"] is True

    def test_register_handler(self, executor):
        """测试注册处理器"""
        async def custom_handler(task):
            return {"custom": True}

        executor.register_handler(TaskType.CUSTOM, custom_handler)

        assert TaskType.CUSTOM in executor._handlers

    def test_get_result(self, executor, sample_task):
        """测试获取结果"""
        executor._results["task_1"] = TaskResult(
            task_id="task_1",
            task_type=TaskType.CHECK,
            status=TaskStatus.COMPLETED,
            started_at=datetime.now(),
        )

        result = executor.get_result("task_1")

        assert result is not None
        assert result.status == TaskStatus.COMPLETED

    def test_get_stats(self, executor, sample_task):
        """测试获取统计"""
        executor.add_task(sample_task)

        stats = executor.get_stats()

        assert stats["total_tasks"] == 1
        assert stats["enabled_tasks"] == 1

    def test_clear_old_results(self, executor):
        """测试清理旧结果"""
        old_result = TaskResult(
            task_id="old_task",
            task_type=TaskType.CHECK,
            status=TaskStatus.COMPLETED,
            started_at=datetime.now() - timedelta(days=10),
            completed_at=datetime.now() - timedelta(days=10),
        )
        new_result = TaskResult(
            task_id="new_task",
            task_type=TaskType.CHECK,
            status=TaskStatus.COMPLETED,
            started_at=datetime.now(),
            completed_at=datetime.now(),
        )

        executor._results["old_task"] = old_result
        executor._results["new_task"] = new_result

        cleaned = executor.clear_old_results(days=7)

        assert cleaned == 1
        assert "old_task" not in executor._results
        assert "new_task" in executor._results


class TestTaskTypes:
    """任务类型测试"""

    @pytest.mark.asyncio
    async def test_check_project_status(self):
        """测试项目状态检查"""
        executor = TaskExecutor()
        task = ProactiveTask(
            id="check_project",
            name="Check Project",
            task_type=TaskType.CHECK,
            config={"check_type": "project_status"},
        )
        executor.add_task(task)

        result = await executor.execute_task("check_project")

        assert result.status == TaskStatus.COMPLETED
        assert "status" in result.result

    @pytest.mark.asyncio
    async def test_check_resource_usage(self):
        """测试资源使用检查"""
        executor = TaskExecutor()
        task = ProactiveTask(
            id="check_resources",
            name="Check Resources",
            task_type=TaskType.CHECK,
            config={"check_type": "resource_usage"},
        )
        executor.add_task(task)

        result = await executor.execute_task("check_resources")

        assert result.status == TaskStatus.COMPLETED
        assert "metrics" in result.result
        metrics = result.result["metrics"]
        assert 0 <= metrics["cpu_percent"] <= 100
        assert 0 <= metrics["memory_percent"] <= 100
        assert 0 <= metrics["disk_percent"] <= 100
        assert metrics["memory_available_gb"] >= 0
        assert metrics["disk_free_gb"] >= 0
        assert metrics["source"] in {"psutil", "fallback"}

    @pytest.mark.asyncio
    async def test_generate_daily_report(self):
        """测试生成日报"""
        executor = TaskExecutor()
        task = ProactiveTask(
            id="daily_report",
            name="Daily Report",
            task_type=TaskType.REPORT,
            config={"report_type": "daily"},
        )
        executor.add_task(task)

        result = await executor.execute_task("daily_report")

        assert result.status == TaskStatus.COMPLETED
        assert "每日报告" in result.result["content"]

    @pytest.mark.asyncio
    async def test_send_meeting_reminder(self):
        """测试发送会议提醒"""
        executor = TaskExecutor()
        task = ProactiveTask(
            id="meeting_reminder",
            name="Meeting Reminder",
            task_type=TaskType.REMINDER,
            config={
                "reminder_type": "meeting",
                "meeting_title": "Team Standup",
                "meeting_time": "10:00",
            },
        )
        executor.add_task(task)

        result = await executor.execute_task("meeting_reminder")

        assert result.status == TaskStatus.COMPLETED
        assert result.result["delivered"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
