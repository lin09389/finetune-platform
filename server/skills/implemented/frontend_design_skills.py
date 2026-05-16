"""
前端设计 UI/UX 技能 - 提供高质量、独特的前端界面设计建议和代码生成
"""

from skills.base import SkillBase
from skills.models import (
    SkillCategory,
    SkillMetadata,
    SkillParameter,
    SkillParameterType,
    SkillResult,
)


class FrontendDesignSkill(SkillBase):
    """前端设计 UI/UX 技能"""

    COLOR_SCHEMES = {
        "retro_digital": {
            "name": "复古数字风",
            "primary": "#1a1a2e",
            "secondary": "#16213e",
            "accent": "#e94560",
            "text": "#eaeaea",
            "muted": "#0f3460",
        },
        "editorial": {
            "name": "编辑主义",
            "background": "#faf9f7",
            "primary": "#2d2d2d",
            "accent": "#d4a373",
            "secondary": "#6b7280",
            "border": "#e5e5e5",
        },
        "cyber_craftsman": {
            "name": "赛博工匠",
            "dark": "#0d1117",
            "light": "#f0f6fc",
            "accent": "#ff6b35",
            "secondary": "#58a6ff",
            "success": "#3fb950",
        },
        "oriental_elegant": {
            "name": "东方雅致",
            "background": "#f7f5f0",
            "ink": "#2c2c2c",
            "vermilion": "#c45c48",
            "cyan": "#5b8a72",
            "gold": "#c9b037",
        },
    }

    TYPOGRAPHY = {
        "headings": {
            "en": ["Playfair Display", "Space Grotesk", "Clash Display"],
            "cn": ["Source Han Serif CN", "Noto Serif SC"],
        },
        "body": {
            "en": ["Inter", "Switzer", "General Sans"],
            "cn": ["Source Han Sans CN", "Noto Sans SC"],
        },
        "sizes": {
            "hero": "64px",
            "h1": "48px",
            "h2": "32px",
            "h3": "24px",
            "body": "16px",
            "small": "14px",
            "caption": "12px",
        },
    }

    SPACING = {
        "1": "4px",
        "2": "8px",
        "3": "12px",
        "4": "16px",
        "5": "24px",
        "6": "32px",
        "7": "48px",
        "8": "64px",
    }

    @classmethod
    def get_metadata(cls) -> SkillMetadata:
        return SkillMetadata(
            name="frontend_design",
            display_name="前端设计 UI/UX",
            description="提供高质量、独特的前端界面设计建议和代码生成",
            version="1.0.0",
            category=SkillCategory.DESIGN,
            tags=["frontend", "ui", "ux", "design", "css", "tailwind"],
            parameters=[
                SkillParameter(
                    name="component_type",
                    type=SkillParameterType.STRING,
                    description="组件类型: button, card, input, navigation, dashboard, form",
                    required=True,
                ),
                SkillParameter(
                    name="style",
                    type=SkillParameterType.STRING,
                    description="设计风格: retro_digital, editorial, cyber_craftsman, oriental_elegant",
                    required=False,
                    default="editorial",
                ),
                SkillParameter(
                    name="framework",
                    type=SkillParameterType.STRING,
                    description="框架: tailwind, css, styled-components",
                    required=False,
                    default="tailwind",
                ),
            ],
            examples=[
                {"component_type": "button", "style": "editorial"},
                {"component_type": "dashboard", "style": "cyber_craftsman"},
                {"component_type": "card", "style": "oriental_elegant"},
            ],
        )

    async def execute(self, **kwargs) -> SkillResult:
        component_type = kwargs.get("component_type", "")
        style = kwargs.get("style", "editorial")
        framework = kwargs.get("framework", "tailwind")

        if not component_type:
            return SkillResult(
                success=False,
                error="请提供组件类型",
                error_code="MISSING_COMPONENT_TYPE",
            )

        color_scheme = self.COLOR_SCHEMES.get(style, self.COLOR_SCHEMES["editorial"])

        component_code = self._generate_component(component_type, color_scheme, framework)
        design_tokens = self._get_design_tokens(color_scheme)

        return SkillResult(
            success=True,
            data={
                "component_type": component_type,
                "style": style,
                "framework": framework,
                "code": component_code,
                "design_tokens": design_tokens,
                "color_scheme": color_scheme,
            },
        )

    def _generate_component(self, component_type: str, colors: dict, framework: str) -> str:
        if framework == "tailwind":
            return self._generate_tailwind_component(component_type, colors)
        else:
            return self._generate_css_component(component_type, colors)

    def _generate_tailwind_component(self, component_type: str, colors: dict) -> str:
        components = {
            "button": self._tailwind_button(colors),
            "card": self._tailwind_card(colors),
            "input": self._tailwind_input(colors),
            "navigation": self._tailwind_navigation(colors),
            "dashboard": self._tailwind_dashboard(colors),
            "form": self._tailwind_form(colors),
        }
        return components.get(component_type, f"// {component_type} 组件代码待生成")

    def _tailwind_button(self, colors: dict) -> str:
        primary = colors.get("primary", "#2d2d2d")
        return f'''// 主按钮 - 实心填充
<button className="
  px-6 py-3
  bg-[{primary}]
  text-white
  text-sm font-medium
  rounded-md
  transition-all duration-200
  hover:bg-[#1a1a1a]
  active:scale-[0.98]
  focus:outline-none focus:ring-2 focus:ring-[{primary}]/20
">
  确认操作
</button>

// 次按钮 - 描边风格
<button className="
  px-6 py-3
  bg-transparent
  border border-[#e5e5e5]
  text-[{primary}]
  text-sm font-medium
  rounded-md
  transition-all duration-200
  hover:bg-[#faf9f7] hover:border-[#d4d4d4]
  active:bg-[#f0f0f0]
">
  取消
</button>'''

    def _tailwind_card(self, colors: dict) -> str:
        primary = colors.get("primary", "#2d2d2d")
        return f'''// 编辑主义风格卡片
<div className="
  bg-white
  border border-[#e5e5e5]
  rounded-lg
  p-6
  transition-all duration-200
  hover:border-[#d4d4d4]
  hover:shadow-[0_2px_8px_rgba(0,0,0,0.04)]
">
  <div className="flex items-start justify-between mb-4">
    <h3 className="text-lg font-semibold text-[{primary}]">卡片标题</h3>
    <span className="text-xs text-[#6b7280] uppercase tracking-wider">标签</span>
  </div>
  <p className="text-[#6b7280] leading-relaxed">
    卡片内容描述，使用舒适的行高和灰度层次。
  </p>
</div>'''

    def _tailwind_input(self, colors: dict) -> str:
        return '''// 精致输入框
<div className="space-y-2">
  <label className="text-sm font-medium text-[#2d2d2d]">
    邮箱地址
  </label>
  <input
    type="email"
    className="
      w-full px-4 py-3
      bg-white
      border border-[#e5e5e5]
      rounded-md
      text-[#2d2d2d] placeholder:text-[#9ca3af]
      transition-all duration-200
      focus:outline-none focus:border-[#2d2d2d] focus:ring-1 focus:ring-[#2d2d2d]/10
      hover:border-[#d4d4d4]
    "
    placeholder="name@example.com"
  />
  <p className="text-xs text-[#6b7280]">我们将发送验证邮件到此地址</p>
</div>'''

    def _tailwind_navigation(self, colors: dict) -> str:
        return '''// 顶部导航 - 编辑风格
<nav className="
  sticky top-0 z-50
  bg-[#faf9f7]/95 backdrop-blur-sm
  border-b border-[#e5e5e5]
">
  <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
    <div className="flex items-center gap-2">
      <div className="w-8 h-8 bg-[#2d2d2d] rounded-md flex items-center justify-center">
        <span className="text-white font-bold text-sm">L</span>
      </div>
      <span className="font-semibold text-[#2d2d2d] tracking-tight">Logo</span>
    </div>
    <div className="flex items-center gap-1">
      {['首页', '产品', '关于', '联系'].map((item) => (
        <a key={item} href="#" className="px-4 py-2 text-sm text-[#6b7280] rounded-md transition-all hover:text-[#2d2d2d] hover:bg-[#f0f0f0]">
          {item}
        </a>
      ))}
    </div>
    <button className="px-4 py-2 bg-[#2d2d2d] text-white text-sm font-medium rounded-md transition-all hover:bg-[#1a1a1a]">
      开始使用
    </button>
  </div>
</nav>'''

    def _tailwind_dashboard(self, colors: dict) -> str:
        return '''// Dashboard 页面 - 编辑主义风格
<div className="min-h-screen bg-[#faf9f7]">
  {/* Stats Grid */}
  <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
    {[
      { label: '总项目', value: '24', change: '+12%' },
      { label: '进行中', value: '8', change: '+3' },
      { label: '已完成', value: '16', change: '98%' }
    ].map((stat) => (
      <div key={stat.label} className="bg-white border border-[#e5e5e5] rounded-lg p-6 transition-all hover:border-[#d4d4d4] hover:shadow-[0_2px_8px_rgba(0,0,0,0.04)]">
        <p className="text-sm text-[#6b7280] mb-1">{stat.label}</p>
        <div className="flex items-baseline gap-2">
          <span className="text-3xl font-semibold text-[#2d2d2d]">{stat.value}</span>
          <span className="text-sm text-[#5b8a72] font-medium">{stat.change}</span>
        </div>
      </div>
    ))}
  </div>
</div>'''

    def _tailwind_form(self, colors: dict) -> str:
        return '''// 表单组件
<form className="space-y-6 bg-white border border-[#e5e5e5] rounded-lg p-6">
  <div className="space-y-2">
    <label className="text-sm font-medium text-[#2d2d2d]">用户名</label>
    <input type="text" className="w-full px-4 py-3 bg-white border border-[#e5e5e5] rounded-md text-[#2d2d2d] transition-all focus:outline-none focus:border-[#2d2d2d]" placeholder="请输入用户名" />
  </div>
  <div className="space-y-2">
    <label className="text-sm font-medium text-[#2d2d2d]">密码</label>
    <input type="password" className="w-full px-4 py-3 bg-white border border-[#e5e5e5] rounded-md text-[#2d2d2d] transition-all focus:outline-none focus:border-[#2d2d2d]" placeholder="请输入密码" />
  </div>
  <button type="submit" className="w-full px-6 py-3 bg-[#2d2d2d] text-white text-sm font-medium rounded-md transition-all hover:bg-[#1a1a1a]">
    登录
  </button>
</form>'''

    def _generate_css_component(self, component_type: str, colors: dict) -> str:
        primary = colors.get("primary", "#2d2d2d")
        return f"""/* CSS 组件代码 - {component_type} */
.btn-primary {{
  padding: 0.75rem 1.5rem;
  background-color: {primary};
  color: white;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s ease;
}}
.btn-primary:hover {{
  opacity: 0.9;
  transform: translateY(-1px);
}}"""

    def _get_design_tokens(self, colors: dict) -> dict:
        return {
            "colors": colors,
            "typography": self.TYPOGRAPHY,
            "spacing": self.SPACING,
            "shadows": {
                "float": "0 2px 8px rgba(0, 0, 0, 0.04)",
                "elevate": "0 1px 2px rgba(0, 0, 0, 0.02), 0 4px 12px rgba(0, 0, 0, 0.04)",
                "focus": "0 0 0 1px rgba(0, 0, 0, 0.05), 0 20px 40px rgba(0, 0, 0, 0.1)",
            },
            "border_radius": {
                "sm": "4px",
                "md": "8px",
                "lg": "12px",
                "full": "9999px",
            },
        }
