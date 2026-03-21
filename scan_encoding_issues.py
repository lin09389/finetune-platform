#!/usr/bin/env python3
"""
编码问题扫描和修复工具
扫描项目中所有文本文件，检测编码损坏问题并尝试修复
"""

import os
import chardet
import codecs
import json
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import re

PROJECT_ROOT = Path(r"c:\Users\JHJ\Desktop\finetune-platform")

TEXT_EXTENSIONS = {
    '.py', '.ts', '.tsx', '.js', '.jsx', '.json', '.yaml', '.yml',
    '.md', '.txt', '.html', '.css', '.scss', '.xml', '.sh', '.bat',
    '.env', '.example', '.toml', '.ini', '.cfg', '.conf'
}

SKIP_DIRS = {
    'node_modules', '__pycache__', '.git', 'dist', 'build', '.venv',
    'venv', 'env', '.idea', '.vscode', 'chroma.sqlite3', 'data'
}

class EncodingScanner:
    def __init__(self, root_path: Path):
        self.root_path = root_path
        self.issues: List[Dict] = []
        self.scanned_files = 0
        self.problematic_files = 0
        
    def should_scan_file(self, file_path: Path) -> bool:
        for skip_dir in SKIP_DIRS:
            if skip_dir in file_path.parts:
                return False
        
        ext = file_path.suffix.lower()
        if ext in TEXT_EXTENSIONS:
            return True
        
        if file_path.name.startswith('.'):
            return True
            
        return False
    
    def detect_encoding(self, file_path: Path) -> Tuple[Optional[str], float, bytes]:
        try:
            with open(file_path, 'rb') as f:
                raw_data = f.read()
            
            if not raw_data:
                return 'utf-8', 1.0, raw_data
            
            result = chardet.detect(raw_data)
            encoding = result.get('encoding', 'utf-8')
            confidence = result.get('confidence', 0)
            
            if encoding:
                encoding = encoding.lower()
                if encoding in ('ascii', 'iso-8859-1'):
                    encoding = 'utf-8'
            
            return encoding, confidence, raw_data
        except Exception as e:
            return None, 0, b''
    
    def check_bom(self, raw_data: bytes) -> Optional[str]:
        if raw_data.startswith(codecs.BOM_UTF8):
            return 'utf-8-sig'
        elif raw_data.startswith(codecs.BOM_UTF16_LE):
            return 'utf-16-le'
        elif raw_data.startswith(codecs.BOM_UTF16_BE):
            return 'utf-16-be'
        elif raw_data.startswith(codecs.BOM_UTF32_LE):
            return 'utf-32-le'
        elif raw_data.startswith(codecs.BOM_UTF32_BE):
            return 'utf-32-be'
        return None
    
    def has_garbled_chars(self, content: str) -> bool:
        garbled_patterns = [
            r'[\x00-\x08\x0b\x0c\x0e-\x1f]',
            r'锟斤拷',
            r'烫烫',
            r'屯屯',
            r'锘',
            r'\ufffd',
        ]
        
        for pattern in garbled_patterns:
            if re.search(pattern, content):
                return True
        
        chinese_pattern = r'[\u4e00-\u9fff]'
        has_chinese = bool(re.search(chinese_pattern, content))
        
        if has_chinese:
            weird_chars = re.findall(r'[^\x00-\x7F\u4e00-\u9fff\u3000-\u303f\uff00-\uffef\s\w\.,;:!?\'"()\[\]{}@#$%^&*+=<>/\\|`~-]', content)
            if len(weird_chars) > 5:
                return True
        
        return False
    
    def try_decode_with_encodings(self, raw_data: bytes) -> Tuple[str, str]:
        encodings_to_try = [
            'utf-8',
            'utf-8-sig',
            'gbk',
            'gb2312',
            'gb18030',
            'big5',
            'cp1252',
            'latin1',
            'utf-16',
            'utf-16-le',
            'utf-16-be',
        ]
        
        best_encoding = None
        best_content = None
        
        for encoding in encodings_to_try:
            try:
                content = raw_data.decode(encoding)
                if not self.has_garbled_chars(content):
                    return encoding, content
                if best_content is None:
                    best_encoding = encoding
                    best_content = content
            except (UnicodeDecodeError, LookupError):
                continue
        
        if best_content:
            return best_encoding, best_content
        
        return 'utf-8', raw_data.decode('utf-8', errors='replace')
    
    def scan_file(self, file_path: Path) -> Optional[Dict]:
        self.scanned_files += 1
        
        detected_encoding, confidence, raw_data = self.detect_encoding(file_path)
        
        if detected_encoding is None:
            return {
                'file': str(file_path.relative_to(self.root_path)),
                'issue': '无法检测编码',
                'detected_encoding': None,
                'confidence': 0,
                'can_fix': False
            }
        
        bom_encoding = self.check_bom(raw_data)
        
        try:
            if bom_encoding:
                content = raw_data.decode(bom_encoding)
                actual_encoding = bom_encoding
            else:
                actual_encoding, content = self.try_decode_with_encodings(raw_data)
            
            has_issues = self.has_garbled_chars(content)
            
            if has_issues or (confidence < 0.7 and detected_encoding != 'utf-8'):
                self.problematic_files += 1
                return {
                    'file': str(file_path.relative_to(self.root_path)),
                    'issue': '编码损坏或乱码' if has_issues else '编码检测置信度低',
                    'detected_encoding': detected_encoding,
                    'actual_encoding': actual_encoding,
                    'confidence': confidence,
                    'has_bom': bom_encoding is not None,
                    'can_fix': True,
                    'content_length': len(content)
                }
                
        except Exception as e:
            self.problematic_files += 1
            return {
                'file': str(file_path.relative_to(self.root_path)),
                'issue': f'解码错误: {str(e)}',
                'detected_encoding': detected_encoding,
                'confidence': confidence,
                'can_fix': False
            }
        
        return None
    
    def scan_directory(self) -> List[Dict]:
        print(f"开始扫描目录: {self.root_path}")
        print("-" * 60)
        
        for root, dirs, files in os.walk(self.root_path):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            
            for file in files:
                file_path = Path(root) / file
                
                if self.should_scan_file(file_path):
                    issue = self.scan_file(file_path)
                    if issue:
                        self.issues.append(issue)
                        print(f"[问题] {issue['file']}")
                        print(f"       问题: {issue['issue']}")
                        print(f"       检测编码: {issue['detected_encoding']} (置信度: {issue['confidence']:.2%})")
                        if 'actual_encoding' in issue:
                            print(f"       实际编码: {issue['actual_encoding']}")
                        print()
        
        return self.issues
    
    def generate_report(self) -> str:
        report = []
        report.append("=" * 60)
        report.append("编码问题扫描报告")
        report.append("=" * 60)
        report.append(f"扫描目录: {self.root_path}")
        report.append(f"扫描文件数: {self.scanned_files}")
        report.append(f"问题文件数: {self.problematic_files}")
        report.append("")
        
        if self.issues:
            report.append("-" * 60)
            report.append("问题文件列表:")
            report.append("-" * 60)
            
            for i, issue in enumerate(self.issues, 1):
                report.append(f"\n{i}. {issue['file']}")
                report.append(f"   问题类型: {issue['issue']}")
                report.append(f"   检测编码: {issue['detected_encoding']}")
                report.append(f"   置信度: {issue['confidence']:.2%}")
                if 'actual_encoding' in issue:
                    report.append(f"   实际编码: {issue['actual_encoding']}")
                if 'has_bom' in issue:
                    report.append(f"   包含BOM: {'是' if issue['has_bom'] else '否'}")
                report.append(f"   可修复: {'是' if issue['can_fix'] else '否'}")
        else:
            report.append("\n未发现编码问题!")
        
        return "\n".join(report)


def main():
    scanner = EncodingScanner(PROJECT_ROOT)
    issues = scanner.scan_directory()
    
    report = scanner.generate_report()
    print(report)
    
    report_path = PROJECT_ROOT / "encoding_scan_report.txt"
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f"\n报告已保存到: {report_path}")
    
    issues_json_path = PROJECT_ROOT / "encoding_issues.json"
    with open(issues_json_path, 'w', encoding='utf-8') as f:
        json.dump(issues, f, ensure_ascii=False, indent=2)
    print(f"问题详情已保存到: {issues_json_path}")


if __name__ == "__main__":
    main()
