# -*- coding: utf-8 -*-
"""检查所有 Python 文件是否有语法错误"""
import ast
import os
import sys

def check_python_files(directory):
    errors = []
    for root, dirs, files in os.walk(directory):
        # Skip venv directories
        if 'venv' in root or '.venv' in root or '__pycache__' in root:
            continue
        
        for f in files:
            if f.endswith('.py'):
                filepath = os.path.join(root, f)
                try:
                    with open(filepath, 'r', encoding='utf-8') as fp:
                        content = fp.read()
                    ast.parse(content)
                except SyntaxError as e:
                    errors.append((filepath, f"SyntaxError: {e.msg} (line {e.lineno})"))
                except UnicodeDecodeError as e:
                    errors.append((filepath, f"UnicodeDecodeError: {e}"))
                except Exception as e:
                    errors.append((filepath, str(e)))
    
    return errors

if __name__ == "__main__":
    server_dir = os.path.dirname(os.path.abspath(__file__))
    errors = check_python_files(server_dir)
    
    if errors:
        print(f"Found {len(errors)} files with errors:\n")
        for filepath, error in errors:
            print(f"  {filepath}")
            print(f"    Error: {error}\n")
    else:
        print("All Python files are valid!")
