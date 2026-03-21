"""
技能发现与注册系统测试
"""
import asyncio
from pathlib import Path

from skills import (
    SkillScanner,
    SkillLifecycleManager,
    EnhancedSkillRegistry,
    get_enhanced_registry,
    get_lifecycle_manager,
    create_scanner,
    LifecycleEventType,
)


def test_scanner():
    print("\n=== 测试扫描器 ===")
    
    skills_dir = Path(__file__).parent / "implemented"
    scanner = create_scanner(skills_dir=skills_dir)
    
    report = scanner.scan_directory()
    
    print(f"扫描结果: 总计 {report.total_scanned} 个文件")
    print(f"  - 成功: {report.successful}")
    print(f"  - 失败: {report.failed}")
    print(f"  - 跳过: {report.skipped}")
    print(f"  - 耗时: {report.duration_ms}ms")
    
    for result in report.results:
        if result.metadata:
            print(f"  发现技能: {result.skill_name} ({result.metadata.category})")
    
    return scanner, report


def test_registry():
    print("\n=== 测试注册器 ===")
    
    registry = get_enhanced_registry()
    
    from skills.implemented.text_skills import TextTransformSkill, WordCountSkill
    
    registry.register(TextTransformSkill)
    registry.register(WordCountSkill)
    
    print(f"已注册技能: {registry.list_skills()}")
    print(f"统计信息: {registry.get_stats()}")
    
    text_meta = registry.get_metadata("text_transform")
    if text_meta:
        print(f"text_transform 元数据: {text_meta.display_name}")
    
    return registry


async def test_execution():
    print("\n=== 测试技能执行 ===")
    
    registry = get_enhanced_registry()
    
    execution = await registry.execute(
        name="text_transform",
        parameters={"text": "Hello World", "operation": "uppercase"},
    )
    
    print(f"执行状态: {execution.status}")
    if execution.result:
        print(f"执行结果: {execution.result.data}")
        print(f"执行时间: {execution.result.execution_time:.3f}s")
    
    execution2 = await registry.execute(
        name="word_count",
        parameters={"text": "Hello World\nThis is a test."},
    )
    
    print(f"字数统计结果: {execution2.result.data if execution2.result else None}")


def test_lifecycle():
    print("\n=== 测试生命周期管理 ===")
    
    skills_dir = Path(__file__).parent / "implemented"
    lifecycle = SkillLifecycleManager(skills_dir=skills_dir)
    
    events = []
    
    def on_load(event):
        events.append(f"LOAD: {event.skill_name}")
        print(f"  事件: {event.event_type.value} - {event.skill_name}")
    
    def on_unload(event):
        events.append(f"UNLOAD: {event.skill_name}")
        print(f"  事件: {event.event_type.value} - {event.skill_name}")
    
    lifecycle.on(LifecycleEventType.AFTER_LOAD, on_load)
    lifecycle.on(LifecycleEventType.AFTER_UNLOAD, on_unload)
    
    results = lifecycle.load_all()
    print(f"加载结果: {len([r for r in results.values() if r.success])} 成功")
    
    stats = lifecycle.get_status_report()
    print(f"状态报告: {stats['load_states']}")
    
    return lifecycle


def test_dependencies():
    print("\n=== 测试依赖管理 ===")
    
    registry = get_enhanced_registry()
    
    deps = registry.get_dependencies("text_transform")
    print(f"text_transform 依赖: {deps}")
    
    dependents = registry.get_dependents("text_transform")
    print(f"依赖 text_transform 的技能: {dependents}")
    
    load_order = registry.get_load_order()
    print(f"加载顺序: {load_order}")


def test_search():
    print("\n=== 测试技能搜索 ===")
    
    registry = get_enhanced_registry()
    
    by_category = registry.list_skills_by_category("data")
    print(f"按类别搜索(data): {by_category}")
    
    by_tag = registry.list_skills_by_tag("text")
    print(f"按标签搜索(text): {by_tag}")
    
    search_results = registry.search_skills(query="text")
    print(f"关键词搜索(text): {search_results}")


def main():
    print("=" * 50)
    print("技能发现与注册系统测试")
    print("=" * 50)
    
    test_scanner()
    test_registry()
    test_dependencies()
    test_search()
    test_lifecycle()
    
    asyncio.run(test_execution())
    
    print("\n" + "=" * 50)
    print("所有测试完成")
    print("=" * 50)


if __name__ == "__main__":
    main()
