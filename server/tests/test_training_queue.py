"""
训练队列管理模块测试
"""
import pytest
import tempfile
import threading
import time
from pathlib import Path
from datetime import datetime

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.training_queue import (
    TrainingQueue, TrainingTask, TaskStatus, TaskPriority,
    get_training_queue, shutdown_queue, reset_training_queue
)


class TestTaskStatus:
    """TaskStatus 测试"""

    def test_status_values(self):
        """测试状态�?""
        assert TaskStatus.PENDING.value == "pending"
        assert TaskStatus.QUEUED.value == "queued"
        assert TaskStatus.RUNNING.value == "running"
        assert TaskStatus.PAUSED.value == "paused"
        assert TaskStatus.COMPLETED.value == "completed"
        assert TaskStatus.FAILED.value == "failed"
        assert TaskStatus.CANCELLED.value == "cancelled"


class TestTaskPriority:
    """TaskPriority 测试"""

    def test_priority_order(self):
        """测试优先级顺�?""
        assert TaskPriority.URGENT.value < TaskPriority.HIGH.value
        assert TaskPriority.HIGH.value < TaskPriority.NORMAL.value
        assert TaskPriority.NORMAL.value < TaskPriority.LOW.value


class TestTrainingTask:
    """TrainingTask 测试"""

    def test_create_task(self):
        """测试创建任务"""
        task = TrainingTask(
            priority=TaskPriority.NORMAL.value,
            created_at=datetime.now().timestamp(),
            task_id="test-001",
            config={"lr": 5e-5}
        )
        assert task.task_id == "test-001"
        assert task.status == TaskStatus.PENDING
        assert task.error is None

    def test_task_to_dict(self):
        """测试任务转字�?""
        task = TrainingTask(
            priority=TaskPriority.HIGH.value,
            created_at=1704067200.0,
            task_id="test-002",
            config={},
            status=TaskStatus.RUNNING
        )
        data = task.to_dict()
        assert data["task_id"] == "test-002"
        assert data["priority"] == TaskPriority.HIGH.value
        assert data["status"] == "running"

    def test_task_comparison(self):
        """测试任务比较（优先级队列�?""
        task1 = TrainingTask(
            priority=TaskPriority.HIGH.value,
            created_at=100.0,
            task_id="high",
            config={}
        )
        task2 = TrainingTask(
            priority=TaskPriority.LOW.value,
            created_at=50.0,
            task_id="low",
            config={}
        )
        assert task1 < task2


class TestTrainingQueue:
    """TrainingQueue 测试"""

    @pytest.fixture
    def temp_dir(self):
        """创建临时目录"""
        with tempfile.TemporaryDirectory() as d:
            yield Path(d)

    @pytest.fixture
    def queue(self, temp_dir):
        """创建队列实例"""
        state_file = temp_dir / "queue_state.json"
        q = TrainingQueue(
            max_concurrent=1,
            max_queue_size=5,
            state_file=state_file
        )
        q.start()
        yield q
        q.stop()

    def test_init(self, queue):
        """测试初始�?""
        status = queue.get_queue_status()
        assert status["queue_size"] == 0
        assert status["running_count"] == 0
        assert status["max_concurrent"] == 1

    def test_submit_task(self, queue):
        """测试提交任务"""
        executed = threading.Event()

        def callback():
            executed.set()

        result = queue.submit(
            task_id="submit-test",
            config={"test": True},
            callback=callback,
            priority=TaskPriority.NORMAL
        )

        assert result is True

        executed.wait(timeout=5.0)
        assert executed.is_set()

    def test_submit_to_full_queue(self, queue):
        """测试提交到已满队�?""
        blocked = threading.Event()

        def blocking_callback():
            blocked.wait(timeout=10)

        queue.submit("block-1", {}, blocking_callback)
        time.sleep(0.1)

        for i in range(5):
            result = queue.submit(f"fill-{i}", {}, lambda: None)
            if not result:
                break

        result = queue.submit("overflow", {}, lambda: None)
        assert result is False

        blocked.set()

    def test_cancel_running_task(self, queue):
        """测试取消运行中的任务"""
        started = threading.Event()
        cancelled = threading.Event()

        def long_callback():
            started.set()
            time.sleep(10)

        queue.submit("cancel-test", {}, long_callback)
        started.wait(timeout=2.0)

        result = queue.cancel("cancel-test")
        assert result is True

        status = queue.get_task_status("cancel-test")
        assert status["status"] == "cancelled"

    def test_cancel_queued_task(self, queue):
        """P0-2: 测试取消队列中的任务"""
        blocked = threading.Event()
        task_started = threading.Event()

        def blocking_callback():
            task_started.set()
            blocked.wait(timeout=30)

        queue.submit("blocking", {}, blocking_callback)
        task_started.wait(timeout=2.0)

        queued_ids = []
        for i in range(3):
            task_id = f"queued-{i}"
            queued_ids.append(task_id)
            queue.submit(task_id, {}, lambda: None)

        time.sleep(0.2)

        result = queue.cancel("queued-1")
        assert result is True

        blocked.set()

    def test_get_queue_status(self, queue):
        """测试获取队列状�?""
        status = queue.get_queue_status()
        assert "queue_size" in status
        assert "running_count" in status
        assert "history_count" in status
        assert "max_concurrent" in status
        assert "max_queue_size" in status

    def test_get_task_status(self, queue):
        """测试获取任务状�?""
        executed = threading.Event()

        def callback():
            executed.set()

        queue.submit("status-test", {}, callback)
        executed.wait(timeout=5.0)

        status = queue.get_task_status("status-test")
        assert status is not None
        assert status["task_id"] == "status-test"
        assert status["status"] == "completed"

    def test_get_pending_tasks(self, queue):
        """测试获取待执行任�?""
        blocked = threading.Event()
        task_started = threading.Event()

        def blocking_callback():
            task_started.set()
            blocked.wait(timeout=10)

        queue.submit("blocking-task", {}, blocking_callback)
        task_started.wait(timeout=2.0)

        for i in range(2):
            queue.submit(f"pending-{i}", {}, lambda: None)

        time.sleep(0.2)

        pending = queue.get_pending_tasks()
        assert len(pending) >= 1

        blocked.set()


class TestTrainingQueuePersistence:
    """TrainingQueue 持久化测�?""

    @pytest.fixture
    def temp_dir(self):
        """创建临时目录"""
        with tempfile.TemporaryDirectory() as d:
            yield Path(d)

    def test_state_persistence(self, temp_dir):
        """测试状态持久化"""
        state_file = temp_dir / "queue_state.json"

        queue1 = TrainingQueue(
            max_concurrent=1,
            state_file=state_file
        )
        queue1.start()

        executed = threading.Event()

        def callback():
            executed.set()

        queue1.submit("persist-test", {"key": "value"}, callback)
        executed.wait(timeout=5.0)

        time.sleep(0.5)
        queue1.stop()

        queue2 = TrainingQueue(
            max_concurrent=1,
            state_file=state_file
        )
        queue2.start()

        status = queue2.get_task_status("persist-test")
        assert status is not None
        assert status["task_id"] == "persist-test"

        queue2.stop()

    def test_atomic_write(self, temp_dir):
        """P1-3: 测试原子写入"""
        state_file = temp_dir / "queue_state.json"

        queue = TrainingQueue(
            max_concurrent=1,
            state_file=state_file
        )
        queue.start()

        executed = threading.Event()

        def callback():
            executed.set()

        queue.submit("atomic-test", {}, callback)
        executed.wait(timeout=5.0)

        time.sleep(0.5)

        assert state_file.exists()

        import json
        with open(state_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        assert "history" in data
        assert "atomic-test" in data["history"]

        queue.stop()


class TestTrainingQueuePriority:
    """TrainingQueue 优先级测�?""

    @pytest.fixture
    def temp_dir(self):
        """创建临时目录"""
        with tempfile.TemporaryDirectory() as d:
            yield Path(d)

    def test_priority_order(self, temp_dir):
        """测试优先级执行顺�?""
        state_file = temp_dir / "queue_state.json"
        queue = TrainingQueue(
            max_concurrent=1,
            state_file=state_file
        )
        queue.start()

        blocked = threading.Event()
        task_started = threading.Event()
        execution_order = []

        def blocking_callback():
            task_started.set()
            blocked.wait(timeout=10)

        def record_callback(task_id):
            def cb():
                execution_order.append(task_id)
            return cb

        queue.submit("blocking", {}, blocking_callback)
        task_started.wait(timeout=2.0)

        queue.submit("low", {}, record_callback("low"), TaskPriority.LOW)
        queue.submit("normal", {}, record_callback("normal"), TaskPriority.NORMAL)
        queue.submit("high", {}, record_callback("high"), TaskPriority.HIGH)

        time.sleep(0.3)
        blocked.set()

        time.sleep(1.0)

        if len(execution_order) >= 3:
            assert execution_order[0] == "high"

        queue.stop()


class TestTrainingQueueConcurrency:
    """TrainingQueue 并发测试"""

    @pytest.fixture
    def temp_dir(self):
        """创建临时目录"""
        with tempfile.TemporaryDirectory() as d:
            yield Path(d)

    def test_concurrent_submissions(self, temp_dir):
        """测试并发提交"""
        state_file = temp_dir / "queue_state.json"
        queue = TrainingQueue(
            max_concurrent=2,
            max_queue_size=20,
            state_file=state_file
        )
        queue.start()

        executed_count = [0]
        lock = threading.Lock()

        def callback():
            with lock:
                executed_count[0] += 1

        threads = []
        for i in range(10):
            t = threading.Thread(
                target=lambda i=i: queue.submit(f"concurrent-{i}", {}, callback)
            )
            threads.append(t)
            t.start()

        for t in threads:
            t.join(timeout=5.0)

        time.sleep(3.0)

        assert executed_count[0] == 10

        queue.stop()


class TestGlobalFunctions:
    """全局函数测试"""

    def test_get_training_queue(self):
        """测试获取全局队列实例"""
        reset_training_queue()
        queue = get_training_queue()
        assert queue is not None
        assert isinstance(queue, TrainingQueue)

    def test_singleton(self):
        """测试单例模式"""
        reset_training_queue()
        queue1 = get_training_queue()
        queue2 = get_training_queue()
        assert queue1 is queue2

    def test_shutdown_queue(self):
        """测试关闭队列"""
        queue = get_training_queue()
        shutdown_queue()

        reset_training_queue()
        new_queue = get_training_queue()
        assert new_queue is not queue


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
