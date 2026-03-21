# -*- coding: utf-8 -*-
"""
自动修复编码损坏的 Python 文件
"""
import os
import re
import ast
from pathlib import Path
from typing import List, Tuple, Optional

# 常见的编码损坏模式及其修复
ENCODING_FIXES = {
    # 截断的中文字符模式
    r'[\u4e00-\u9fff]\?': lambda m: m.group(0).replace('?', '）'),
    r'\?[\u4e00-\u9fff]': lambda m: m.group(0).replace('?', '（'),
    # 常见的截断修复
    r'已初始\?': '已初始化',
    r'已加载\?': '已加载',
    r'已创建\?': '已创建',
    r'已删除\?': '已删除',
    r'已更新\?': '已更新',
    r'已保存\?': '已保存',
    r'已清理\?': '已清理',
    r'已连接\?': '已连接',
    r'已完成\?': '已完成',
    r'已启动\?': '已启动',
    r'已停止\?': '已停止',
    r'已关闭\?': '已关闭',
    r'已过期\?': '已过期',
    r'已存在\?': '已存在',
    r'不存在\?': '不存在',
    r'失败\?': '失败',
    r'成功\?': '成功',
    r'错误\?': '错误',
    r'警告\?': '警告',
    r'信息\?': '信息',
    r'配置\?': '配置',
    r'文件\?': '文件',
    r'目录\?': '目录',
    r'模块\?': '模块',
    r'服务\?': '服务',
    r'请求\?': '请求',
    r'响应\?': '响应',
    r'数据\?': '数据',
    '功能：?': '功能：',
    '参数：?': '参数：',
    '返回：?': '返回：',
    '类型：?': '类型：',
    '状态：?': '状态：',
    '名称：?': '名称：',
    '描述：?': '描述：',
}

def try_read_file(filepath: str) -> Tuple[Optional[str], Optional[str]]:
    """尝试用不同编码读取文件"""
    encodings = ['utf-8', 'gbk', 'gb2312', 'gb18030', 'latin-1']
    
    for encoding in encodings:
        try:
            with open(filepath, 'r', encoding=encoding, errors='replace') as f:
                content = f.read()
            return content, encoding
        except Exception:
            continue
    
    return None, None

def fix_truncated_chinese(content: str) -> str:
    """修复截断的中文字符"""
    # 修复常见的截断模式
    lines = content.split('\n')
    fixed_lines = []
    
    for line in lines:
        fixed_line = line
        
        # 检查是否以 ? 结尾的不完整字符串
        if '"' in fixed_line and fixed_line.rstrip().endswith('?'):
            # 尝试修复
            if '已初始?' in fixed_line:
                fixed_line = fixed_line.replace('已初始?', '已初始化')
            elif '已加载?' in fixed_line:
                fixed_line = fixed_line.replace('已加载?', '已加载')
            elif '已创建?' in fixed_line:
                fixed_line = fixed_line.replace('已创建?', '已创建')
            elif '已删除?' in fixed_line:
                fixed_line = fixed_line.replace('已删除?', '已删除')
            elif '已更新?' in fixed_line:
                fixed_line = fixed_line.replace('已更新?', '已更新')
            elif '已保存?' in fixed_line:
                fixed_line = fixed_line.replace('已保存?', '已保存')
            elif '已清理?' in fixed_line:
                fixed_line = fixed_line.replace('已清理?', '已清理')
            elif '已连接?' in fixed_line:
                fixed_line = fixed_line.replace('已连接?', '已连接')
            elif '已完成?' in fixed_line:
                fixed_line = fixed_line.replace('已完成?', '已完成')
            elif '已启动?' in fixed_line:
                fixed_line = fixed_line.replace('已启动?', '已启动')
            elif '已停止?' in fixed_line:
                fixed_line = fixed_line.replace('已停止?', '已停止')
            elif '已关闭?' in fixed_line:
                fixed_line = fixed_line.replace('已关闭?', '已关闭')
            elif '已过期?' in fixed_line:
                fixed_line = fixed_line.replace('已过期?', '已过期')
            elif '已存在?' in fixed_line:
                fixed_line = fixed_line.replace('已存在?', '已存在')
            elif '不存在?' in fixed_line:
                fixed_line = fixed_line.replace('不存在?', '不存在')
            elif '失败?' in fixed_line:
                fixed_line = fixed_line.replace('失败?', '失败')
            elif '成功?' in fixed_line:
                fixed_line = fixed_line.replace('成功?', '成功')
            elif '错误?' in fixed_line:
                fixed_line = fixed_line.replace('错误?', '错误')
            elif '警告?' in fixed_line:
                fixed_line = fixed_line.replace('警告?', '警告')
            elif '信息?' in fixed_line:
                fixed_line = fixed_line.replace('信息?', '信息')
            elif '配置?' in fixed_line:
                fixed_line = fixed_line.replace('配置?', '配置')
            elif '文件?' in fixed_line:
                fixed_line = fixed_line.replace('文件?', '文件')
            elif '目录?' in fixed_line:
                fixed_line = fixed_line.replace('目录?', '目录')
            elif '模块?' in fixed_line:
                fixed_line = fixed_line.replace('模块?', '模块')
            elif '服务?' in fixed_line:
                fixed_line = fixed_line.replace('服务?', '服务')
            elif '请求?' in fixed_line:
                fixed_line = fixed_line.replace('请求?', '请求')
            elif '响应?' in fixed_line:
                fixed_line = fixed_line.replace('响应?', '响应')
            elif '数据?' in fixed_line:
                fixed_line = fixed_line.replace('数据?', '数据')
            elif '功能：?' in fixed_line:
                fixed_line = fixed_line.replace('功能：?', '功能：')
            elif '参数：?' in fixed_line:
                fixed_line = fixed_line.replace('参数：?', '参数：')
            elif '返回：?' in fixed_line:
                fixed_line = fixed_line.replace('返回：?', '返回：')
            elif '类型：?' in fixed_line:
                fixed_line = fixed_line.replace('类型：?', '类型：')
            elif '状态：?' in fixed_line:
                fixed_line = fixed_line.replace('状态：?', '状态：')
            elif '名称：?' in fixed_line:
                fixed_line = fixed_line.replace('名称：?', '名称：')
            elif '描述：?' in fixed_line:
                fixed_line = fixed_line.replace('描述：?', '描述：')
            else:
                # 通用修复：将末尾的 ? 替换为合适的字符
                pass
        
        fixed_lines.append(fixed_line)
    
    return '\n'.join(fixed_lines)

def fix_unterminated_strings(content: str) -> str:
    """修复未终止的字符串"""
    lines = content.split('\n')
    fixed_lines = []
    
    for i, line in enumerate(lines):
        # 检查未终止的字符串
        if line.count('"') % 2 == 1 and not line.strip().endswith('\\'):
            # 尝试添加闭合引号
            if '?' in line:
                # 替换 ? 为合适的中文结尾
                line = line.rstrip()
                if line.endswith('?'):
                    line = line[:-1] + '）"'
                elif line.endswith('?"'):
                    line = line[:-2] + '）"'
                else:
                    line = line + '"'
        
        if line.count("'") % 2 == 1 and not line.strip().endswith('\\'):
            if '?' in line:
                line = line.rstrip()
                if line.endswith('?'):
                    line = line[:-1] + "）'"
                elif line.endswith("?'"):
                    line = line[:-2] + "）'"
                else:
                    line = line + "'"
        
        fixed_lines.append(line)
    
    return '\n'.join(fixed_lines)

def is_valid_python(content: str) -> bool:
    """检查是否是有效的 Python 代码"""
    try:
        ast.parse(content)
        return True
    except:
        return False

def fix_file(filepath: str) -> Tuple[bool, str]:
    """修复单个文件"""
    content, encoding = try_read_file(filepath)
    
    if content is None:
        return False, "无法读取文件"
    
    # 如果已经是有效的 Python，跳过
    if is_valid_python(content):
        return True, "文件已经是有效的"
    
    # 尝试修复
    fixed_content = fix_truncated_chinese(content)
    fixed_content = fix_unterminated_strings(fixed_content)
    
    # 检查修复后是否有效
    if is_valid_python(fixed_content):
        # 保存修复后的文件
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(fixed_content)
            return True, "修复成功"
        except Exception as e:
            return False, f"保存失败: {e}"
    
    return False, "无法自动修复"

def scan_and_fix_directory(directory: str) -> List[Tuple[str, bool, str]]:
    """扫描并修复目录中的所有 Python 文件"""
    results = []
    
    for root, dirs, files in os.walk(directory):
        # 跳过虚拟环境
        if 'venv' in root or '.venv' in root or '__pycache__' in root:
            continue
        
        for f in files:
            if f.endswith('.py'):
                filepath = os.path.join(root, f)
                
                # 先检查是否有问题
                try:
                    with open(filepath, 'r', encoding='utf-8') as fp:
                        content = fp.read()
                    ast.parse(content)
                    # 没有问题，跳过
                    continue
                except SyntaxError:
                    pass
                except UnicodeDecodeError:
                    pass
                except:
                    continue
                
                # 有问题，尝试修复
                success, message = fix_file(filepath)
                results.append((filepath, success, message))
    
    return results

if __name__ == "__main__":
    server_dir = os.path.dirname(os.path.abspath(__file__))
    print(f"扫描目录: {server_dir}")
    print("=" * 60)
    
    results = scan_and_fix_directory(server_dir)
    
    if results:
        print(f"\n处理了 {len(results)} 个文件:\n")
        for filepath, success, message in results:
            status = "✓" if success else "✗"
            print(f"  {status} {filepath}")
            print(f"      {message}")
    else:
        print("\n没有需要修复的文件")
