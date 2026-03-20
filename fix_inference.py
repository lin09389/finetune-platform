# Fix the think tag handling in inference.py

with open("C:/Users/JHJ/Desktop/finetune-platform/server/api/inference.py", "r", encoding="utf-8") as f:
    content = f.read()

# The old broken code (checking for space instead of think tags)
old_code = '''                        if " " in text:
                            in_think_block = True
                            text = text.split(" ")[-1] if " " in text else text

                        if " " in text:
                            in_think_block = False
                            text = text.split(" ")[-1] if " " in text else text
                        elif in_think_block:
                            text = ""'''

# New correct code - properly handle Qwen think tags
new_code = '''                        # Handle Qwen think tags
                        if "<think>" in text:
                            in_think_block = True
                            # Remove content before and including <think>
                            text = text.split("<think>")[-1] if "<think>" in text else text

                        if "</think>" in text:
                            in_think_block = False
                            # Remove content after and including </think>
                            text = text.split("</think>")[0] if "</think>" in text else text
                        elif in_think_block:
                            # Inside think block, skip output
                            text = ""'''

# Replace all occurrences
new_content = content.replace(old_code, new_code)

if new_content != content:
    with open("C:/Users/JHJ/Desktop/finetune-platform/server/api/inference.py", "w", encoding="utf-8") as f:
        f.write(new_content)
    print("Fixed think tag handling in inference.py")
else:
    print("No changes made - pattern not found")
    # Debug: print the actual content around line 735
    lines = content.split('\n')
    for i in range(730, 750):
        if i < len(lines):
            print(f"{i+1}: {repr(lines[i])}")