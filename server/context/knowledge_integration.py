"""
知识库集成模块
实现对话中自动知识检索、检索结果注入上下文、知识来源引用格式化
"""
import json
import logging
from dataclasses import dataclass, field
from typing import Any

from rag.hybrid_retriever import HybridRetriever, get_hybrid_retriever
from rag.reranker import CrossEncoderReranker, get_reranker
from rag.service import RAGService, get_rag_service

logger = logging.getLogger(__name__)


@dataclass
class KnowledgeSource:
    """知识来源"""
    id: str
    content: str
    source: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "source": self.source,
            "score": self.score,
            "metadata": self.metadata
        }


@dataclass
class KnowledgeRetrievalResult:
    """知识检索结果"""
    query: str
    sources: list[KnowledgeSource]
    context: str
    retrieval_method: str
    total_results: int
    retrieval_time: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "sources": [s.to_dict() for s in self.sources],
            "context": self.context,
            "retrieval_method": self.retrieval_method,
            "total_results": self.total_results,
            "retrieval_time": self.retrieval_time
        }


class KnowledgeIntegrator:
    """知识库集成器"""

    KNOWLEDGE_KEYWORDS = [
        "知识库", "文档", "资料", "文件", "内容",
        "查找", "搜索", "检索", "查询", "寻找",
        "什么是", "怎么", "如何", "为什么", "哪个",
        "解释", "说明", "介绍", "描述", "定义",
        "帮我", "请帮我", "能否", "可以",
        "根据", "基于", "参考", "按照"
    ]

    EXCLUSION_KEYWORDS = [
        "写代码", "编程", "实现", "创建文件", "删除文件",
        "运行", "执行", "终端", "命令"
    ]

    DOMAIN_KEYWORDS = {
        "law": {
            "keywords": [
                "法律", "法规", "法典", "法条", "条款", "规定",
                "违法", "犯罪", "刑罚", "判决", "诉讼", "仲裁",
                "合同", "协议", "违约", "赔偿", "责任", "义务",
                "权利", "权益", "保护", "侵权", "纠纷", "争议",
                "律师", "法院", "检察院", "公安", "司法",
                "民事", "刑事", "行政", "宪法", "民法", "刑法",
                "婚姻", "继承", "劳动", "公司", "知识产权",
                "商标", "专利", "著作权", "版权",
                "罚款", "拘留", "逮捕", "起诉", "上诉",
                "民法典", "刑法典", "宪法", "劳动法", "公司法"
            ],
            "description": "法律领域"
        },
        "medical": {
            "keywords": [
                "医疗", "医学", "健康", "疾病", "症状", "治疗",
                "药物", "药品", "医院", "医生", "诊断", "检查",
                "手术", "康复", "预防", "保健", "养生",
                "发烧", "感冒", "咳嗽", "头痛", "腹痛",
                "高血压", "糖尿病", "心脏病", "癌症"
            ],
            "description": "医疗健康领域"
        },
        "finance": {
            "keywords": [
                "金融", "投资", "理财", "股票", "基金", "债券",
                "银行", "贷款", "利率", "汇率", "期货", "期权",
                "财务", "会计", "审计", "税务", "税收",
                "资产", "负债", "利润", "收入", "支出",
                "保险", "证券", "基金"
            ],
            "description": "金融财经领域"
        },
        "education": {
            "keywords": [
                "教育", "教学", "学校", "课程", "考试", "学习",
                "培训", "辅导", "教材", "教案", "作业",
                "高考", "考研", "公务员", "资格证",
                "大学", "中学", "小学", "幼儿园"
            ],
            "description": "教育领域"
        },
        "tech": {
            "keywords": [
                "技术", "编程", "开发", "软件", "硬件", "系统",
                "算法", "数据", "网络", "安全", "架构",
                "人工智能", "机器学习", "深度学习", "大数据",
                "云计算", "区块链", "物联网"
            ],
            "description": "技术领域"
        }
    }

    def __init__(
        self,
        default_top_k: int = 5,
        retrieval_top_k: int = 20,
        use_hybrid: bool = True,
        use_rerank: bool = True,
        vector_weight: float = 0.5,
        keyword_weight: float = 0.5,
        min_score_threshold: float = 0.3,
        max_context_length: int = 2000
    ):
        """
        初始化知识库集成器

        Args:
            default_top_k: 默认返回结果数量
            retrieval_top_k: 初始检索数量
            use_hybrid: 是否使用混合检索
            use_rerank: 是否使用重排序
            vector_weight: 向量检索权重
            keyword_weight: 关键词检索权重
            min_score_threshold: 最小分数阈值
            max_context_length: 最大上下文长度
        """
        self.default_top_k = default_top_k
        self.retrieval_top_k = retrieval_top_k
        self.use_hybrid = use_hybrid
        self.use_rerank = use_rerank
        self.vector_weight = vector_weight
        self.keyword_weight = keyword_weight
        self.min_score_threshold = min_score_threshold
        self.max_context_length = max_context_length

        self._rag_service: RAGService | None = None
        self._hybrid_retriever: HybridRetriever | None = None
        self._reranker: CrossEncoderReranker | None = None

    def _get_rag_service(self) -> RAGService:
        """获取 RAG 服务"""
        if self._rag_service is None:
            self._rag_service = get_rag_service()
        return self._rag_service

    def _get_hybrid_retriever(self) -> HybridRetriever:
        """获取混合检索器"""
        if self._hybrid_retriever is None:
            rag_service = self._get_rag_service()
            self._hybrid_retriever = get_hybrid_retriever(
                vector_store=rag_service.vector_store,
                embedder=rag_service.embedder
            )
        return self._hybrid_retriever

    def _get_reranker(self) -> CrossEncoderReranker:
        """获取重排序器"""
        if self._reranker is None:
            self._reranker = get_reranker()
        return self._reranker

    def should_retrieve_knowledge(
        self,
        query: str,
        collection_id: str | None = None,
        force_retrieve: bool = False
    ) -> tuple[bool, str]:
        """
        判断是否需要检索知识库

        Args:
            query: 用户查询
            collection_id: 知识库集合 ID
            force_retrieve: 强制检索

        Returns:
            (是否需要检索, 原因)
        """
        if force_retrieve:
            return True, "强制检索"

        if not collection_id:
            return False, "未指定知识库"

        query_lower = query.lower()

        for keyword in self.EXCLUSION_KEYWORDS:
            if keyword in query_lower:
                return False, f"排除关键词: {keyword}"

        domain_detected = self.detect_domain(query)
        if domain_detected:
            return True, f"检测到{domain_detected['description']}"

        for keyword in self.KNOWLEDGE_KEYWORDS:
            if keyword in query_lower:
                return True, f"匹配关键词: {keyword}"

        if len(query) > 15 and '?' in query:
            return True, "问题式查询"

        if len(query) > 20:
            return True, "长查询"

        return False, "未匹配检索条件"

    def detect_domain(self, query: str) -> dict[str, Any] | None:
        """
        检测查询所属领域

        Args:
            query: 用户查询

        Returns:
            检测到的领域信息，未检测到则返回 None
        """
        query_lower = query.lower()
        best_domain = None
        best_score = 0

        for domain_id, domain_info in self.DOMAIN_KEYWORDS.items():
            score = 0
            matched_keywords = []

            for keyword in domain_info["keywords"]:
                if keyword in query_lower:
                    score += 1
                    matched_keywords.append(keyword)

            if score > best_score:
                best_score = score
                best_domain = {
                    "id": domain_id,
                    "description": domain_info["description"],
                    "matched_keywords": matched_keywords,
                    "score": score
                }

        return best_domain

    def get_collection_for_domain(self, domain_id: str) -> str | None:
        """
        根据领域获取对应的知识库集合名称

        Args:
            domain_id: 领域 ID

        Returns:
            知识库集合名称
        """
        domain_mapping = {
            "law": "law",
            "medical": "medical",
            "finance": "finance",
            "education": "education",
            "tech": "tech"
        }
        return domain_mapping.get(domain_id)

    def retrieve_knowledge(
        self,
        query: str,
        collection_id: str,
        top_k: int | None = None,
        use_hybrid: bool | None = None,
        use_rerank: bool | None = None
    ) -> KnowledgeRetrievalResult:
        """
        检索知识库

        Args:
            query: 查询文本
            collection_id: 集合 ID
            top_k: 返回结果数量
            use_hybrid: 是否使用混合检索
            use_rerank: 是否使用重排序

        Returns:
            检索结果
        """
        import time
        start_time = time.time()

        top_k = top_k or self.default_top_k
        use_hybrid = use_hybrid if use_hybrid is not None else self.use_hybrid
        use_rerank = use_rerank if use_rerank is not None else self.use_rerank

        retrieval_method = "vector"
        results = []

        try:
            if use_hybrid:
                hybrid_retriever = self._get_hybrid_retriever()
                hybrid_retriever.set_weights(self.vector_weight, self.keyword_weight)

                initial_results = hybrid_retriever.search(
                    collection_name=collection_id,
                    query=query,
                    top_k=self.retrieval_top_k
                )
                retrieval_method = "hybrid"

                results = [
                    {
                        "id": r.id,
                        "content": r.content,
                        "score": r.score,
                        "metadata": r.metadata,
                        "source": r.source
                    }
                    for r in initial_results
                ]
            else:
                rag_service = self._get_rag_service()
                results = rag_service.search(
                    collection_name=collection_id,
                    query=query,
                    top_k=self.retrieval_top_k
                )

            if use_rerank and results:
                reranker = self._get_reranker()
                reranked_results = reranker.rerank(
                    query=query,
                    results=results,
                    top_k=top_k
                )
                retrieval_method += "_rerank"

                results = [
                    {
                        "id": r.id,
                        "content": r.content,
                        "score": r.score,
                        "metadata": r.metadata,
                        "original_score": r.original_score,
                        "original_rank": r.original_rank
                    }
                    for r in reranked_results
                ]
            else:
                results = results[:top_k]

            filtered_results = [
                r for r in results
                if r.get("score", 0) >= self.min_score_threshold
            ]

            sources = [
                KnowledgeSource(
                    id=r["id"],
                    content=r["content"],
                    source=r.get("source", r.get("metadata", {}).get("source", "未知来源")),
                    score=r["score"],
                    metadata=r.get("metadata", {})
                )
                for r in filtered_results
            ]

            context = self._build_context(sources)

            retrieval_time = time.time() - start_time

            logger.info(f"知识检索完成: query='{query[:50]}...', "
                       f"method={retrieval_method}, "
                       f"results={len(sources)}, "
                       f"time={retrieval_time:.3f}s")

            return KnowledgeRetrievalResult(
                query=query,
                sources=sources,
                context=context,
                retrieval_method=retrieval_method,
                total_results=len(sources),
                retrieval_time=retrieval_time
            )

        except Exception as e:
            logger.error(f"知识检索失败: {e}", exc_info=True)
            return KnowledgeRetrievalResult(
                query=query,
                sources=[],
                context="",
                retrieval_method="error",
                total_results=0,
                retrieval_time=time.time() - start_time
            )

    def _build_context(self, sources: list[KnowledgeSource]) -> str:
        """
        构建上下文文本

        Args:
            sources: 知识来源列表

        Returns:
            上下文文本
        """
        if not sources:
            return ""

        context_parts = []
        current_length = 0

        for i, source in enumerate(sources):
            part = f"[参考资料 {i+1}]\n来源: {source.source}\n内容: {source.content}\n"

            if current_length + len(part) > self.max_context_length:
                break

            context_parts.append(part)
            current_length += len(part)

        return "\n".join(context_parts)

    def inject_knowledge_to_messages(
        self,
        messages: list[dict[str, str]],
        retrieval_result: KnowledgeRetrievalResult,
        system_prompt_template: str | None = None
    ) -> list[dict[str, str]]:
        """
        将检索到的知识注入到对话消息中

        Args:
            messages: 原始消息列表
            retrieval_result: 检索结果
            system_prompt_template: 系统提示词模板

        Returns:
            注入知识后的消息列表
        """
        if not retrieval_result.sources:
            return messages

        if system_prompt_template is None:
            system_prompt_template = """你是一个有帮助的 AI 助手。请基于以下参考资料回答用户的问题。

参考资料：
{context}

请注意：
1. 优先使用参考资料中的信息回答
2. 如果参考资料中没有相关信息，请明确说明
3. 引用具体内容时，请标注来源编号（如 [参考资料 1]）
4. 保持回答简洁、准确、有帮助"""

        system_content = system_prompt_template.format(
            context=retrieval_result.context
        )

        injected_messages = []
        has_system = False

        for msg in messages:
            if msg.get("role") == "system":
                injected_messages.append({
                    "role": "system",
                    "content": f"{msg['content']}\n\n{system_content}"
                })
                has_system = True
            else:
                if not has_system:
                    injected_messages.insert(0, {
                        "role": "system",
                        "content": system_content
                    })
                    has_system = True
                injected_messages.append(msg)

        if not has_system:
            injected_messages.insert(0, {
                "role": "system",
                "content": system_content
            })

        return injected_messages

    def format_sources_citation(
        self,
        sources: list[KnowledgeSource],
        style: str = "markdown"
    ) -> str:
        """
        格式化知识来源引用

        Args:
            sources: 知识来源列表
            style: 格式风格 (markdown/json/text)

        Returns:
            格式化后的引用文本
        """
        if not sources:
            return ""

        if style == "json":
            return json.dumps([s.to_dict() for s in sources], ensure_ascii=False, indent=2)

        elif style == "markdown":
            lines = ["\n---\n**📚 知识来源引用:**\n"]
            for i, source in enumerate(sources):
                lines.append(f"\n[{i+1}] **{source.source}**")
                lines.append(f"    相关度: {source.score:.2%}")
                if source.metadata.get("doc_id"):
                    lines.append(f"    文档ID: {source.metadata['doc_id']}")
            return "\n".join(lines)

        else:
            lines = ["\n知识来源:"]
            for i, source in enumerate(sources):
                lines.append(f"  [{i+1}] {source.source} (相关度: {source.score:.2%})")
            return "\n".join(lines)

    def enhance_response_with_sources(
        self,
        response: str,
        sources: list[KnowledgeSource],
        include_citation: bool = True
    ) -> str:
        """
        在回复中添加知识来源引用

        Args:
            response: 原始回复
            sources: 知识来源列表
            include_citation: 是否包含引用

        Returns:
            增强后的回复
        """
        if not sources or not include_citation:
            return response

        citation = self.format_sources_citation(sources, style="markdown")

        return f"{response}\n{citation}"


class KnowledgeAwareChatManager:
    """知识感知的对话管理器"""

    def __init__(self, integrator: KnowledgeIntegrator | None = None):
        """
        初始化对话管理器

        Args:
            integrator: 知识集成器实例
        """
        self.integrator = integrator or KnowledgeIntegrator()
        self._session_knowledge: dict[str, list[KnowledgeRetrievalResult]] = {}

    def process_message(
        self,
        session_id: str,
        user_message: str,
        collection_id: str | None = None,
        auto_retrieve: bool = True,
        force_retrieve: bool = False
    ) -> tuple[KnowledgeRetrievalResult | None, dict[str, Any]]:
        """
        处理用户消息，自动检索知识

        Args:
            session_id: 会话 ID
            user_message: 用户消息
            collection_id: 知识库集合 ID
            auto_retrieve: 是否自动检索
            force_retrieve: 强制检索

        Returns:
            (检索结果, 处理信息)
        """
        process_info = {
            "session_id": session_id,
            "retrieved": False,
            "reason": "",
            "sources_count": 0
        }

        if not auto_retrieve or not collection_id:
            process_info["reason"] = "未启用自动检索或未指定知识库"
            return None, process_info

        should_retrieve, reason = self.integrator.should_retrieve_knowledge(
            query=user_message,
            collection_id=collection_id,
            force_retrieve=force_retrieve
        )

        if not should_retrieve:
            process_info["reason"] = reason
            return None, process_info

        retrieval_result = self.integrator.retrieve_knowledge(
            query=user_message,
            collection_id=collection_id
        )

        if session_id not in self._session_knowledge:
            self._session_knowledge[session_id] = []
        self._session_knowledge[session_id].append(retrieval_result)

        process_info["retrieved"] = True
        process_info["reason"] = reason
        process_info["sources_count"] = len(retrieval_result.sources)

        return retrieval_result, process_info

    def get_session_knowledge(
        self,
        session_id: str,
        limit: int = 5
    ) -> list[KnowledgeRetrievalResult]:
        """
        获取会话的知识检索历史

        Args:
            session_id: 会话 ID
            limit: 最大返回数量

        Returns:
            检索结果列表
        """
        results = self._session_knowledge.get(session_id, [])
        return results[-limit:] if results else []

    def clear_session_knowledge(self, session_id: str):
        """
        清除会话的知识检索历史

        Args:
            session_id: 会话 ID
        """
        if session_id in self._session_knowledge:
            del self._session_knowledge[session_id]

    def build_knowledge_enhanced_prompt(
        self,
        user_message: str,
        retrieval_result: KnowledgeRetrievalResult | None,
        conversation_history: list[dict[str, str]] | None = None
    ) -> str:
        """
        构建知识增强的提示词

        Args:
            user_message: 用户消息
            retrieval_result: 检索结果
            conversation_history: 对话历史

        Returns:
            增强后的提示词
        """
        prompt_parts = []

        if retrieval_result and retrieval_result.context:
            prompt_parts.append(f"参考资料:\n{retrieval_result.context}\n")

        if conversation_history:
            history_text = []
            for msg in conversation_history[-5:]:
                role = "用户" if msg.get("role") == "user" else "助手"
                history_text.append(f"{role}: {msg.get('content', '')}")
            if history_text:
                prompt_parts.append("对话历史:\n" + "\n".join(history_text) + "\n")

        prompt_parts.append(f"用户问题: {user_message}")
        prompt_parts.append("\n请基于参考资料回答用户问题，并在回答中标注引用来源。")

        return "\n".join(prompt_parts)


_integrator_instance: KnowledgeIntegrator | None = None
_manager_instance: KnowledgeAwareChatManager | None = None


def get_knowledge_integrator() -> KnowledgeIntegrator:
    """获取知识集成器实例"""
    global _integrator_instance
    if _integrator_instance is None:
        _integrator_instance = KnowledgeIntegrator()
    return _integrator_instance


def get_knowledge_chat_manager() -> KnowledgeAwareChatManager:
    """获取知识感知对话管理器实例"""
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = KnowledgeAwareChatManager()
    return _manager_instance
