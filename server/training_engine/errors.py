"""
训练异常定义
"""


class RecoverableError(Exception):
    """可恢复错误 - 训练失败后可自动重试"""
    pass


class UnrecoverableError(Exception):
    """不可恢复错误 - 需要用户干预"""
    pass
