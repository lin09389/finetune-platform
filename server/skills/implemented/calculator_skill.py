"""
计算器技�?执行数学计算
"""
import math
from typing import Dict, Any

from skills.base import SkillBase
from skills.models import SkillMetadata, SkillParameter, SkillResult, SkillCategory


class CalculatorSkill(SkillBase):
    """计算器技�?""
    
    metadata = SkillMetadata(
        name="calculator",
        display_name="计算�?,
        description="执行数学计算",
        version="1.0.0",
        category=SkillCategory.UTILITY,
        parameters=[
            SkillParameter(
                name="expression",
                type="string",
                description="数学表达�?,
                required=True,
            ),
        ],
        tags=["math", "calculate", "utility"],
    )
    
    SAFE_FUNCTIONS = {
        'abs': abs, 'round': round, 'min': min, 'max': max,
        'sum': sum, 'pow': pow, 'sqrt': math.sqrt,
        'sin': math.sin, 'cos': math.cos, 'tan': math.tan,
        'log': math.log, 'log10': math.log10, 'exp': math.exp,
        'pi': math.pi, 'e': math.e,
    }
    
    async def execute(self, **kwargs) -> SkillResult:
        expression = kwargs.get("expression")
        
        if not expression:
            return SkillResult(
                success=False,
                error="缺少 expression 参数",
                error_code="MISSING_PARAMETER",
            )
        
        try:
            result = self._safe_eval(expression)
            
            return SkillResult(
                success=True,
                data={
                    "expression": expression,
                    "result": result,
                },
                message=f"计算结果: {expression} = {result}",
            )
            
        except Exception as e:
            return SkillResult(
                success=False,
                error=f"计算错误: {str(e)}",
                error_code="CALCULATION_ERROR",
            )
    
    def _safe_eval(self, expression: str):
        safe_dict = {"__builtins__": {}}
        safe_dict.update(self.SAFE_FUNCTIONS)
        result = eval(expression, safe_dict, {})
        return result


def get_skill():
    return CalculatorSkill()
