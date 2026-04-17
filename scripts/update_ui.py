import os

file_path = 'client/src/index.css'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update Fonts
content = content.replace(
    "--font-sans: 'Inter', -apple-system",
    "--font-sans: 'Geist', 'Outfit', 'Inter', -apple-system"
).replace(
    "--font-mono: 'JetBrains Mono'",
    "--font-mono: 'Geist Mono', 'JetBrains Mono'"
)

# 2. Update Shadows
content = content.replace(
    "--shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.04);",
    "--shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.02), 0 1px 1px rgba(0, 0, 0, 0.01);"
).replace(
    "--shadow-md: 0 4px 12px rgba(0, 0, 0, 0.05);",
    "--shadow-md: 0 4px 6px -1px rgba(0, 0, 0, 0.03), 0 2px 4px -2px rgba(0, 0, 0, 0.02);"
).replace(
    "--shadow-lg: 0 12px 32px rgba(0, 0, 0, 0.08);",
    "--shadow-lg: 0 10px 15px -3px rgba(0, 0, 0, 0.04), 0 4px 6px -4px rgba(0, 0, 0, 0.02);"
).replace(
    "--shadow-xl: 0 24px 64px rgba(0, 0, 0, 0.12);",
    "--shadow-xl: 0 20px 25px -5px rgba(0, 0, 0, 0.05), 0 8px 10px -6px rgba(0, 0, 0, 0.03);"
)

# 3. Update Radiuses
content = content.replace(
    "--radius-sm: 4px;\n  --radius-md: 6px;\n  --radius-lg: 12px;\n  --radius-xl: 16px;",
    "--radius-sm: 6px;\n  --radius-md: 8px;\n  --radius-lg: 16px;\n  --radius-xl: 24px;"
)

# 4. Update Transitions
content = content.replace(
    "--transition-fast: 100ms cubic-bezier(0.16, 1, 0.3, 1);\n  --transition-base: 150ms cubic-bezier(0.16, 1, 0.3, 1);\n  --transition-slow: 250ms cubic-bezier(0.16, 1, 0.3, 1);",
    "--transition-fast: 150ms cubic-bezier(0.25, 1, 0.5, 1);\n  --transition-base: 250ms cubic-bezier(0.25, 1, 0.5, 1);\n  --transition-slow: 400ms cubic-bezier(0.25, 1, 0.5, 1);\n  --transition-spring: 500ms cubic-bezier(0.34, 1.56, 0.64, 1);"
)

# 5. Update Light Theme
content = content.replace(
    "--bg-primary: #fafaf9;\n  --bg-secondary: #ffffff;\n  --bg-elevated: #f4f4f5;\n  --bg-hover: #eeeeef;\n  --bg-active: #e4e4e7;",
    "--bg-primary: #FAFAFA;\n  --bg-secondary: #FFFFFF;\n  --bg-elevated: #F4F4F5;\n  --bg-hover: #F1F1F3;\n  --bg-active: #E4E4E7;"
).replace(
    "--border-color: #e4e4e7;\n  --border-hover: #c4c4c7;\n  --border-active: #71717a;",
    "--border-color: #E5E7EB;\n  --border-hover: #D4D4D8;\n  --border-active: #A1A1AA;"
).replace(
    "--accent-primary: #3b5bdb;\n  --accent-primary-hover: #2f4ecf;\n  --accent-primary-light: #edf2ff;\n  --accent-secondary: #7c3aed;",
    "--accent-primary: #4F46E5;\n  --accent-primary-hover: #4338CA;\n  --accent-primary-light: #EEF2FF;\n  --accent-secondary: #7C3AED;"
)

# 6. Update Dark Theme
content = content.replace(
    "--bg-primary: #09090b;\n  --bg-secondary: #111113;\n  --bg-elevated: #1c1c1f;\n  --bg-hover: #27272a;\n  --bg-active: #3f3f46;",
    "--bg-primary: #000000;\n  --bg-secondary: #0A0A0A;\n  --bg-elevated: #141414;\n  --bg-hover: #1F1F1F;\n  --bg-active: #27272A;"
).replace(
    "--border-color: #27272a;\n  --border-hover: #3f3f46;\n  --border-active: #71717a;",
    "--border-color: #262626;\n  --border-hover: #3F3F46;\n  --border-active: #52525B;"
).replace(
    "--accent-primary: #6880e8;\n  --accent-primary-hover: #7c8ff0;\n  --accent-primary-light: #1e2a6e28;\n  --accent-secondary: #a78bfa;",
    "--accent-primary: #6366F1;\n  --accent-primary-hover: #818CF8;\n  --accent-primary-light: rgba(99, 102, 241, 0.1);\n  --accent-secondary: #A78BFA;"
)

# 7. Update button animations for spring effect
content = content.replace(
    "transition: all var(--transition-fast);",
    "transition: all var(--transition-spring);"
).replace(
    "transition: all 0.12s cubic-bezier(0.16, 1, 0.3, 1) !important;",
    "transition: all var(--transition-spring) !important;"
)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)
print('UI/UX Phase 1 implemented successfully via index.css update.')