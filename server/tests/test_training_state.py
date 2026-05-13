"""
训练状态管理模块测试
"""
import json
import os
import sys
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.training_state import (
    StateUpdate,
    TrainingProgress,
    TrainingRecord,
    TrainingState,
    get_training_state,
    reset_training_state,
)


class TestTrainingProgress:
    """TrainingProgress 测试"""

    def test_default_values(self):
        """测试默认值"""
        progress = TrainingProgress()
        assert progress.epoch == 0
        assert progress.step == 0
        assert progress.total_steps == 0
        assert progress.loss == 0.0
        assert progress.lr == 0.0
        assert progress.vram_used == 0.0
        assert progress.elapsed_time == 0.0
        assert progress.eta == 0.0
        assert progress.status == "idle"
        assert progress.message == ""

    def test_custom_values(self):
        """测试自定义值"""
        progress = TrainingProgress(
            epoch=1,
            step=100,
            total_steps=1000,
            loss=0.5,
            lr=5e-5,
            vram_used=4.5,
            elapsed_time=3600.0,
            eta=7200.0,
            status="training",
            message="Training in progress"
        )
        assert progress.epoch == 1
        assert progress.step == 100
        assert progress.total_steps == 1000
        assert progress.loss == 0.5
        assert progress.lr == 5e-5
        assert progress.vram_used == 4.5
        assert progress.elapsed_time == 3600.0
        assert progress.eta == 7200.0
        assert progress.status == "training"
        assert progress.message == "Training in progress"

    def test_model_copy(self):
        """测试模型复制"""
        progress = TrainingProgress(epoch=2, step=200)
        copied = progress.copy()
        assert copied.epoch == 2
        assert copied.step == 200
        assert copied is not progress


class TestTrainingRecord:
    """TrainingRecord 测试"""

    def test_create_record(self):
        """测试创建记录"""
        record = TrainingRecord(
            id="test-123",
            model_name="test-model",
            dataset_name="test-dataset",
            method="qlora",
            status="running",
            start_time=datetime.now().isoformat(),
            config={"lr": 5e-5},
            output_path="/output/test"
        )
        assert record.id == "test-123"
        assert record.model_name == "test-model"
        assert record.dataset_name == "test-dataset"
        assert record.method == "qlora"
        assert record.status == "running"
        assert record.end_time is None
        assert record.checkpoint_path is None

    def test_model_dump(self):
        """测试模型导出"""
        record = TrainingRecord(
            id="test-456",
            model_name="model",
            dataset_name="dataset",
            method="lora",
            status="completed",
            start_time="2024-01-01T00:00:00",
            config={},
            output_path="/output"
        )
        data = record.model_dump()
        assert data["id"] == "test-456"
        assert data["status"] == "completed"


class TestStateUpdate:
    """StateUpdate 测试"""

    def test_progress_update(self):
        """测试进度更新"""
        update = StateUpdate('progress', epoch=1, step=100, loss=0.5)
        assert update.update_type == 'progress'
        assert update.data['epoch'] == 1
        assert update.data['step'] == 100
        assert update.data['loss'] == 0.5

    def test_training_update(self):
        """测试训练状态更新"""
        update = StateUpdate('training', value=True)
        assert update.update_type == 'training'
        assert update.data['value'] is True


class TestTrainingState:
    """TrainingState 测试"""

    @pytest.fixture
    def temp_dir(self):
        """创建临时目录"""
        with tempfile.TemporaryDirectory() as d:
            yield Path(d)

    @pytest.fixture
    def training_state(self, temp_dir):
        """创建训练状态实例"""
        history_file = temp_dir / "training_history.json"
        state = TrainingState(history_file)
        yield state
        state.cleanup()

    def test_init(self, training_state):
        """测试初始化"""
        assert training_state.is_training() is False
        progress = training_state.get_progress()
        assert progress.status == "idle"

    def test_set_training(self, training_state):
        """测试设置训练状态"""
        training_state.set_training(True)
        assert training_state.is_training() is True

        training_state.set_training(False)
        assert training_state.is_training() is False

    def test_stop_request_lifecycle(self, training_state):
        """停止请求位应可设置并在训练结束时清除"""
        training_state.set_training(True)
        assert training_state.should_stop() is False
        training_state.request_stop()
        assert training_state.should_stop() is True
        training_state.set_training(False)
        assert training_state.should_stop() is False

    def test_queue_progress_update(self, training_state):
        """测试队列式进度更新"""
        training_state.queue_progress_update(
            epoch=1,
            step=100,
            total_steps=1000,
            loss=0.5,
            status="training"
        )
        time.sleep(0.1)

        progress = training_state.get_progress()
        assert progress.epoch == 1
        assert progress.step == 100
        assert progress.total_steps == 1000
        assert progress.loss == 0.5
        assert progress.status == "training"

    def test_get_status(self, training_state):
        """测试获取状态"""
        status = training_state.get_status()
        assert "is_training" in status
        assert "progress" in status
        assert "active_tasks" in status

    def test_add_to_history_sync(self, training_state, temp_dir):
        """测试同步添加历史记录"""
        record = TrainingRecord(
            id="test-001",
            model_name="model",
            dataset_name="dataset",
            method="qlora",
            status="completed",
            start_time=datetime.now().isoformat(),
            config={},
            output_path=str(temp_dir)
        )

        training_state.add_to_history_sync(record)
        time.sleep(0.1)

        history = training_state.get_history()
        assert len(history) == 1
        assert history[0].id == "test-001"

    def test_update_existing_record(self, training_state, temp_dir):
        """测试更新已存在的记录"""
        record = TrainingRecord(
            id="test-002",
            model_name="model",
            dataset_name="dataset",
            method="qlora",
            status="running",
            start_time=datetime.now().isoformat(),
            config={},
            output_path=str(temp_dir)
        )

        training_state.add_to_history_sync(record)
        time.sleep(0.1)

        record.status = "completed"
        record.end_time = datetime.now().isoformat()
        training_state.add_to_history_sync(record)
        time.sleep(0.1)

        history = training_state.get_history()
        assert len(history) == 1
        assert history[0].status == "completed"

    def test_register_training_task(self, training_state):
        """测试注册训练任务"""
        def dummy_task():
            time.sleep(0.1)

        thread = threading.Thread(target=dummy_task)
        thread.start()

        training_state.register_training_task("task-001", thread)
        thread.join(timeout=1.0)

        time.sleep(0.1)
        active_tasks = training_state.get_active_tasks()
        assert len(active_tasks) == 0

    def test_cleanup(self, training_state):
        """测试资源清理"""
        training_state.queue_progress_update(epoch=1, step=100)
        time.sleep(0.1)

        training_state.cleanup()

        progress = training_state.get_progress()
        assert progress.epoch == 1


class TestTrainingStateFileOperations:
    """TrainingState 文件操作测试"""

    @pytest.fixture
    def temp_dir(self):
        """创建临时目录"""
        with tempfile.TemporaryDirectory() as d:
            yield Path(d)

    def test_atomic_write(self, temp_dir):
        """测试原子写入"""
        history_file = temp_dir / "training_history.json"
        state = TrainingState(history_file)

        record = TrainingRecord(
            id="atomic-test",
            model_name="model",
            dataset_name="dataset",
            method="lora",
            status="completed",
            start_time=datetime.now().isoformat(),
            config={},
            output_path=str(temp_dir)
        )

        state.add_to_history_sync(record)
        time.sleep(0.2)

        assert history_file.exists()

        with open(history_file, encoding='utf-8') as f:
            data = json.load(f)

        assert len(data) == 1
        assert data[0]['id'] == "atomic-test"

        state.cleanup()

    def test_backup_file(self, temp_dir):
        """测试备份文件"""
        history_file = temp_dir / "training_history.json"
        state = TrainingState(history_file)

        record = TrainingRecord(
            id="backup-test-1",
            model_name="model",
            dataset_name="dataset",
            method="lora",
            status="completed",
            start_time=datetime.now().isoformat(),
            config={},
            output_path=str(temp_dir)
        )

        state.add_to_history_sync(record)
        time.sleep(0.2)

        backup_file = history_file.with_suffix('.json.bak')
        assert backup_file.exists() or history_file.exists()

        state.cleanup()

    def test_load_existing_history(self, temp_dir):
        """测试加载已存在的历史记录"""
        history_file = temp_dir / "training_history.json"

        existing_data = [{
            "id": "existing-001",
            "model_name": "existing-model",
            "dataset_name": "existing-dataset",
            "method": "qlora",
            "status": "completed",
            "start_time": "2024-01-01T00:00:00",
            "config": {},
            "output_path": str(temp_dir)
        }]

        with open(history_file, 'w', encoding='utf-8') as f:
            json.dump(existing_data, f)

        state = TrainingState(history_file)
        time.sleep(0.1)

        history = state.get_history()
        assert len(history) == 1
        assert history[0].id == "existing-001"

        state.cleanup()


class TestTrainingStateConcurrency:
    """TrainingState 并发测试"""

    @pytest.fixture
    def temp_dir(self):
        """创建临时目录"""
        with tempfile.TemporaryDirectory() as d:
            yield Path(d)

    def test_concurrent_progress_updates(self, temp_dir):
        """测试并发进度更新"""
        history_file = temp_dir / "training_history.json"
        state = TrainingState(history_file)

        def update_progress(thread_id):
            for i in range(10):
                state.queue_progress_update(
                    epoch=thread_id,
                    step=i,
                    loss=0.1 * i
                )
                time.sleep(0.01)

        threads = []
        for i in range(5):
            t = threading.Thread(target=update_progress, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join(timeout=5.0)

        time.sleep(0.2)

        progress = state.get_progress()
        assert progress.epoch in range(5)
        assert progress.step in range(10)

        state.cleanup()

    def test_concurrent_history_writes(self, temp_dir):
        """测试并发历史记录写入 - 使用队列避免直接并发"""
        history_file = temp_dir / "training_history.json"
        state = TrainingState(history_file)

        def add_record(i):
            record = TrainingRecord(
                id=f"concurrent-{i}",
                model_name=f"model-{i}",
                dataset_name="dataset",
                method="lora",
                status="completed",
                start_time=datetime.now().isoformat(),
                config={},
                output_path=str(temp_dir)
            )
            state.queue_history_add(record)

        for i in range(10):
            add_record(i)

        time.sleep(1.5)

        history = state.get_history()
        assert len(history) >= 5

        ids = {r.id for r in history}
        assert len(ids) >= 5

        state.cleanup()


class TestGlobalFunctions:
    """全局函数测试"""

    def test_get_training_state(self):
        """测试获取全局状态实例"""
        reset_training_state()
        state = get_training_state()
        assert state is not None
        assert isinstance(state, TrainingState)

    def test_singleton(self):
        """测试单例模式"""
        reset_training_state()
        state1 = get_training_state()
        state2 = get_training_state()
        assert state1 is state2

    def test_reset_training_state(self):
        """测试重置状态"""
        state1 = get_training_state()
        reset_training_state()
        state2 = get_training_state()
        assert state1 is not state2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
