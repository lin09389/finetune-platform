# -*- coding: utf-8 -*-
"""
记忆提取器 - 从用户消息中提取需要记忆的信息
"""
import re
from typing import List, Dict, Any, Optional
import logging

from .models import MemoryType, MEMORY_IMPORTANCE

logger = logging.getLogger(__name__)


class MemoryExtractor:
    """记忆提取器"""

    def __init__(self):
        self.patterns = {
            MemoryType.PERSONAL: [
                (r'我叫\s*(\S+)', '用户的名字是 {1}'),
                (r'我是\s*(\S+?)(?:，|。|！|,|$)', '用户的身份是 {1}'),
                (r'我在?\s*(.+?)工作', '用户在 {1} 工作'),
                (r'我住[在是]\s*(.+?)[，。]', '用户住在 {1}'),
                (r'我的(\S+)是\s*(\S+)', '用户的{1}是{2}'),
                (r'我(\d+)岁', '用户{1}岁'),
                (r'我是\s*(\S+?)学生', '用户是学生，{1}'),
                (r'我学\s*(\S+)', '用户学习{1}'),
            ],
            MemoryType.PREFERENCE: [
                (r'我喜欢用?\s*(\S+)', '用户喜欢用 {1}'),
                (r'我喜欢\s+(\S+)', '用户喜欢 {1}'),
                (r'我讨厌\s+(\S+)', '用户讨厌 {1}'),
                (r'我偏好\s+(\S+)', '用户偏好 {1}'),
                (r'我常用\s+(\S+)', '用户常用 {1}'),
                (r'我不用\s+(\S+)', '用户不用 {1}'),
                (r'我更(?:喜欢|倾向)\s*(\S+)', '用户更倾向 {1}'),
            ],
            MemoryType.PROJECT: [
                (r'我在做?\s*(.+?)项目', '用户在做 {1} 项目'),
                (r'我的项目用?\s*(\S+)', '用户的项目使用 {1}'),
                (r'我在开发?\s*(.+)', '用户在开发 {1}'),
                (r'我在研究?\s*(.+)', '用户在研究 {1}'),
                (r'我在写?\s*(.+?)代码', '用户在写 {1} 代码'),
            ],
            MemoryType.SKILL: [
                (r'我会\s+(\S+)', '用户会 {1}'),
                (r'我精通?\s+(\S+)', '用户精通 {1}'),
                (r'我熟悉?\s+(\S+)', '用户熟悉 {1}'),
                (r'我正在学?\s*(\S+)', '用户正在学习 {1}'),
                (r'我掌握?\s*(\S+)', '用户掌握 {1}'),
            ],
            MemoryType.HABIT: [
                (r'我习惯\s+(.+)', '用户习惯 {1}'),
                (r'我一般\s+(.+)', '用户一般 {1}'),
                (r'我通常?\s+(.+)', '用户通常 {1}'),
                (r'我总是?\s+(.+)', '用户总是 {1}'),
            ],
        }

        self.important_keywords = [
            '记住', '别忘了', '记得', 'important',
            '我的', '我家', '我公司', '我学校', '我团队',
            '注意', '提醒我'
        ]

    def extract(
        self,
        message: str,
        role: str = 'user'
    ) -> List[Dict[str, Any]]:
        """
        从消息中提取记忆

        Args:
            message: 消息内容
            role: 角色（user/assistant）
        Returns:
            提取的记忆列表
        """
        if role != 'user':
            return []

        memories = []

        rule_memories = self._rule_extraction(message)
        memories.extend(rule_memories)

        keyword_memories = self._keyword_extraction(message)
        memories.extend(keyword_memories)

        memories = self._deduplicate(memories)

        if memories:
            logger.info(f"从消息中提取了 {len(memories)} 条记忆")

        return memories

    def _rule_extraction(self, message: str) -> List[Dict[str, Any]]:
        """规则提取"""
        memories = []

        for mem_type, patterns in self.patterns.items():
            for pattern, template in patterns:
                try:
                    matches = re.finditer(pattern, message, re.IGNORECASE)
                    for match in matches:
                        content = template
                        for i, group in enumerate(match.groups(), 1):
                            content = content.replace(f'{{{i}}}', group or '')

                        content = content.strip()
                        if len(content) < 5:
                            continue

                        memories.append({
                            'content': content,
                            'type': mem_type.value,
                            'importance': MEMORY_IMPORTANCE.get(mem_type, 0.5),
                            'source': 'rule',
                            'raw_text': match.group(0)
                        })
                except Exception as e:
                    logger.warning(f"规则提取失败: {pattern}, {e}")

        return memories

    def _keyword_extraction(self, message: str) -> List[Dict[str, Any]]:
        """关键词提取"""
        memories = []

        has_important = any(kw in message.lower() for kw in self.important_keywords)

        if has_important:
            sentences = re.split(r'[.!。！？\n]', message)
            for sentence in sentences:
                sentence = sentence.strip()
                if not sentence or len(sentence) < 10 or len(sentence) > 100:
                    continue

                if any(kw in sentence for kw in self.important_keywords):
                    memories.append({
                        'content': sentence,
                        'type': MemoryType.KNOWLEDGE.value,
                        'importance': 0.6,
                        'source': 'keyword'
                    })

        return memories

    def _deduplicate(self, memories: List[Dict]) -> List[Dict]:
        """去重"""
        seen = set()
        unique = []
        for mem in memories:
            key = mem['content']
            if key not in seen:
                seen.add(key)
                unique.append(mem)
        return unique

    def extract_from_conversation(
        self,
        messages: List[Dict[str, str]]
    ) -> List[Dict[str, Any]]:
        """
        从对话历史中提取记忆

        Args:
            messages: 对话消息列表 [{"role": "user", "content": "..."}]

        Returns:
            提取的记忆列表
        """
        all_memories = []

        for msg in messages:
            if msg.get('role') == 'user':
                memories = self.extract(msg.get('content', ''), 'user')
                all_memories.extend(memories)

        return self._deduplicate(all_memories)
