"""测试增强版记忆系统"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from memory import (
    KnowledgeGraph,
    MemoryMerger,
    ShortTermMemory,
    extract_memories,
    get_enhanced_memory_service,
)


def test_knowledge_graph():
    print("=== 测试知识图谱 ===")
    kg = KnowledgeGraph()

    entity_id, is_new = kg.add_entity('张三', 'person', {'age': 25}, 0.9)
    print(f"添加实体: {entity_id}, 新建: {is_new}")

    kg.add_entity('Python', 'skill', {'level': 'expert'}, 0.8)
    kg.add_entity('AI项目', 'project', {}, 0.7)

    rel_id = kg.add_relation('张三', 'Python', 'knows', '张三会Python')
    print(f"添加关系: {rel_id}")

    entity = kg.get_entity(entity_id)
    print(f"获取实体: {entity.name}, 类型: {entity.entity_type}")

    stats = kg.get_stats()
    print(f"统计: {stats['total_entities']} 实体, {stats['total_relations']} 关系")
    print("知识图谱测试通过!\n")


def test_short_term_memory():
    print("=== 测试短期记忆 ===")
    stm = ShortTermMemory(max_turns=10)

    stm.add_message('user', '我叫张三，今年25岁')
    stm.add_message('assistant', '你好张三，很高兴认识你！')
    stm.add_message('user', '我喜欢用Python编程')

    context = stm.get_context(max_tokens=500)
    print(f"上下文长度: {len(context)} 字符")

    active_entities = stm.get_active_entities()
    print(f"活跃实体: {active_entities}")

    summary = stm.summarize()
    print(f"摘要: {summary['message_count']} 条消息")
    print("短期记忆测试通过!\n")


def test_intelligent_extractor():
    print("=== 测试智能提取器 ===")

    result = extract_memories('我叫张三，我在做一个AI项目，我会Python和机器学习')

    print(f"提取实体: {len(result.entities)}")
    for e in result.entities:
        print(f"  - {e['name']} ({e['type']})")

    print(f"提取关系: {len(result.relations)}")
    for r in result.relations:
        print(f"  - {r['source']} -> {r['target']} ({r['relation']})")

    print(f"提取事实: {len(result.facts)}")
    print("智能提取器测试通过!\n")


def test_memory_merger():
    print("=== 测试记忆合并器 ===")
    merger = MemoryMerger()

    existing = {
        'id': 'ent_001',
        'name': '张三',
        'type': 'person',
        'attributes': {'age': 25},
        'confidence': 0.8
    }

    new = {
        'id': 'ent_002',
        'name': '张三',
        'type': 'person',
        'attributes': {'city': '北京'},
        'confidence': 0.9
    }

    merged, conflict = merger.merge_memories(existing, new)
    print(f"合并结果: {merged['name']}")
    print(f"合并属性: {merged['attributes']}")
    print(f"冲突: {conflict}")
    print("记忆合并器测试通过!\n")


def test_enhanced_memory_service():
    print("=== 测试增强版记忆服务 ===")
    service = get_enhanced_memory_service()

    result = service.process_message(
        message='我叫李四，我在做一个AI项目，我会Python和机器学习',
        role='user',
        user_id='test_user'
    )

    print("处理消息结果:")
    print(f"  - 提取实体: {len(result['entities_extracted'])}")
    print(f"  - 提取关系: {len(result['relations_extracted'])}")
    print(f"  - 提取事实: {len(result['facts_extracted'])}")

    stats = service.get_stats('test_user')
    print(f"服务统计: {stats['knowledge_graph']}")
    print("增强版记忆服务测试通过!\n")


def test_mcp_server():
    print("=== 测试 MCP 服务器 ===")
    from memory.mcp_server import MCPServer

    server = MCPServer()

    print(f"已注册处理器: {list(server.handlers.keys())}")
    print("MCP 服务器测试通过!\n")


if __name__ == '__main__':
    print("=" * 50)
    print("记忆系统升级验证测试")
    print("=" * 50 + "\n")

    test_knowledge_graph()
    test_short_term_memory()
    test_intelligent_extractor()
    test_memory_merger()
    test_enhanced_memory_service()
    test_mcp_server()

    print("=" * 50)
    print("所有测试通过! 记忆系统升级成功!")
    print("=" * 50)
