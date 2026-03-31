"""
意图检测训练数据集
包含完整的意图样本、参数模板和权重配置
支持多意图、口语化表达、模糊表达
"""
from dataclasses import dataclass, field
from typing import Any


@dataclass
class IntentSample:
    """意图样本"""
    text: str
    params_template: dict[str, Any] = field(default_factory=dict)
    confidence_base: float = 0.8
    keywords: list[str] = field(default_factory=list)
    context_hints: list[str] = field(default_factory=list)
    is_colloquial: bool = False
    is_negative: bool = False


INTENT_TRAINING_DATA: dict[str, dict[str, Any]] = {
    "file_create": {
        "samples": [
            IntentSample("创建一个新文件", {"file_path": ""}, 0.85, ["创建", "新文件"]),
            IntentSample("新建一个test.py文件", {"file_path": "test.py"}, 0.95, ["新建", "test.py"]),
            IntentSample("帮我创建一个README.md", {"file_path": "README.md"}, 0.95, ["创建", "README.md"]),
            IntentSample("生成一个配置文件", {"file_path": "config"}, 0.80, ["生成", "配置文件"]),
            IntentSample("建立一个新文档", {"file_path": ""}, 0.75, ["建立", "新文档"]),
            IntentSample("创建一个空的文件", {"file_path": ""}, 0.85, ["创建", "空文件"]),
            IntentSample("新建config.json配置文件", {"file_path": "config.json"}, 0.95, ["新建", "config.json"]),
            IntentSample("帮我新建一个日志文件", {"file_path": ""}, 0.85, ["新建", "日志文件"]),
            IntentSample("建立一个数据文件", {"file_path": ""}, 0.75, ["建立", "数据文件"]),
            IntentSample("生成index.html首页", {"file_path": "index.html"}, 0.95, ["生成", "index.html"]),
            IntentSample("创建main.py主程序文件", {"file_path": "main.py"}, 0.95, ["创建", "main.py"]),
            IntentSample("建立一个样式文件", {"file_path": ""}, 0.80, ["创建", "样式文件"]),
            IntentSample("新建style.css样式表", {"file_path": "style.css"}, 0.95, ["新建", "style.css"]),
            IntentSample("生成README文档", {"file_path": "README.md"}, 0.90, ["生成", "README.md"]),
            IntentSample("创建一个YAML配置", {"file_path": ""}, 0.80, ["创建", "YAML"]),
            IntentSample("新建docker-compose.yml", {"file_path": "docker-compose.yml"}, 0.95, ["新建", "docker-compose.yml"]),
        ],
        "colloquial_samples": [
            IntentSample("弄一个新文件", {"file_path": ""}, 0.70, ["弄", "新文件"], is_colloquial=True),
            IntentSample("搞个Python脚本", {"file_path": ""}, 0.70, ["搞", "Python"], is_colloquial=True),
            IntentSample("帮我弄个配置", {"file_path": ""}, 0.65, ["弄", "配置"], is_colloquial=True),
        ],
        "negative_samples": [
            IntentSample("不要创建文件", {}, 0.9, ["不要", "创建"], is_negative=True),
            IntentSample("取消新建", {}, 0.8, ["取消", "新建"], is_negative=True),
        ],
        "keywords_weight": {
            "创建": 0.3, "新建": 0.3, "生成": 0.25, "建立": 0.2,
            "文件": 0.15, "文档": 0.1, "脚本": 0.1
        },
        "params_extractors": {
            "file_path": r"(?:创建|新建|生成|建立)\s*(?:一个)?(?:新)?(?:文件|文档|脚本)?\s*(\S+\.\w+)"
        }
    },
    "file_read": {
        "samples": [
            IntentSample("读取config.json文件", {"file_path": "config.json"}, 0.95, ["读取", "config.json"]),
            IntentSample("查看README.md的内容", {"file_path": "README.md"}, 0.95, ["查看", "README.md"]),
            IntentSample("打开main.py文件", {"file_path": "main.py"}, 0.95, ["打开", "main.py"]),
            IntentSample("显示test.txt的内容", {"file_path": "test.txt"}, 0.95, ["显示", "test.txt"]),
            IntentSample("帮我看看package.json", {"file_path": "package.json"}, 0.90, ["看看", "package.json"]),
            IntentSample("读取配置文件", {"file_path": ""}, 0.70, ["读取", "配置文件"]),
            IntentSample("查看当前文件内容", {"file_path": ""}, 0.65, ["查看", "文件内容"]),
            IntentSample("打开日志文件看看", {"file_path": ""}, 0.70, ["打开", "日志文件"]),
        ],
        "colloquial_samples": [
            IntentSample("看看这个文件", {"file_path": ""}, 0.60, ["看看", "文件"], is_colloquial=True),
            IntentSample("读一下那个文档", {"file_path": ""}, 0.60, ["读一下", "文档"], is_colloquial=True),
        ],
        "negative_samples": [
            IntentSample("不要读取文件", {}, 0.9, ["不要", "读取"], is_negative=True),
            IntentSample("不需要查看", {}, 0.8, ["不需要", "查看"], is_negative=True),
        ],
        "keywords_weight": {
            "读取": 0.3, "查看": 0.3, "打开": 0.25, "显示": 0.25, "看看": 0.2,
            "内容": 0.1, "代码": 0.1, "文件": 0.1
        },
        "params_extractors": {
            "file_path": r"(?:读取|查看|打开|显示|看看)\s*(\S+\.\w+)"
        }
    },
    "file_write": {
        "samples": [
            IntentSample("把config.json的内容改成{}", {"file_path": "config.json", "content": "{}"}, 0.95, ["改成", "config.json"]),
            IntentSample("写入test.txt内容Hello", {"file_path": "test.txt", "content": "Hello"}, 0.95, ["写入", "test.txt"]),
            IntentSample("在README.md中添加说明", {"file_path": "README.md"}, 0.85, ["添加", "README.md"]),
            IntentSample("修改main.py的代码", {"file_path": "main.py"}, 0.80, ["修改", "main.py"]),
            IntentSample("更新配置文件", {"file_path": ""}, 0.70, ["更新", "配置文件"]),
        ],
        "colloquial_samples": [
            IntentSample("改一下这个文件", {"file_path": ""}, 0.60, ["改", "文件"], is_colloquial=True),
            IntentSample("把那个改一改", {"file_path": ""}, 0.55, ["改一改"], is_colloquial=True),
        ],
        "negative_samples": [
            IntentSample("不要写入", {}, 0.9, ["不要", "写入"], is_negative=True),
            IntentSample("不改了", {}, 0.8, ["不改"], is_negative=True),
        ],
        "keywords_weight": {
            "写入": 0.3, "修改": 0.3, "更新": 0.25, "添加": 0.25, "改成": 0.3,
            "内容": 0.1, "代码": 0.1, "配置": 0.1
        },
        "params_extractors": {
            "file_path": r"(?:写入|修改|更新|添加|改成)\s*(\S+\.\w+)",
            "content": r"(?:改成|内容|写入)\s*[\"']?(.+?)[\"']?(?:\s|$)"
        }
    },
    "file_delete": {
        "samples": [
            IntentSample("删除test.txt文件", {"file_path": "test.txt"}, 0.95, ["删除", "test.txt"]),
            IntentSample("移除old_config.json", {"file_path": "old_config.json"}, 0.95, ["移除", "old_config.json"]),
            IntentSample("删除临时文件", {"file_path": ""}, 0.70, ["删除", "临时文件"]),
            IntentSample("移除备份文件", {"file_path": ""}, 0.70, ["移除", "备份文件"]),
        ],
        "colloquial_samples": [
            IntentSample("把这个删了", {"file_path": ""}, 0.60, ["删了"], is_colloquial=True),
            IntentSample("去掉那个文件", {"file_path": ""}, 0.60, ["去掉", "文件"], is_colloquial=True),
        ],
        "negative_samples": [
            IntentSample("不要删除", {}, 0.9, ["不要", "删除"], is_negative=True),
            IntentSample("保留这个", {}, 0.8, ["保留"], is_negative=True),
        ],
        "keywords_weight": {
            "删除": 0.35, "移除": 0.35, "清除": 0.25, "清理": 0.2,
            "文件": 0.1, "目录": 0.1
        },
        "params_extractors": {
            "file_path": r"(?:删除|移除|清除|清理)\s*(\S+)"
        },
        "need_confirm": True
    },
    "file_list": {
        "samples": [
            IntentSample("列出当前目录的文件", {"directory": "."}, 0.95, ["列出", "目录", "文件"]),
            IntentSample("显示src文件夹内容", {"directory": "src"}, 0.95, ["显示", "src"]),
            IntentSample("查看当前目录", {"directory": "."}, 0.90, ["查看", "目录"]),
            IntentSample("列出所有文件", {"directory": "."}, 0.85, ["列出", "所有"]),
            IntentSample("显示项目文件结构", {"directory": "."}, 0.80, ["显示", "文件结构"]),
        ],
        "colloquial_samples": [
            IntentSample("看看有什么文件", {"directory": "."}, 0.65, ["看看", "文件"], is_colloquial=True),
            IntentSample("这目录里都有啥", {"directory": "."}, 0.55, ["都有啥"], is_colloquial=True),
        ],
        "negative_samples": [],
        "keywords_weight": {
            "列出": 0.3, "显示": 0.25, "查看": 0.25, "ls": 0.35,
            "目录": 0.15, "文件列表": 0.15, "文件": 0.1, "内容": 0.1
        },
        "params_extractors": {
            "directory": r"(?:列出|显示|查看|ls)\s*(\S+)?\s*(?:目录|文件夹)?"
        }
    },
    "app_open": {
        "samples": [
            IntentSample("打开VS Code", {"app_name": "vscode"}, 0.95, ["打开", "VS Code"]),
            IntentSample("启动VSCode编辑器", {"app_name": "vscode"}, 0.90, ["启动", "VSCode"]),
            IntentSample("打开记事本", {"app_name": "notepad"}, 0.95, ["打开", "记事本"]),
            IntentSample("启动Chrome浏览器", {"app_name": "chrome"}, 0.90, ["启动", "Chrome"]),
        ],
        "colloquial_samples": [
            IntentSample("开VSCode", {"app_name": "vscode"}, 0.80, ["开", "VSCode"], is_colloquial=True),
            IntentSample("起个终端", {"app_name": "terminal"}, 0.70, ["起", "终端"], is_colloquial=True),
        ],
        "negative_samples": [],
        "keywords_weight": {
            "打开": 0.3, "启动": 0.3, "运行": 0.25, "开启": 0.2,
            "应用": 0.1, "程序": 0.1, "软件": 0.1
        },
        "params_extractors": {
            "app_name": r"(?:打开|启动|运行|开启)\s*(\S+)"
        }
    },
    "url_open": {
        "samples": [
            IntentSample("打开https://github.com", {"url": "https://github.com"}, 0.98, ["打开", "github.com"]),
            IntentSample("访问http://localhost:3000", {"url": "http://localhost:3000"}, 0.98, ["访问", "localhost"]),
        ],
        "colloquial_samples": [],
        "negative_samples": [],
        "keywords_weight": {
            "打开": 0.2, "访问": 0.2, "网址": 0.15, "网站": 0.15,
            "http": 0.4, "https": 0.4, "www": 0.3
        },
        "params_extractors": {
            "url": r"(https?://\S+)"
        }
    },
    "screenshot": {
        "samples": [
            IntentSample("截图", {"monitor": 0}, 0.98, ["截图"]),
            IntentSample("截屏", {"monitor": 0}, 0.98, ["截屏"]),
            IntentSample("截取屏幕", {"monitor": 0}, 0.98, ["截取", "屏幕"]),
        ],
        "colloquial_samples": [
            IntentSample("帮我截一下", {"monitor": 0}, 0.85, ["截一下"], is_colloquial=True),
            IntentSample("来张截图", {"monitor": 0}, 0.80, ["来张"], is_colloquial=True),
        ],
        "negative_samples": [],
        "keywords_weight": {
            "截图": 0.4, "截屏": 0.4, "截取": 0.3, "拍照": 0.2, "屏幕": 0.2
        },
        "params_extractors": {}
    },
}


def get_intent_samples(intent_name: str) -> list[IntentSample]:
    """获取指定意图的样本列表"""
    intent_data = INTENT_TRAINING_DATA.get(intent_name, {})
    samples = intent_data.get("samples", [])
    samples.extend(intent_data.get("colloquial_samples", []))
    return samples


def get_all_samples() -> list[tuple]:
    """获取所有意图样本"""
    all_samples = []
    for intent_name, data in INTENT_TRAINING_DATA.items():
        for sample in data.get("samples", []):
            all_samples.append((intent_name, sample))
        for sample in data.get("colloquial_samples", []):
            all_samples.append((intent_name, sample))
    return all_samples


def get_keywords_weight(intent_name: str) -> dict[str, float]:
    """获取意图的关键词权重"""
    intent_data = INTENT_TRAINING_DATA.get(intent_name, {})
    return intent_data.get("keywords_weight", {})


def get_params_extractors(intent_name: str) -> dict[str, str]:
    """获取意图的参数提取器"""
    intent_data = INTENT_TRAINING_DATA.get(intent_name, {})
    return intent_data.get("params_extractors", {})


def get_all_intent_names() -> list[str]:
    """获取所有意图名称"""
    return list(INTENT_TRAINING_DATA.keys())
