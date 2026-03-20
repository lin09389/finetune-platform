"""
RAG 知识�?- 文档解析�?支持 PDF、DOCX、TXT、MD 等格�?"""
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class DocumentParser:
    """文档解析�?""
    
    def __init__(self):
        pass
    
    def parse(self, file_path: str) -> Optional[str]:
        """
        解析文档内容
        
        Args:
            file_path: 文件路径
            
        Returns:
            解析后的文本内容
        """
        path = Path(file_path)
        if not path.exists():
            logger.error(f"文件不存在：{file_path}")
            return None
        
        ext = path.suffix.lower()
        
        try:
            if ext == '.pdf':
                return self._parse_pdf(file_path)
            elif ext in ['.docx', '.doc']:
                return self._parse_docx(file_path)
            elif ext in ['.txt', '.md', '.markdown']:
                return self._parse_text(file_path)
            else:
                logger.warning(f"不支持的文件格式：{ext}，尝试按文本解析")
                return self._parse_text(file_path)
        except Exception as e:
            logger.error(f"解析文件失败 {file_path}: {e}")
            return None
    
    def _parse_pdf(self, file_path: str) -> str:
        """解析 PDF 文件"""
        try:
            import PyPDF2
            
            text_parts = []
            with open(file_path, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                for i, page in enumerate(reader.pages):
                    text = page.extract_text()
                    if text:
                        text_parts.append(f"--- �?{i+1} �?---\n{text}")
            
            return '\n\n'.join(text_parts)
        except Exception as e:
            raise Exception(f"PDF 解析失败：{e}")
    
    def _parse_docx(self, file_path: str) -> str:
        """解析 DOCX 文件"""
        try:
            import docx
            
            doc = docx.Document(file_path)
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            return '\n\n'.join(paragraphs)
        except Exception as e:
            raise Exception(f"DOCX 解析失败：{e}")
    
    def _parse_text(self, file_path: str) -> str:
        """解析文本文件"""
        encodings = ['utf-8', 'gbk', 'gb2312', 'latin-1']
        
        for encoding in encodings:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    return f.read()
            except UnicodeDecodeError:
                continue
        
        raise Exception(f"无法解析文件编码，尝试的编码：{encodings}")
    
    def get_supported_formats(self) -> list[str]:
        """获取支持的文件格�?""
        return ['.pdf', '.docx', '.doc', '.txt', '.md', '.markdown']


# 单例实例
_parser_instance: Optional[DocumentParser] = None


def get_parser() -> DocumentParser:
    """获取解析器实�?""
    global _parser_instance
    if _parser_instance is None:
        _parser_instance = DocumentParser()
    return _parser_instance
