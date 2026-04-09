"""
帮助系统 API 路由
"""

from fastapi import APIRouter, Query
from pydantic import BaseModel

from agent.help_system import (
    HelpCategory,
    format_help,
    get_help_system,
    search_help,
)

router = APIRouter(prefix="/help", tags=["help"])


class CommandHelpResponse(BaseModel):
    """命令帮助响应"""
    command: str
    description: str
    examples: list[str]
    parameters: dict[str, str]
    tips: list[str]
    related_commands: list[str]


class CategoryHelpResponse(BaseModel):
    """类别帮助响应"""
    category: str
    name: str
    commands: list[str]


class SearchResult(BaseModel):
    """搜索结果"""
    command: str
    description: str


class HelpOverviewResponse(BaseModel):
    """帮助概览响应"""
    categories: dict[str, list[str]]
    total_commands: int


class HelpTopicResponse(BaseModel):
    """帮助主题响应"""
    title: str
    content: str
    see_also: list[str]


@router.get("", response_model=HelpOverviewResponse)
async def get_help_overview():
    """
    获取帮助概览

    返回所有命令类别和命令列表
    """
    system = get_help_system()
    categories = system.get_all_categories()

    category_names = {
        "file_operations": "文件操作",
        "screen_operations": "屏幕操作",
        "app_operations": "应用操作",
        "system_operations": "系统操作",
        "getting_started": "快速入门",
        "troubleshooting": "故障排除",
        "advanced": "高级功能",
    }

    named_categories = {}
    for category, commands in categories.items():
        name = category_names.get(category.value, category.value)
        named_categories[name] = commands

    return HelpOverviewResponse(
        categories=named_categories,
        total_commands=len(system.get_all_commands()),
    )


@router.get("/search", response_model=list[SearchResult])
async def search_help_commands(
    q: str = Query(..., description="搜索关键词"),
    limit: int = Query(10, ge=1, le=50, description="返回结果数量限制"),
):
    """
    搜索帮助命令

    根据关键词搜索相关命令
    """
    results = search_help(q)[:limit]

    return [
        SearchResult(
            command=cmd.command,
            description=cmd.description,
        )
        for cmd in results
    ]


@router.get("/category/{category}", response_model=CategoryHelpResponse)
async def get_category_help(category: str):
    """
    获取类别帮助

    返回指定类别下的所有命令
    """
    category_mapping = {
        "file": HelpCategory.FILE_OPERATIONS,
        "file_operations": HelpCategory.FILE_OPERATIONS,
        "screen": HelpCategory.SCREEN_OPERATIONS,
        "screen_operations": HelpCategory.SCREEN_OPERATIONS,
        "app": HelpCategory.APP_OPERATIONS,
        "app_operations": HelpCategory.APP_OPERATIONS,
    }

    help_category = category_mapping.get(category.lower())
    if not help_category:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"未找到类别: {category}")

    system = get_help_system()
    commands = system.get_category_commands(help_category)

    category_names = {
        HelpCategory.FILE_OPERATIONS: "文件操作",
        HelpCategory.SCREEN_OPERATIONS: "屏幕操作",
        HelpCategory.APP_OPERATIONS: "应用操作",
    }

    return CategoryHelpResponse(
        category=help_category.value,
        name=category_names.get(help_category, help_category.value),
        commands=[cmd.command for cmd in commands],
    )


@router.get("/command/{command}", response_model=CommandHelpResponse)
async def get_command_help(command: str):
    """
    获取命令详细帮助

    返回指定命令的详细帮助信息
    """
    system = get_help_system()
    cmd = system.get_command_help(command)

    if not cmd:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"未找到命令: {command}")

    return CommandHelpResponse(
        command=cmd.command,
        description=cmd.description,
        examples=cmd.examples,
        parameters=cmd.parameters,
        tips=cmd.tips,
        related_commands=cmd.related_commands,
    )


@router.get("/topic/{topic}", response_model=HelpTopicResponse)
async def get_help_topic(topic: str):
    """
    获取帮助主题

    返回指定主题的详细帮助内容
    """
    system = get_help_system()
    help_topic = system.get_topic(topic)

    if not help_topic:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"未找到主题: {topic}")

    return HelpTopicResponse(
        title=help_topic.title,
        content=help_topic.content,
        see_also=help_topic.see_also,
    )


@router.get("/format")
async def get_formatted_help(
    query: str = Query(None, description="查询关键词，为空则返回概览"),
):
    """
    获取格式化的帮助文本

    返回可直接显示的帮助文本
    """
    return {
        "text": format_help(query),
    }
