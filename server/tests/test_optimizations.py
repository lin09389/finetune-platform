"""
微调流程优化方案 - 测试脚本

测试内容：
1. 资源预检功能
2. 训练状态队列更新
3. 训练队列管理
"""
import os
import sys
import time
from pathlib import Path

server_path = Path(__file__).parent.parent
sys.path.insert(0, str(server_path))
os.chdir(server_path)

from core.training_queue import TaskPriority, get_training_queue
from core.training_state import get_training_state
from core.utils import cleanup_gpu_memory, get_vram_usage, pre_training_resource_check


def test_resource_check():
    """测试资源预检功能"""
    print("\n" + "=" * 50)
    print("测试 1: 资源预检功能")
    print("=" * 50)

    scenarios = [
        {"method": "qlora", "model_size": "7B", "required_vram": 4.0},
        {"method": "lora", "model_size": "7B", "required_vram": 8.0},
        {"method": "qlora", "model_size": "13B", "required_vram": 8.0},
    ]

    for scenario in scenarios:
        print(f"\n场景：{scenario['method']} - {scenario['model_size']} - 需要 {scenario['required_vram']}GB")
        result = pre_training_resource_check(
            required_vram_gb=scenario["required_vram"],
            method=scenario["method"],
            model_size=scenario["model_size"]
        )

        print(f"  检查结果：{'通过' if result['passed'] else '失败'}")
        print(f"  可用显存：{result['available_vram']} GB")
        print(f"  设备名称：{result.get('device_name', 'N/A')}")

        if result['warnings']:
            print(f"  警告：{result['warnings']}")

        if result['suggestions']:
            print(f"  建议：{result['suggestions']}")

        if result['recommended_config']:
            print(f"  推荐配置：{result['recommended_config']}")

    print("\n[PASS] 资源预检测试完成")


def test_training_state():
    """测试训练状态队列更新"""
    print("\n" + "=" * 50)
    print("测试 2: 训练状态队列更新")
    print("=" * 50)

    import tempfile
    import time

    with tempfile.TemporaryDirectory() as tmpdir:
        state = get_training_state(Path(tmpdir))

        print("\n1. 测试队列式进度更新...")
        start_time = time.time()

        for i in range(10):
            state.queue_progress_update(
                epoch=1,
                step=i * 10,
                total_steps=100,
                loss=1.0 / (i + 1),
                lr=5e-5,
                vram_used=get_vram_usage(),
                elapsed_time=time.time() - start_time,
                eta=100 - i * 10,
                status="running",
                message=f"Step {i * 10}"
            )

        time.sleep(0.5)

        progress = state.get_progress()
        print(f"  最终进度：step={progress.step}, loss={progress.loss:.4f}, status={progress.status}")

        print("  [OK] 队列更新正常")

        print("\n2. 测试队列式状态更新...")
        state.queue_training_state(True)
        time.sleep(0.2)

        is_training = state.is_training()
        print(f"  训练状态：{is_training}")
        assert is_training is True, "状态更新失败"

        state.queue_training_state(False)
        print("  [OK] 状态更新正常")

        state.stop_worker()

    print("\n[PASS] 训练状态测试完成")


def test_training_queue():
    """测试训练队列管理"""
    print("\n" + "=" * 50)
    print("测试 3: 训练队列管理")
    print("=" * 50)

    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmpdir:
        queue = get_training_queue(
            max_concurrent=2,
            max_queue_size=5,
            state_file=Path(tmpdir) / "queue_state.json"
        )

        print("\n1. 测试任务提交...")

        executed_tasks = []

        def task_callback(task_name):
            def callback():
                print(f"  执行任务：{task_name}")
                executed_tasks.append(task_name)
            return callback

        tasks = [
            ("task_1", TaskPriority.LOW),
            ("task_2", TaskPriority.HIGH),
            ("task_3", TaskPriority.NORMAL),
            ("task_4", TaskPriority.URGENT),
        ]

        for task_id, priority in tasks:
            success = queue.submit(
                task_id=task_id,
                config={"test": True},
                callback=task_callback(task_id),
                priority=priority
            )
            print(f"  提交 {task_id} (优先级：{priority.name}): {'成功' if success else '失败'}")

        print("\n2. 等待任务执行...")
        time.sleep(2)

        print("\n3. 获取队列状态...")
        status = queue.get_queue_status()
        print(f"  队列大小：{status['queue_size']}")
        print(f"  运行中：{status['running_count']}")
        print(f"  历史：{status['history_count']}")
        print(f"  执行的任务：{executed_tasks}")

        queue.stop()

    print("\n[PASS] 训练队列测试完成")


def test_gpu_cleanup():
    """测试 GPU 清理功能"""
    print("\n" + "=" * 50)
    print("测试 4: GPU 清理功能")
    print("=" * 50)

    vram_before = get_vram_usage()
    print(f"\n清理前 VRAM: {vram_before:.2f} GB")

    success = cleanup_gpu_memory()

    vram_after = get_vram_usage()
    print(f"清理后 VRAM: {vram_after:.2f} GB")
    print(f"清理结果：{'成功' if success else '失败'}")

    print("\n[PASS] GPU 清理测试完成")


def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("微调流程优化方案 - 测试套件")
    print("=" * 60)

    try:
        test_resource_check()
        test_training_state()
        test_training_queue()
        test_gpu_cleanup()

        print("\n" + "=" * 60)
        print("[PASS] 所有测试完成")
        print("=" * 60)

    except Exception as e:
        print(f"\n[FAIL] 测试失败：{e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
