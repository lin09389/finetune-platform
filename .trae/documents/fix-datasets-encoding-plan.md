# datasets.py 编码问题修复计划

## 问题分析

`server/api/datasets.py` 文件存在编码损坏问题，表现为：
- 中文字符被截断，显示为 `?` 后跟不完整字符
- 例如：`数据集管?API` 应为 `数据集管理 API`
- 例如：`延迟初始?_datasets_dir` 应为 `延迟初始化 _datasets_dir`

这是典型的 UTF-8 编码损坏问题，可能原因：
1. 文件在传输过程中编码转换错误
2. Git 在 Windows 上处理编码不当
3. 编辑器保存时使用了错误的编码

## 修复方案

### 方案一：从 Git 历史恢复（推荐）

如果 Git 历史中有正确的版本：

```bash
# 查看文件历史
git log --oneline server/api/datasets.py

# 恢复到特定提交
git checkout <commit_hash> -- server/api/datasets.py
```

### 方案二：使用编码修复脚本

创建 Python 脚本自动修复常见编码问题：

```python
# fix_datasets_encoding.py
import re

file_path = 'server/api/datasets.py'

with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
    content = f.read()

# 定义修复映射
fixes = {
    # 文档字符串
    '数据集管?API': '数据集管理 API',
    '统计功?': '统计功能',
    
    # 注释
    '延迟初始?': '延迟初始化',
    '数据集目?': '数据集目录',
    '数据集信?': '数据集信息',
    '数据集列?': '数据集列表',
    '数据集描?': '数据集描述',
    '数据集文?': '数据集文件',
    '数据集名?': '数据集名称',
    '文件名安全处?': '文件名安全处理',
    '生成数据?ID': '生成数据集ID',
    '格式验证和样本计?': '格式验证和样本计数',
    '保存元信?': '保存元信息',
    'JSON 文件检查大?': 'JSON 文件检查大小',
    '消息长度分布（按角色?': '消息长度分布（按角色）',
    '计算数据集统计信?': '计算数据集统计信息',
    '尝试从数据文件生成信?': '尝试从数据文件生成信息',
    
    # 函数返回值描述
    '错误消?': '错误消息',
    '样本?': '样本数',
    '验证数据集格?': '验证数据集格式',
    '如果?messages 字段': '如果有 messages 字段',
    
    # 错误消息
    '空文?': '空文件',
    '数据?': '数据集',
    '数据文件不存?': '数据文件不存在',
    '数据集删除成?': '数据集删除成功',
    '数据集上传成?': '数据集上传成功',
    '统计信息已更?': '统计信息已更新',
    '读取数据集信息失?': '读取数据集信息失败',
    '加载数据集失?': '加载数据集失败',
    '减小文件大小?': '减小文件大小）',
    '获取数据集详?': '获取数据集详情',
    '预览数据?': '预览数据集',
    '删除数据?': '删除数据集',
    '刷新数据集统计信?': '刷新数据集统计信息',
    '获取数据集统计信?': '获取数据集统计信息',
}

for old, new in fixes.items():
    content = content.replace(old, new)

# 移除替换字符
content = content.replace('\ufffd', '')

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)
```

### 方案三：手动重写文件

如果损坏严重，考虑：
1. 从其他相似项目复制模板
2. 根据功能需求重新编写
3. 使用 AI 辅助生成

## 实施步骤

1. **检查 Git 历史**
   - 运行 `git log --oneline server/api/datasets.py`
   - 查找是否有正确的版本

2. **尝试 Git 恢复**
   - 如果找到正确版本，使用 `git checkout` 恢复
   - 验证文件是否正常

3. **运行修复脚本**
   - 如果 Git 恢复失败，运行编码修复脚本
   - 验证修复后的文件语法

4. **验证修复结果**
   - 运行 `python -c "from api.datasets import router"`
   - 确保无语法错误

5. **提交修复**
   - `git add server/api/datasets.py`
   - `git commit -m "fix: 修复 datasets.py 编码问题"`

## 预防措施

1. **Git 配置**
   ```bash
   git config --global core.autocrlf false
   git config --global core.safecrlf true
   ```

2. **编辑器配置**
   - 确保编辑器使用 UTF-8 编码保存
   - 添加 `.editorconfig` 文件统一编码配置

3. **CI 检查**
   - 添加编码检查到 CI 流程
   - 使用 `file` 命令检查文件编码
