#!/usr/bin/env python3
"""
编码问题修复工具
修复检测到的编码损坏文件
"""

import os
import chardet
import json
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import re

PROJECT_ROOT = Path(r"c:\Users\JHJ\Desktop\finetune-platform")

FILES_TO_FIX = [
    "server/check_all_features.py",
    "server/test_all_features.py",
    "server/test_cloud_ai.py",
    "server/test_hf_mirror.py",
    "server/backup_old_modules/session.py",
    "server/memory/test_memory_system.py",
    "server/skills/test_skills_system.py",
    "server/tests/test_device.py",
    "server/tests/test_inference.py",
    "server/tests/test_models.py",
    "server/tests/test_training.py",
    "server/workspace/task_api.py",
]

SKIP_FILES = [
    "server/models/modelscope_cache/tiansz/bert-base-chinese/.mdl",
    "server/models/modelscope_cache/tiansz/bert-base-chinese/.msc",
    "server/models/Qwen2.5-0.5B-Instruct/.mdl",
    "server/models/Qwen2.5-0.5B-Instruct/.msc",
    "server/models/Qwen3.5-2B/.mdl",
    "server/models/Qwen3.5-2B/.msc",
]

COMMON_CHINESE_WORDS = {
    "检测脚本": "检测脚本",
    "检测": "检测",
    "检查": "检查",
    "功能": "功能",
    "测试": "测试",
    "模块": "模块",
    "环境": "环境",
    "依赖": "依赖",
    "目录": "目录",
    "结构": "结构",
    "前端": "前端",
    "结果": "结果",
    "汇总": "汇总",
    "完成": "完成",
    "不存在": "不存在",
    "服务商": "服务商",
    "模型": "模型",
    "列表": "列表",
    "获取": "获取",
    "个": "个",
    "验证": "验证",
    "错误": "错误",
    "处理": "处理",
    "请求": "请求",
    "状态码": "状态码",
    "配置": "配置",
    "成功": "成功",
    "下载": "下载",
    "支持": "支持",
    "镜像源": "镜像源",
    "会话": "会话",
    "管理": "管理",
    "数据": "数据",
    "状态": "状态",
    "自定义": "自定义",
    "消息": "消息",
    "角色": "角色",
    "内容": "内容",
    "搜索": "搜索",
    "关键词": "关键词",
    "过滤": "过滤",
    "日期": "日期",
    "偏移": "偏移",
    "详情": "详情",
    "更新": "更新",
    "删除": "删除",
    "恢复": "恢复",
    "归档": "归档",
    "添加": "添加",
    "导出": "导出",
    "标签": "标签",
    "统计": "统计",
    "信息": "信息",
    "记忆": "记忆",
    "系统": "系统",
    "知识": "知识",
    "图谱": "图谱",
    "实体": "实体",
    "关系": "关系",
    "短期": "短期",
    "上下文": "上下文",
    "长度": "长度",
    "字符": "字符",
    "活跃": "活跃",
    "摘要": "摘要",
    "条": "条",
    "智能": "智能",
    "提取器": "提取器",
    "提取": "提取",
    "机器学习": "机器学习",
    "合并": "合并",
    "器": "器",
    "属性": "属性",
    "服务": "服务",
    "处理器": "处理器",
    "技能": "技能",
    "发现": "发现",
    "注册": "注册",
    "扫描器": "扫描器",
    "文件": "文件",
    "注册表": "注册表",
    "元数据": "元数据",
    "执行": "执行",
    "状态": "状态",
    "依赖": "依赖",
    "搜索": "搜索",
    "类别": "类别",
    "报告": "报告",
    "健康": "健康",
    "根端点": "根端点",
    "推理": "推理",
    "参数": "参数",
    "空请求": "空请求",
    "聊天": "聊天",
    "格式": "格式",
    "网络": "网络",
    "连接": "连接",
    "训练": "训练",
    "进度": "进度",
    "空闲": "空闲",
    "历史": "历史",
    "开始": "开始",
    "缺失": "缺失",
    "无效": "无效",
    "停止": "停止",
    "应该": "应该",
    "返回": "返回",
    "任务": "任务",
    "追踪": "追踪",
    "端点": "端点",
    "接口": "接口",
    "创建": "创建",
    "创建者": "创建者",
    "标题": "标题",
    "描述": "描述",
    "所属": "所属",
    "项目": "项目",
    "优先级": "优先级",
    "截止": "截止",
    "负责人": "负责人",
    "子任务": "子任务",
    "筛选": "筛选",
    "逾期": "逾期",
    "数量": "数量",
    "详情": "详情",
    "指定": "指定",
    "详细": "详细",
    "更新": "更新",
    "百分比": "百分比",
    "硬删除": "硬删除",
    "物理": "物理",
    "软删除": "软删除",
    "标记": "标记",
    "已取消": "已取消",
    "分配": "分配",
    "进行中": "进行中",
    "已完成": "已完成",
    "已取消": "已取消",
    "通知": "通知",
    "接收者": "接收者",
    "未读": "未读",
    "默认": "默认",
    "最大": "最大",
    "已读": "已读",
    "所有": "所有",
    "实时": "实时",
    "流": "流",
    "连接": "连接",
    "心跳": "心跳",
}

def fix_truncated_chinese(content: str) -> str:
    patterns = [
        (r'检测脚�?', '检测脚本'),
        (r'全面检测�?', '全面检测'),
        (r'功能检�?', '功能检查'),
        (r'环境检�?', '环境检查'),
        (r'依赖检�?', '依赖检查'),
        (r'模块检�?', '模块检查'),
        (r'目录检�?', '目录检查'),
        (r'前端检�?', '前端检查'),
        (r'检测结果�?', '检测结果'),
        (r'检测完�?', '检测完成'),
        (r'核心依赖检�?', '核心依赖检查'),
        (r'API 模块检�?', 'API 模块检查'),
        (r'项目上下文模块检�?', '项目上下文模块检查'),
        (r'RAG 模块检�?', 'RAG 模块检查'),
        (r'Agent 模块检�?', 'Agent 模块检查'),
        (r'Core 模块检�?', 'Core 模块检查'),
        (r'目录结构检�?', '目录结构检查'),
        (r'关键文件检�?', '关键文件检查'),
        (r'测试结果�?', '测试结果'),
        (r'测试完�?', '测试完成'),
        (r'项目上下文模块测�?', '项目上下文模块测试'),
        (r'服务商列�?', '服务商列表'),
        (r'云端AI服务商列�?', '云端AI服务商列表'),
        (r'获取到�?', '获取到'),
        (r'个模�?', '个模型'),
        (r'汇总�?', '汇总'),
        (r'功能特�?', '功能特性'),
        (r'非流式聊�?', '非流式聊天'),
        (r'连接池复�?', '连接池复用'),
        (r'智能超时设�?', '智能超时设置'),
        (r'错误处理和重试机�?', '错误处理和重试机制'),
        (r'现在可以正常下载�?', '现在可以正常下载'),
        (r'HuggingFace 模型了�?', 'HuggingFace 模型了'),
        (r'支持的镜像源�?', '支持的镜像源：'),
        (r'功能：�?', '功能：'),
        (r'自定义数�?', '自定义数据'),
        (r'会话状�?', '会话状态'),
        (r'重要性评�?', '重要性评分'),
        (r'元数�?', '元数据'),
        (r'搜索关键�?', '搜索关键词'),
        (r'状态过�?', '状态过滤'),
        (r'开始日�?', '开始日期'),
        (r'偏移�?', '偏移量'),
        (r'创建新会�?', '创建新会话'),
        (r'会话不存�?', '会话不存在'),
        (r'更新会话元数�?', '更新会话元数据'),
        (r'软�?删除会话', '软删除会话'),
        (r'会话已删�?', '会话已删除'),
        (r'添加消息到会�?', '添加消息到会话'),
        (r'无效的消息角�?', '无效的消息角色'),
        (r'消息已添�?', '消息已添加'),
        (r'消息已删�?', '消息已删除'),
        (r'获取所有标�?', '获取所有标签'),
        (r'测试增强版记忆系�?', '测试增强版记忆系统'),
        (r'今�?5�?', '今年25岁'),
        (r'上下文长�?', '上下文长度'),
        (r'条消�?', '条消息'),
        (r'智能提取�?', '智能提取器'),
        (r'机器学�?', '机器学习'),
        (r'记忆合并�?', '记忆合并器'),
        (r'合并属�?', '合并属性'),
        (r'增强版记忆服�?', '增强版记忆服务'),
        (r'MCP 服务�?', 'MCP 服务器'),
        (r'测试扫描�?', '测试扫描器'),
        (r'发现技�?', '发现技能'),
        (r'测试注册�?', '测试注册表'),
        (r'已注册技�?', '已注册技能'),
        (r'元数�?', '元数据'),
        (r'测试技能执�?', '测试技能执行'),
        (r'执行状�?', '执行状态'),
        (r'状态报�?', '状态报告'),
        (r'依赖 text_transform 的技�?', '依赖 text_transform 的技能'),
        (r'测试技能搜�?', '测试技能搜索'),
        (r'按类别搜�?', '按类别搜索'),
        (r'按标签搜�?', '按标签搜索'),
        (r'关键词搜�?', '关键词搜索'),
        (r'所有测试完�?', '所有测试完成'),
        (r'测试健康检�?', '测试健康检查'),
        (r'测试根端�?', '测试根端点'),
        (r'测试空请�?', '测试空请求'),
        (r'网络连�?', '网络连接'),
        (r'测试获取训练状�?', '测试获取训练状态'),
        (r'测试开始训练参数验�?', '测试开始训练参数验证'),
        (r'空闲时应该返回错�?', '空闲时应该返回错误'),
        (r'任务追踪 API 端点', '任务追踪 API 端点'),
        (r'任务的 CRUD、分配、通知和进度追踪接�?', '任务的 CRUD、分配、通知和进度追踪接口'),
        (r'创建�?', '创建者'),
        (r'创建新任�?', '创建新任务'),
        (r'项目ID筛�?', '项目ID筛选'),
        (r'状态筛�?', '状态筛选'),
        (r'优先级筛�?', '优先级筛选'),
        (r'负责人筛�?', '负责人筛选'),
        (r'标签筛选（逗号分隔�?', '标签筛选（逗号分隔）'),
        (r'搜索关键�?', '搜索关键词'),
        (r'按项目、状态、优先级、负责人筛�?', '按项目、状态、优先级、负责人筛选'),
        (r'按标签筛选（多个标签用逗号分隔�?', '按标签筛选（多个标签用逗号分隔）'),
        (r'搜索标题或描�?', '搜索标题或描述'),
        (r'返回：�?', '返回：'),
        (r'各状态任务数�?', '各状态任务数量'),
        (r'逾期任务�?', '逾期任务数'),
        (r'高优先级任务�?', '高优先级任务数'),
        (r'完成�?', '完成率'),
        (r'获取指定任务的详细信�?', '获取指定任务的详细信息'),
        (r'标题、描�?', '标题、描述'),
        (r'进度百分�?', '进度百分比'),
        (r'是否硬删除（物理删除�?', '是否硬删除（物理删除）'),
        (r'软删除（标记为已取消�?', '软删除（标记为已取消）'),
        (r'硬删除（物理删除�?', '硬删除（物理删除）'),
        (r'任务已删�?', '任务已删除'),
        (r'将任务分配给指定负责�?', '将任务分配给指定负责人'),
        (r'进度百分�?', '进度百分比'),
        (r'进度消息（可选，会发送通知�?', '进度消息（可选，会发送通知）'),
        (r'当进度达到100%时，自动将任务标记为完�?', '当进度达到100%时，自动将任务标记为完成'),
        (r'更新子任务完成状�?', '更新子任务完成状态'),
        (r'会自动计算并更新父任务的进度百分�?', '会自动计算并更新父任务的进度百分比'),
        (r'开始任�?', '开始任务'),
        (r'将任务状态改为"进行�?', '将任务状态改为"进行中"'),
        (r'将任务状态改为"已完�?', '将任务状态改为"已完成"'),
        (r'将任务状态改为"已取�?', '将任务状态改为"已取消"'),
        (r'接收者筛�?', '接收者筛选'),
        (r'按接收者筛�?', '按接收者筛选'),
        (r'返回数量限制（默认50，最大200�?', '返回数量限制（默认50，最大200）'),
        (r'标记通知为已�?', '标记通知为已读'),
        (r'标记指定通知为已�?', '标记指定通知为已读'),
        (r'标记所有通知为已�?', '标记所有通知为已读'),
        (r'接收�?', '接收者'),
        (r'已标记�?', '已标记'),
        (r'条通知为已�?', '条通知为已读'),
        (r'实时通知�?', '实时通知流'),
        (r'实时通知流（Server-Sent Events�?', '实时通知流（Server-Sent Events）'),
        (r'不存�?', '不存在'),
        (r'大部分功能正常，有少量错误需要修�?', '大部分功能正常，有少量错误需要修复'),
        (r'存在多个错误，需要检查修�?', '存在多个错误，需要检查修复'),
    ]
    
    fixed_content = content
    for pattern, replacement in patterns:
        fixed_content = re.sub(pattern, replacement, fixed_content)
    
    return fixed_content

def fix_file_encoding(file_path: Path) -> Dict:
    result = {
        'file': str(file_path.relative_to(PROJECT_ROOT)),
        'success': False,
        'original_encoding': None,
        'fixed': False,
        'error': None
    }
    
    try:
        with open(file_path, 'rb') as f:
            raw_data = f.read()
        
        detected = chardet.detect(raw_data)
        result['original_encoding'] = detected.get('encoding', 'unknown')
        
        encodings_to_try = ['utf-8', 'gbk', 'gb2312', 'gb18030', 'latin1']
        
        content = None
        used_encoding = None
        
        for encoding in encodings_to_try:
            try:
                content = raw_data.decode(encoding)
                used_encoding = encoding
                break
            except (UnicodeDecodeError, LookupError):
                continue
        
        if content is None:
            content = raw_data.decode('utf-8', errors='replace')
            used_encoding = 'utf-8 (with replacements)'
        
        fixed_content = fix_truncated_chinese(content)
        
        if fixed_content != content:
            with open(file_path, 'w', encoding='utf-8', newline='\n') as f:
                f.write(fixed_content)
            result['fixed'] = True
            result['success'] = True
            print(f"[已修复] {result['file']}")
        else:
            result['success'] = True
            result['fixed'] = False
            print(f"[无需修复] {result['file']}")
            
    except Exception as e:
        result['error'] = str(e)
        print(f"[错误] {result['file']}: {e}")
    
    return result

def main():
    print("=" * 60)
    print("编码问题修复工具")
    print("=" * 60)
    print(f"\n待修复文件数: {len(FILES_TO_FIX)}")
    print("-" * 60)
    
    results = []
    fixed_count = 0
    error_count = 0
    
    for file_rel in FILES_TO_FIX:
        file_path = PROJECT_ROOT / file_rel
        if file_path.exists():
            result = fix_file_encoding(file_path)
            results.append(result)
            if result['fixed']:
                fixed_count += 1
            if result['error']:
                error_count += 1
        else:
            print(f"[不存在] {file_rel}")
            results.append({
                'file': file_rel,
                'success': False,
                'error': '文件不存在'
            })
    
    print("\n" + "=" * 60)
    print("修复结果汇总")
    print("=" * 60)
    print(f"处理文件数: {len(FILES_TO_FIX)}")
    print(f"成功修复: {fixed_count}")
    print(f"无需修复: {len(FILES_TO_FIX) - fixed_count - error_count}")
    print(f"错误数: {error_count}")
    
    results_path = PROJECT_ROOT / "encoding_fix_results.json"
    with open(results_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n修复结果已保存到: {results_path}")

if __name__ == "__main__":
    main()
