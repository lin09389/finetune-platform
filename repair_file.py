# 修复 inference.py - 替换损坏的 generate 函数

# 读取所有行
with open('server/api/inference.py', 'r', encoding='utf-8') as f:
    all_lines = f.readlines()

# 保留前 683 行 (0-682)
# 替换 683-692 (10 行)
# 保留 693 行之后

# 新的 generate 函数体 (从第 684 行开始，共 10 行替换)
new_code_lines = [
    '        async def generate() -> AsyncGenerator[str, None]:\n',
    '            in_think_block = False\n',
    '            try:\n',
    '                for text in streamer:\n',
    '                    if text:\n',
    '                        # 清理特殊标记和思考标签\n',
    '                        cleaned = text.replace("