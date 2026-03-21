"""
批量修复编码问题的脚本
"""
import os
import re
from pathlib import Path

# 常见的编码错误模式及其修复
ENCODING_FIXES = {
    # 常见的中文字符截断
    r'测试\b': '测试',
    r'文件\b': '文件',
    r'功能\b': '功能',
    r'状态\b': '状态',
    r'信息\b': '信息',
    r'模型\b': '模型',
    r'训练\b': '训练',
    r'数据\b': '数据',
    r'参数\b': '参数',
    r'结果\b': '结果',
    r'错误\b': '错误',
    r'成功\b': '成功',
    r'失败\b': '失败',
    r'获取\b': '获取',
    r'设置\b': '设置',
    r'列表\b': '列表',
    r'检查\b': '检查',
    r'验证\b': '验证',
    r'连接\b': '连接',
    r'网络\b': '网络',
    r'请求\b': '请求',
    r'响应\b': '响应',
    r'处理\b': '处理',
    r'配置\b': '配置',
    r'系统\b': '系统',
    r'服务\b': '服务',
    r'接口\b': '接口',
    r'方法\b': '方法',
    r'类型\b': '类型',
    r'名称\b': '名称',
    r'路径\b': '路径',
    r'目录\b': '目录',
    r'内容\b': '内容',
    r'大小\b': '大小',
    r'数量\b': '数量',
    r'时间\b': '时间',
    r'日期\b': '日期',
    r'版本\b': '版本',
    r'用户\b': '用户',
    r'会话\b': '会话',
    r'消息\b': '消息',
    r'对话\b': '对话',
    r'输入\b': '输入',
    r'输出\b': '输出',
    r'返回\b': '返回',
    r'执行\b': '执行',
    r'操作\b': '操作',
    r'创建\b': '创建',
    r'更新\b': '更新',
    r'删除\b': '删除',
    r'查询\b': '查询',
    r'搜索\b': '搜索',
    r'过滤\b': '过滤',
    r'排序\b': '排序',
    r'分页\b': '分页',
    r'统计\b': '统计',
    r'报告\b': '报告',
    r'日志\b': '日志',
    r'警告\b': '警告',
    r'异常\b': '异常',
    r'注意\b': '注意',
    r'说明\b': '说明',
    r'描述\b': '描述',
    r'示例\b': '示例',
    r'备注\b': '备注',
    r'注释\b': '注释',
}

def fix_file_encoding(file_path: Path) -> bool:
    """尝试修复单个文件的编码问题"""
    try:
        # 尝试用 UTF-8 读取
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return True  # 文件正常，无需修复
    except UnicodeDecodeError:
        # 尝试用其他编码读取
        encodings = ['gbk', 'gb2312', 'gb18030', 'latin-1', 'cp1252']
        
        for encoding in encodings:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    content = f.read()
                
                # 修复常见的编码问题
                fixed_content = content
                for pattern, replacement in ENCODING_FIXES.items():
                    fixed_content = re.sub(pattern, replacement, fixed_content)
                
                # 用 UTF-8 写回
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(fixed_content)
                
                print(f"已修复: {file_path} (从 {encoding} 转换)")
                return True
                
            except (UnicodeDecodeError, UnicodeEncodeError):
                continue
        
        print(f"无法修复: {file_path}")
        return False

def main():
    """主函数"""
    server_dir = Path(__file__).parent
    tests_dir = server_dir / "tests"
    
    if not tests_dir.exists():
        print("tests 目录不存在")
        return
    
    fixed_count = 0
    failed_count = 0
    
    for py_file in tests_dir.glob("*.py"):
        if fix_file_encoding(py_file):
            fixed_count += 1
        else:
            failed_count += 1
    
    print(f"\n修复完成: {fixed_count} 个文件")
    print(f"修复失败: {failed_count} 个文件")

if __name__ == "__main__":
    main()
