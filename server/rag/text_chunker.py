"""
RAG 知识�?- 文本分块�?智能文本分块，支持多种分块策�?"""
from typing import List, Optional
from dataclasses import dataclass
import logging
import re

logger = logging.getLogger(__name__)


@dataclass
class TextChunk:
    """文本�?""
    content: str
    start_index: int
    end_index: int
    metadata: dict


class TextChunker:
    """文本分块�?""
    
    def __init__(
        self,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        min_chunk_size: int = 50
    ):
        """
        初始化分块器
        
        Args:
            chunk_size: 每块最大字符数
            chunk_overlap: 块间重叠字符�?            min_chunk_size: 最小块大小（小于该值的块会被合并）
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_size = min_chunk_size
    
    def chunk(self, text: str, metadata: Optional[dict] = None) -> List[TextChunk]:
        """
        智能分块（优先在句子/段落边界切分�?        
        Args:
            text: 待分块的文本
            metadata: 元数�?            
        Returns:
            文本块列�?        """
        if not text or not text.strip():
            return []
        
        # 1. 尝试按段落分�?        paragraphs = self._split_by_paragraph(text)
        
        # 2. 如果段落太大，进一步按句子分块
        chunks = []
        for para in paragraphs:
            if len(para) > self.chunk_size:
                # 按句子分�?                sentences = self._split_by_sentence(para)
                chunks.extend(self._merge_sentences(sentences, metadata))
            else:
                chunks.append(TextChunk(
                    content=para.strip(),
                    start_index=text.find(para),
                    end_index=text.find(para) + len(para),
                    metadata=metadata or {}
                ))
        
        # 3. 合并过小的块
        chunks = self._merge_small_chunks(chunks)
        
        # 4. 确保每块不超�?chunk_size
        final_chunks = []
        for chunk in chunks:
            if len(chunk.content) > self.chunk_size:
                # 强制按字符数分块
                sub_chunks = self._split_by_chars(chunk.content)
                for i, sub in enumerate(sub_chunks):
                    final_chunks.append(TextChunk(
                        content=sub,
                        start_index=chunk.start_index + i * self.chunk_size,
                        end_index=chunk.start_index + i * self.chunk_size + len(sub),
                        metadata=chunk.metadata
                    ))
            else:
                final_chunks.append(chunk)
        
        logger.info(f"文本分块完成：{len(text)} 字符 -> {len(final_chunks)} �?)
        return final_chunks
    
    def _split_by_paragraph(self, text: str) -> List[str]:
        """按段落分�?""
        # 匹配多个换行�?        paragraphs = re.split(r'\n\s*\n', text)
        return [p.strip() for p in paragraphs if p.strip()]
    
    def _split_by_sentence(self, text: str) -> List[str]:
        """按句子分�?""
        # 中文句子分割（。！�?!?�?        sentences = re.split(r'([。！�?!?！])', text)
        
        result = []
        current = ""
        for s in sentences:
            if not s:
                continue
            current += s
            if s in '。！�?!?�?:
                if current.strip():
                    result.append(current.strip())
                current = ""
        
        if current.strip():
            result.append(current.strip())
        
        return result
    
    def _merge_sentences(
        self,
        sentences: List[str],
        metadata: Optional[dict] = None
    ) -> List[TextChunk]:
        """合并句子为块（确保不超过 chunk_size�?""
        chunks = []
        current_sentences = []
        current_length = 0
        start_index = 0
        
        for i, sentence in enumerate(sentences):
            sentence_len = len(sentence)
            
            if current_length + sentence_len > self.chunk_size:
                # 当前块已满，创建新块
                if current_sentences:
                    content = ' '.join(current_sentences)
                    chunks.append(TextChunk(
                        content=content,
                        start_index=start_index,
                        end_index=start_index + len(content),
                        metadata=metadata or {}
                    ))
                
                # 如果单个句子就超�?chunk_size，强制分�?                if sentence_len > self.chunk_size:
                    sub_chunks = self._split_by_chars(sentence)
                    for sub in sub_chunks:
                        chunks.append(TextChunk(
                            content=sub,
                            start_index=start_index,
                            end_index=start_index + len(sub),
                            metadata=metadata or {}
                        ))
                        start_index += len(sub)
                    current_sentences = []
                    current_length = 0
                else:
                    # 开始新�?                    current_sentences = [sentence]
                    current_length = sentence_len
                    start_index = sum(len(s) for s in sentences[:i])
            else:
                # 添加到当前块
                current_sentences.append(sentence)
                current_length += sentence_len
        
        # 处理剩余的块
        if current_sentences:
            content = ' '.join(current_sentences)
            chunks.append(TextChunk(
                content=content,
                start_index=start_index,
                end_index=start_index + len(content),
                metadata=metadata or {}
            ))
        
        return chunks
    
    def _split_by_chars(self, text: str) -> List[str]:
        """强制按字符数分割"""
        chunks = []
        start = 0
        
        while start < len(text):
            end = start + self.chunk_size
            chunk = text[start:end]
            
            # 尝试在句子边界处切分
            if end < len(text):
                last_period = chunk.rfind('.')
                last_cn_period = chunk.rfind('�?)
                last_newline = chunk.rfind('\n')
                
                split_point = max(last_period, last_cn_period, last_newline)
                if split_point > self.chunk_size * 0.5:
                    end = start + split_point + 1
                    chunk = text[start:end]
            
            if chunk.strip():
                chunks.append(chunk.strip())
            
            start = end - self.chunk_overlap
            if start >= len(text):
                break
        
        return chunks
    
    def _merge_small_chunks(self, chunks: List[TextChunk]) -> List[TextChunk]:
        """合并过小的块"""
        if len(chunks) <= 1:
            return chunks
        
        merged = []
        current = chunks[0]
        
        for chunk in chunks[1:]:
            if len(current.content) + len(chunk.content) < self.chunk_size:
                # 合并
                current = TextChunk(
                    content=current.content + '\n' + chunk.content,
                    start_index=current.start_index,
                    end_index=chunk.end_index,
                    metadata=current.metadata
                )
            else:
                merged.append(current)
                current = chunk
        
        merged.append(current)
        return merged


# 单例实例
_chunker_instance: Optional[TextChunker] = None


def get_chunker(
    chunk_size: int = 500,
    chunk_overlap: int = 50
) -> TextChunker:
    """获取分块器实�?""
    global _chunker_instance
    if _chunker_instance is None:
        _chunker_instance = TextChunker(chunk_size, chunk_overlap)
    return _chunker_instance
