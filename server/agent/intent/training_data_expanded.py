"""
意图检测训练数据集 - 扩充版
每个意图至少 100+ 样本
使用模板生成、同义词替换、句式变换等方法
"""
from dataclasses import dataclass, field
from typing import Any


@dataclass
class IntentSample:
    text: str
    params_template: dict[str, Any] = field(default_factory=dict)
    confidence_base: float = 0.8
    keywords: list[str] = field(default_factory=list)
    context_hints: list[str] = field(default_factory=list)
    is_colloquial: bool = False
    is_negative: bool = False


def generate_samples(templates: list[str], params_list: list[dict] = None, keywords: list[str] = None) -> list[IntentSample]:
    samples = []
    for template in templates:
        if params_list:
            for params in params_list:
                try:
                    text = template.format(**params)
                    samples.append(IntentSample(text, params, 0.9, keywords or []))
                except KeyError:
                    samples.append(IntentSample(template, {}, 0.85, keywords or []))
        else:
            samples.append(IntentSample(template, {}, 0.85, keywords or []))
    return samples


FILE_NAMES = [
    "main.py", "app.py", "server.py", "client.py", "config.py", "utils.py",
    "test.py", "tests.py", "models.py", "views.py", "api.py", "handler.py",
    "index.js", "app.js", "server.js", "client.js", "config.js", "utils.js",
    "index.ts", "app.ts", "main.ts", "config.ts", "utils.ts", "types.ts",
    "index.html", "app.html", "main.html", "index.css", "style.css", "app.css",
    "README.md", "CHANGELOG.md", "TODO.md", "LICENSE", "requirements.txt",
    "package.json", "tsconfig.json", "docker-compose.yml", "Dockerfile",
    "config.json", "settings.json", "data.json", "env.json", "db.json",
    "config.yaml", "settings.yaml", "data.yaml", "docker-compose.yaml",
    "config.xml", "data.xml", "pom.xml", "build.gradle",
    ".gitignore", ".env", ".editorconfig", ".prettierrc", ".eslintrc",
    "Makefile", "Vagrantfile", "Jenkinsfile",
    "logo.png", "icon.svg", "banner.jpg", "image.gif",
    "data.csv", "report.xlsx", "notes.txt", "log.txt", "output.log",
]

APP_NAMES = [
    "VS Code", "Visual Studio Code", "VSCode", "Chrome", "Google Chrome",
    "Firefox", "Edge", "Microsoft Edge", "Safari", "Opera",
    "PyCharm", "IntelliJ IDEA", "WebStorm", "CLion", "GoLand",
    "Sublime Text", "Atom", "Notepad++", "Vim", "Neovim",
    "Terminal", "命令提示符", "PowerShell", "CMD", "Git Bash",
    "微信", "QQ", "钉钉", "飞书", "企业微信",
    "Word", "Excel", "PowerPoint", "Outlook", "OneNote",
    "Photoshop", "Illustrator", "Figma", "Sketch", "XD",
    "Spotify", "网易云音乐", "QQ音乐", "酷狗音乐",
    "Telegram", "Discord", "Slack", "Teams", "Zoom",
    "FileZilla", "WinSCP", "PuTTY", "Xshell", "MobaXterm",
    "Docker", "Postman", "Insomnia", "Redis", "MongoDB Compass",
]

URLS = [
    "https://www.google.com", "https://www.baidu.com", "https://www.bing.com",
    "https://github.com", "https://stackoverflow.com", "https://csdn.net",
    "https://www.python.org", "https://nodejs.org", "https://react.dev",
    "https://vuejs.org", "https://angular.io", "https://nextjs.org",
    "https://tailwindcss.com", "https://ant.design", "https://mui.com",
    "https://huggingface.co", "https://pytorch.org", "https://tensorflow.org",
    "https://openai.com", "https://anthropic.com", "https://deepmind.com",
    "https://www.youtube.com", "https://www.bilibili.com", "https://www.zhihu.com",
    "https://www.reddit.com", "https://twitter.com", "https://weibo.com",
    "https://localhost:3000", "https://localhost:8080", "https://127.0.0.1:8000",
]

SEARCH_TERMS = [
    "Python教程", "JavaScript入门", "React开发", "Vue学习", "TypeScript指南",
    "机器学习", "深度学习", "自然语言处理", "计算机视觉", "数据科学",
    "Docker使用", "Kubernetes部署", "CI/CD流水线", "Git操作", "Linux命令",
    "API设计", "数据库优化", "微服务架构", "分布式系统", "云原生",
    "前端优化", "后端开发", "全栈工程师", "DevOps", "测试自动化",
    "算法学习", "数据结构", "设计模式", "代码重构", "性能优化",
    "人工智能", "大模型", "GPT", "LLM", "RAG",
]


def create_file_create_samples() -> list[IntentSample]:
    samples = []

    verbs = ["创建", "新建", "生成", "建立", "创建一个", "新建一个", "生成一个", "建立一个"]
    adjectives = ["新", "空的", "空白", "新的"]
    nouns = ["文件", "文档", "脚本", "代码文件", "文本文件"]

    for verb in verbs:
        for adj in adjectives:
            for noun in nouns:
                samples.append(IntentSample(f"{verb}{adj}{noun}", {}, 0.85, ["创建", "新建"]))

    for verb in ["创建", "新建", "生成", "建立"]:
        for fname in FILE_NAMES[:30]:
            samples.append(IntentSample(f"{verb}{fname}文件", {"file_path": fname}, 0.95, [fname]))
            samples.append(IntentSample(f"帮我{verb}一个{fname}", {"file_path": fname}, 0.9, [fname]))
            samples.append(IntentSample(f"请{verb}{fname}", {"file_path": fname}, 0.95, [fname]))

    colloquial = [
        "弄个新文件", "搞个文件", "来个新文档", "整一个文件",
        "给我建个文件", "帮我弄个文件", "搞个Python脚本",
        "弄个HTML出来", "来个配置文件", "整一个test.py",
        "建个文件呗", "弄个空文件", "搞个新脚本", "来个文档",
        "整一个配置", "给我弄个文件", "帮我搞个脚本", "建个新文档",
        "弄个main.py", "搞个index.html", "来个config.json",
    ]
    for text in colloquial:
        samples.append(IntentSample(text, {}, 0.7, [], is_colloquial=True))

    return samples


def create_file_read_samples() -> list[IntentSample]:
    samples = []

    verbs = ["读取", "查看", "打开", "阅读", "显示", "浏览", "查看一下", "读取一下", "打开一下"]
    nouns = ["文件", "文档", "内容", "代码", "源码", "源代码"]

    for verb in verbs:
        for noun in nouns:
            samples.append(IntentSample(f"{verb}{noun}", {}, 0.8, ["读取", "查看"]))
            samples.append(IntentSample(f"帮我{verb}{noun}", {}, 0.85, ["读取", "查看"]))
            samples.append(IntentSample(f"请{verb}{noun}", {}, 0.85, ["读取", "查看"]))

    for verb in ["读取", "查看", "打开", "阅读", "显示"]:
        for fname in FILE_NAMES[:30]:
            samples.append(IntentSample(f"{verb}{fname}", {"file_path": fname}, 0.95, [fname]))
            samples.append(IntentSample(f"{verb}{fname}文件", {"file_path": fname}, 0.95, [fname]))
            samples.append(IntentSample(f"{verb}{fname}的内容", {"file_path": fname}, 0.95, [fname]))
            samples.append(IntentSample(f"帮我{verb}{fname}", {"file_path": fname}, 0.9, [fname]))

    context_refs = [
        "读取刚才那个文件", "查看上一个文件", "打开刚才创建的文件",
        "读取它", "查看它", "打开它", "显示它的内容",
        "读取这个文件", "查看这个文件", "打开这个文件",
        "读取那个文件", "查看那个文件", "打开那个文件",
        "读取最近的文件", "查看最近的文件", "打开最近的文件",
    ]
    for text in context_refs:
        samples.append(IntentSample(text, {}, 0.75, ["读取", "查看"]))

    colloquial = [
        "看看文件", "瞅瞅代码", "瞧瞧内容", "瞄一眼文件",
        "打开看看", "读一下", "看一眼", "打开瞧瞧",
        "文件里写的啥", "代码怎么写的", "里面有什么",
        "给我看看文件", "帮我看看代码", "让我看看内容",
        "这个文件是啥", "那个文件呢", "刚才的文件",
    ]
    for text in colloquial:
        samples.append(IntentSample(text, {}, 0.7, [], is_colloquial=True))

    return samples


def create_file_write_samples() -> list[IntentSample]:
    samples = []

    verbs = ["写入", "修改", "编辑", "更新", "更改", "改一下", "编辑一下", "修改一下"]

    for verb in verbs:
        samples.append(IntentSample(f"{verb}文件", {}, 0.8, ["写入", "修改"]))
        samples.append(IntentSample(f"帮我{verb}文件", {}, 0.85, ["写入", "修改"]))
        samples.append(IntentSample(f"请{verb}文件", {}, 0.85, ["写入", "修改"]))

    contents = [
        "Hello World", "你好世界", "测试内容", "示例代码",
        "print('hello')", "console.log('hi')", "def main(): pass",
        "# 这是注释", "// 注释内容", "/* 多行注释 */",
    ]

    for verb in ["写入", "添加", "追加", "插入"]:
        for content in contents[:5]:
            samples.append(IntentSample(f"{verb}内容：{content}", {"content": content}, 0.85, ["写入"]))
            samples.append(IntentSample(f"在文件中{verb}{content}", {"content": content}, 0.85, ["写入"]))

    for verb in ["修改", "编辑", "更新", "更改"]:
        for fname in FILE_NAMES[:20]:
            samples.append(IntentSample(f"{verb}{fname}", {"file_path": fname}, 0.9, [fname]))
            samples.append(IntentSample(f"{verb}{fname}文件", {"file_path": fname}, 0.9, [fname]))
            samples.append(IntentSample(f"帮我{verb}{fname}", {"file_path": fname}, 0.85, [fname]))

    colloquial = [
        "改一下文件", "修一下代码", "编辑一下", "更新一下",
        "帮我改改", "给我改一下", "弄一下文件", "调一下代码",
        "文件改改", "代码修修", "内容换换", "文本改改",
        "把文件改了", "把代码改了", "把内容换了",
    ]
    for text in colloquial:
        samples.append(IntentSample(text, {}, 0.7, [], is_colloquial=True))

    return samples


def create_file_delete_samples() -> list[IntentSample]:
    samples = []

    verbs = ["删除", "移除", "删掉", "去掉", "清除", "删除一个", "移除一个", "删掉一个"]
    nouns = ["文件", "文档", "脚本", "代码文件"]

    for verb in verbs:
        for noun in nouns:
            samples.append(IntentSample(f"{verb}{noun}", {}, 0.85, ["删除", "移除"]))
            samples.append(IntentSample(f"帮我{verb}{noun}", {}, 0.9, ["删除", "移除"]))
            samples.append(IntentSample(f"请{verb}{noun}", {}, 0.9, ["删除", "移除"]))

    for verb in ["删除", "移除", "删掉", "去掉", "清除"]:
        for fname in FILE_NAMES[:25]:
            samples.append(IntentSample(f"{verb}{fname}", {"file_path": fname}, 0.95, [fname]))
            samples.append(IntentSample(f"{verb}{fname}文件", {"file_path": fname}, 0.95, [fname]))
            samples.append(IntentSample(f"帮我{verb}{fname}", {"file_path": fname}, 0.9, [fname]))
            samples.append(IntentSample(f"把{fname}{verb}了", {"file_path": fname}, 0.9, [fname]))

    colloquial = [
        "删了文件", "干掉文件", "弄掉文件", "去掉文件",
        "把文件删了", "把文件干掉", "把文件弄掉",
        "删了吧", "不要了", "清理一下", "清掉文件",
        "帮我删了", "给我删掉", "删掉它", "移除它",
        "这个文件不要了", "那个文件删了", "刚才的文件删掉",
    ]
    for text in colloquial:
        samples.append(IntentSample(text, {}, 0.7, [], is_colloquial=True))

    return samples


def create_file_list_samples() -> list[IntentSample]:
    samples = []

    templates = [
        "列出{}文件", "显示{}文件", "查看{}文件", "列举{}文件",
        "列出{}目录", "显示{}目录", "查看{}目录", "列举{}目录",
        "列出{}文件夹", "显示{}文件夹", "查看{}文件夹", "列举{}文件夹",
        "帮我列出{}文件", "帮我显示{}文件", "帮我查看{}文件",
        "请列出{}文件", "请显示{}文件", "请查看{}文件",
    ]

    modifiers = ["当前", "所有", "全部", "项目中的", "目录下的", "文件夹里的", ""]

    for template in templates:
        for modifier in modifiers:
            samples.append(IntentSample(template.format(modifier), {}, 0.85, ["列出", "显示"]))

    more_templates = [
        "文件列表", "目录列表", "文件夹列表",
        "有什么文件", "有哪些文件", "文件都有什么",
        "目录里有什么", "文件夹里有什么", "里面有什么文件",
        "ls", "dir", "列出文件", "显示目录",
        "查看当前目录", "浏览文件", "文件浏览",
        "项目结构", "目录结构", "文件夹结构",
        "树形结构", "文件树", "目录树",
    ]
    for text in more_templates:
        samples.append(IntentSample(text, {}, 0.8, ["列出", "显示"]))

    colloquial = [
        "看看有什么文件", "瞅瞅目录", "瞧瞧文件夹",
        "文件都在哪", "目录里有啥", "文件夹里都有啥",
        "给我看看文件", "帮我看看目录", "让我看看文件夹",
        "文件呢", "目录呢", "文件夹呢",
        "都有啥文件", "有些什么文件", "文件列表看看",
    ]
    for text in colloquial:
        samples.append(IntentSample(text, {}, 0.7, [], is_colloquial=True))

    return samples


def create_file_copy_samples() -> list[IntentSample]:
    samples = []

    verbs = ["复制", "拷贝", "copy", "复制一下", "拷贝一下"]
    nouns = ["文件", "文档", "脚本", "代码"]

    for verb in verbs:
        for noun in nouns:
            samples.append(IntentSample(f"{verb}{noun}", {}, 0.85, ["复制", "拷贝"]))
            samples.append(IntentSample(f"帮我{verb}{noun}", {}, 0.9, ["复制", "拷贝"]))

    for verb in ["复制", "拷贝", "copy"]:
        for fname in FILE_NAMES[:20]:
            samples.append(IntentSample(f"{verb}{fname}", {"file_path": fname}, 0.95, [fname]))
            samples.append(IntentSample(f"{verb}{fname}文件", {"file_path": fname}, 0.95, [fname]))
            samples.append(IntentSample(f"把{fname}{verb}一份", {"file_path": fname}, 0.9, [fname]))

    destinations = ["桌面", "Documents", "Downloads", "项目目录", "当前目录", "上级目录", "backup文件夹"]
    for verb in ["复制到", "拷贝到", "复制一份到"]:
        for dest in destinations:
            samples.append(IntentSample(f"{verb}{dest}", {"destination": dest}, 0.85, ["复制", "拷贝"]))

    colloquial = [
        "复制一下", "拷贝一份", "copy一下", "复制个副本",
        "帮我复制", "给我拷贝", "复制文件呗",
        "把这个复制了", "把那个拷贝了", "复制它",
        "文件复制一下", "文档拷贝一份", "代码复制",
    ]
    for text in colloquial:
        samples.append(IntentSample(text, {}, 0.7, [], is_colloquial=True))

    return samples


def create_file_move_samples() -> list[IntentSample]:
    samples = []

    verbs = ["移动", "转移", "搬移", "移动一下", "转移一下"]
    nouns = ["文件", "文档", "脚本"]

    for verb in verbs:
        for noun in nouns:
            samples.append(IntentSample(f"{verb}{noun}", {}, 0.85, ["移动", "转移"]))
            samples.append(IntentSample(f"帮我{verb}{noun}", {}, 0.9, ["移动", "转移"]))

    destinations = ["桌面", "Documents", "Downloads", "项目目录", "当前目录", "上级目录", "backup文件夹", "新文件夹"]
    for verb in ["移动到", "转移到", "搬移到"]:
        for dest in destinations:
            samples.append(IntentSample(f"{verb}{dest}", {"destination": dest}, 0.85, ["移动", "转移"]))
            samples.append(IntentSample(f"把文件{verb}{dest}", {"destination": dest}, 0.85, ["移动", "转移"]))

    for fname in FILE_NAMES[:15]:
        for dest in destinations[:5]:
            samples.append(IntentSample(f"把{fname}移动到{dest}", {"file_path": fname, "destination": dest}, 0.9, [fname]))

    colloquial = [
        "移动一下", "转移一下", "搬一下文件", "挪一下",
        "帮我移动", "给我转移", "移动文件呗",
        "把这个移走", "把那个转移", "移动它",
        "文件移动一下", "文档转移一下", "挪个位置",
    ]
    for text in colloquial:
        samples.append(IntentSample(text, {}, 0.7, [], is_colloquial=True))

    return samples


def create_file_rename_samples() -> list[IntentSample]:
    samples = []

    verbs = ["重命名", "改名", "改名子", "重命名一下", "改名一下"]
    nouns = ["文件", "文档", "脚本"]

    for verb in verbs:
        for noun in nouns:
            samples.append(IntentSample(f"{verb}{noun}", {}, 0.85, ["重命名", "改名"]))
            samples.append(IntentSample(f"帮我{verb}{noun}", {}, 0.9, ["重命名", "改名"]))

    new_names = ["new_file.py", "backup.py", "old_version.py", "v2.py", "updated.py"]
    for verb in ["重命名为", "改名为", "改名为"]:
        for new_name in new_names:
            samples.append(IntentSample(f"{verb}{new_name}", {"new_name": new_name}, 0.85, ["重命名"]))

    for fname in FILE_NAMES[:15]:
        samples.append(IntentSample(f"把{fname}重命名", {"file_path": fname}, 0.9, [fname]))
        samples.append(IntentSample(f"重命名{fname}", {"file_path": fname}, 0.95, [fname]))

    colloquial = [
        "改个名", "换个名字", "名字改一下", "重命名一下",
        "帮我改名", "给我改名", "改名呗",
        "把这个改名", "把那个重命名", "改个名字",
        "文件改个名", "文档换个名", "名字换换",
    ]
    for text in colloquial:
        samples.append(IntentSample(text, {}, 0.7, [], is_colloquial=True))

    return samples


def create_app_open_samples() -> list[IntentSample]:
    samples = []

    verbs = ["打开", "启动", "运行", "开启", "启动一下", "打开一下", "运行一下"]

    for verb in verbs:
        for app in APP_NAMES:
            samples.append(IntentSample(f"{verb}{app}", {"app_name": app}, 0.95, [app]))
            samples.append(IntentSample(f"帮我{verb}{app}", {"app_name": app}, 0.9, [app]))
            samples.append(IntentSample(f"请{verb}{app}", {"app_name": app}, 0.9, [app]))

    apps_short = ["VS Code", "Chrome", "Firefox", "微信", "QQ", "Terminal", "PyCharm", "Word", "Excel"]
    for app in apps_short:
        samples.append(IntentSample(f"开{app}", {"app_name": app}, 0.85, [app]))
        samples.append(IntentSample(f"开一下{app}", {"app_name": app}, 0.85, [app]))
        samples.append(IntentSample(f"把{app}打开", {"app_name": app}, 0.9, [app]))

    colloquial = [
        "开个浏览器", "打开编辑器", "启动IDE", "运行一下",
        "帮我开个应用", "给我打开软件", "启动程序",
        "打开VSCode", "开Chrome", "启动微信",
        "把VS Code开了", "把浏览器打开", "把终端开了",
        "开个VS Code呗", "打开Chrome呗", "启动微信呗",
        "VS Code打开", "Chrome启动", "微信打开",
    ]
    for text in colloquial:
        samples.append(IntentSample(text, {}, 0.7, [], is_colloquial=True))

    return samples


def create_app_close_samples() -> list[IntentSample]:
    samples = []

    verbs = ["关闭", "关掉", "退出", "结束", "关闭一下", "关掉一下", "退出一下"]

    for verb in verbs:
        for app in APP_NAMES[:20]:
            samples.append(IntentSample(f"{verb}{app}", {"app_name": app}, 0.95, [app]))
            samples.append(IntentSample(f"帮我{verb}{app}", {"app_name": app}, 0.9, [app]))
            samples.append(IntentSample(f"请{verb}{app}", {"app_name": app}, 0.9, [app]))

    apps_short = ["VS Code", "Chrome", "Firefox", "微信", "QQ", "Terminal"]
    for app in apps_short:
        samples.append(IntentSample(f"关{app}", {"app_name": app}, 0.85, [app]))
        samples.append(IntentSample(f"关一下{app}", {"app_name": app}, 0.85, [app]))
        samples.append(IntentSample(f"把{app}关了", {"app_name": app}, 0.9, [app]))

    samples.extend([
        IntentSample("关闭当前应用", {}, 0.85, ["关闭"]),
        IntentSample("关闭当前程序", {}, 0.85, ["关闭"]),
        IntentSample("退出当前应用", {}, 0.85, ["退出"]),
        IntentSample("关闭所有窗口", {}, 0.8, ["关闭"]),
        IntentSample("关闭这个窗口", {}, 0.85, ["关闭"]),
        IntentSample("关闭那个窗口", {}, 0.85, ["关闭"]),
    ])

    colloquial = [
        "关了", "退出", "关掉", "结束掉",
        "帮我关了", "给我关掉", "关掉它",
        "把程序关了", "把应用关了", "把软件关了",
        "关了VS Code", "退出Chrome", "关掉微信",
        "这个关了", "那个关掉", "刚才的关了",
    ]
    for text in colloquial:
        samples.append(IntentSample(text, {}, 0.7, [], is_colloquial=True))

    return samples


def create_url_open_samples() -> list[IntentSample]:
    samples = []

    verbs = ["打开", "访问", "跳转", "打开一下", "访问一下"]

    for verb in verbs:
        for url in URLS:
            samples.append(IntentSample(f"{verb}{url}", {"url": url}, 0.95, [url]))
            samples.append(IntentSample(f"帮我{verb}{url}", {"url": url}, 0.9, [url]))

    websites = ["百度", "谷歌", "GitHub", "知乎", "B站", "微博", "淘宝", "京东"]
    for site in websites:
        samples.append(IntentSample(f"打开{site}", {"url": site}, 0.85, [site]))
        samples.append(IntentSample(f"访问{site}网站", {"url": site}, 0.85, [site]))
        samples.append(IntentSample(f"去{site}看看", {"url": site}, 0.8, [site]))

    samples.extend([
        IntentSample("打开浏览器", {}, 0.8, ["浏览器"]),
        IntentSample("打开网页", {}, 0.8, ["网页"]),
        IntentSample("打开网站", {}, 0.8, ["网站"]),
        IntentSample("访问网页", {}, 0.8, ["网页"]),
        IntentSample("访问网站", {}, 0.8, ["网站"]),
        IntentSample("打开链接", {}, 0.85, ["链接"]),
        IntentSample("打开这个链接", {}, 0.85, ["链接"]),
        IntentSample("打开那个链接", {}, 0.85, ["链接"]),
    ])

    colloquial = [
        "打开网页", "访问网站", "去个网站", "开个链接",
        "帮我打开网页", "给我访问网站", "打开链接呗",
        "去百度", "去谷歌", "去GitHub",
        "打开这个网址", "访问那个链接", "跳转到网站",
    ]
    for text in colloquial:
        samples.append(IntentSample(text, {}, 0.7, [], is_colloquial=True))

    return samples


def create_screenshot_samples() -> list[IntentSample]:
    samples = []

    verbs = ["截图", "截屏", "抓图", "截图一下", "截屏一下", "抓图一下", "截取", "截取一下"]

    for verb in verbs:
        samples.append(IntentSample(verb, {}, 0.95, ["截图", "截屏"]))
        samples.append(IntentSample(f"帮我{verb}", {}, 0.9, ["截图", "截屏"]))
        samples.append(IntentSample(f"请{verb}", {}, 0.9, ["截图", "截屏"]))
        samples.append(IntentSample(f"{verb}一下", {}, 0.9, ["截图", "截屏"]))

    areas = ["全屏", "当前窗口", "选定区域", "整个屏幕", "这个窗口", "那个窗口",
             "屏幕", "桌面", "活动窗口", "指定区域", "矩形区域", "自定义区域"]
    for verb in ["截图", "截屏", "抓图", "截取"]:
        for area in areas:
            samples.append(IntentSample(f"{verb}{area}", {"area": area}, 0.9, ["截图"]))
            samples.append(IntentSample(f"帮我{verb}{area}", {"area": area}, 0.85, ["截图"]))
            samples.append(IntentSample(f"请{verb}{area}", {"area": area}, 0.85, ["截图"]))

    times = ["现在", "立刻", "马上", "快速", "立即"]
    for verb in ["截图", "截屏", "抓图"]:
        for time in times:
            samples.append(IntentSample(f"{time}{verb}", {}, 0.85, ["截图"]))

    samples.extend([
        IntentSample("截取全屏", {}, 0.9, ["截取"]),
        IntentSample("截取当前窗口", {}, 0.9, ["截取"]),
        IntentSample("截取选定区域", {}, 0.9, ["截取"]),
        IntentSample("截取屏幕", {}, 0.9, ["截取"]),
        IntentSample("截取画面", {}, 0.85, ["截取"]),
        IntentSample("截取图片", {}, 0.85, ["截取"]),
        IntentSample("保存截图", {}, 0.85, ["截图"]),
        IntentSample("保存截屏", {}, 0.85, ["截屏"]),
        IntentSample("截图保存", {}, 0.85, ["截图"]),
        IntentSample("截屏保存", {}, 0.85, ["截屏"]),
        IntentSample("截个图", {}, 0.85, ["截图"]),
        IntentSample("截个屏", {}, 0.85, ["截屏"]),
        IntentSample("抓个图", {}, 0.85, ["抓图"]),
        IntentSample("截图保存到桌面", {}, 0.85, ["截图"]),
        IntentSample("截屏保存到桌面", {}, 0.85, ["截屏"]),
        IntentSample("截图保存到文件", {}, 0.85, ["截图"]),
        IntentSample("截屏保存到文件", {}, 0.85, ["截屏"]),
        IntentSample("全屏截图", {}, 0.9, ["截图"]),
        IntentSample("窗口截图", {}, 0.9, ["截图"]),
        IntentSample("区域截图", {}, 0.9, ["截图"]),
        IntentSample("矩形截图", {}, 0.9, ["截图"]),
        IntentSample("自定义截图", {}, 0.9, ["截图"]),
        IntentSample("屏幕截图", {}, 0.9, ["截图"]),
        IntentSample("桌面截图", {}, 0.9, ["截图"]),
        IntentSample("窗口截屏", {}, 0.9, ["截屏"]),
        IntentSample("区域截屏", {}, 0.9, ["截屏"]),
        IntentSample("全屏截屏", {}, 0.9, ["截屏"]),
    ])

    colloquial = [
        "截个图", "截个屏", "抓个图", "截一下",
        "帮我截个图", "给我截个屏", "截个图呗",
        "把屏幕截了", "把画面截了", "截取一下",
        "全屏截图", "窗口截图", "区域截图",
        "截图保存", "截屏保存", "抓图保存",
        "截个全屏", "截个窗口", "截个区域",
        "快速截图", "快速截屏", "马上截图",
        "截图吧", "截屏吧", "抓图吧",
        "来个截图", "来个截屏", "来个抓图",
        "给我截个全屏", "帮我截个窗口", "截个区域吧",
    ]
    for text in colloquial:
        samples.append(IntentSample(text, {}, 0.7, [], is_colloquial=True))

    return samples


def create_mouse_click_samples() -> list[IntentSample]:
    samples = []

    buttons = ["左键", "右键", "中键", "鼠标左键", "鼠标右键", "鼠标中键", "左键按钮", "右键按钮"]
    for button in buttons:
        samples.append(IntentSample(f"{button}点击", {"button": button}, 0.9, ["点击"]))
        samples.append(IntentSample(f"点击{button}", {"button": button}, 0.9, ["点击"]))
        samples.append(IntentSample(f"鼠标{button}点击", {"button": button}, 0.9, ["点击"]))
        samples.append(IntentSample(f"用{button}点击", {"button": button}, 0.85, ["点击"]))
        samples.append(IntentSample(f"{button}单击", {"button": button}, 0.9, ["单击"]))
        samples.append(IntentSample(f"{button}双击", {"button": button}, 0.9, ["双击"]))

    positions = ["当前位置", "中心位置", "左上角", "右下角", "屏幕中央", "屏幕左上", "屏幕右下",
                 "窗口中心", "指定位置", "目标位置", "这里", "那里", "这个位置", "那个位置"]
    for pos in positions:
        samples.append(IntentSample(f"点击{pos}", {"position": pos}, 0.85, ["点击"]))
        samples.append(IntentSample(f"在{pos}点击", {"position": pos}, 0.85, ["点击"]))
        samples.append(IntentSample(f"鼠标点击{pos}", {"position": pos}, 0.85, ["点击"]))

    samples.extend([
        IntentSample("点击", {}, 0.85, ["点击"]),
        IntentSample("单击", {}, 0.85, ["单击"]),
        IntentSample("双击", {}, 0.85, ["双击"]),
        IntentSample("鼠标点击", {}, 0.85, ["鼠标"]),
        IntentSample("鼠标单击", {}, 0.85, ["鼠标"]),
        IntentSample("鼠标双击", {}, 0.85, ["鼠标"]),
        IntentSample("帮我点击", {}, 0.85, ["点击"]),
        IntentSample("请点击", {}, 0.85, ["点击"]),
        IntentSample("点击一下", {}, 0.85, ["点击"]),
        IntentSample("双击一下", {}, 0.85, ["双击"]),
        IntentSample("单击一下", {}, 0.85, ["单击"]),
        IntentSample("鼠标点一下", {}, 0.85, ["鼠标"]),
        IntentSample("鼠标点两下", {}, 0.85, ["鼠标"]),
        IntentSample("左键点一下", {}, 0.85, ["左键"]),
        IntentSample("右键点一下", {}, 0.85, ["右键"]),
        IntentSample("中键点一下", {}, 0.85, ["中键"]),
        IntentSample("快速点击", {}, 0.85, ["点击"]),
        IntentSample("连续点击", {}, 0.85, ["点击"]),
        IntentSample("多次点击", {}, 0.85, ["点击"]),
    ])

    colloquial = [
        "点一下", "点两下", "点点", "鼠标点一下",
        "左键点一下", "右键点一下", "双击一下",
        "帮我点一下", "给我点一下", "点一下呗",
        "这里点一下", "那里点一下", "点这里", "点那里",
        "点个击", "点一下屏幕", "点一下鼠标",
        "左键单击", "右键单击", "左键双击", "右键双击",
        "快速点一下", "连续点两下", "多点几下",
    ]
    for text in colloquial:
        samples.append(IntentSample(text, {}, 0.7, [], is_colloquial=True))

    return samples


def create_mouse_move_samples() -> list[IntentSample]:
    samples = []

    directions = ["上", "下", "左", "右", "左上", "右下", "左下", "右上", "上方", "下方", "左侧", "右侧"]
    for direction in directions:
        samples.append(IntentSample(f"鼠标向{direction}移动", {"direction": direction}, 0.85, ["移动"]))
        samples.append(IntentSample(f"向{direction}移动鼠标", {"direction": direction}, 0.85, ["移动"]))
        samples.append(IntentSample(f"移动到{direction}边", {"direction": direction}, 0.85, ["移动"]))
        samples.append(IntentSample(f"鼠标移向{direction}", {"direction": direction}, 0.85, ["移动"]))
        samples.append(IntentSample(f"把鼠标移到{direction}", {"direction": direction}, 0.85, ["移动"]))

    positions = ["屏幕中央", "左上角", "右下角", "中心位置", "顶部", "底部", "屏幕中心",
                 "屏幕左上", "屏幕右下", "窗口中心", "指定位置", "目标位置", "这里", "那里"]
    for pos in positions:
        samples.append(IntentSample(f"移动鼠标到{pos}", {"position": pos}, 0.85, ["移动"]))
        samples.append(IntentSample(f"把鼠标移到{pos}", {"position": pos}, 0.85, ["移动"]))
        samples.append(IntentSample(f"鼠标移到{pos}", {"position": pos}, 0.85, ["移动"]))
        samples.append(IntentSample(f"光标移到{pos}", {"position": pos}, 0.85, ["移动"]))

    samples.extend([
        IntentSample("移动鼠标", {}, 0.85, ["移动"]),
        IntentSample("鼠标移动", {}, 0.85, ["移动"]),
        IntentSample("移动光标", {}, 0.85, ["移动"]),
        IntentSample("光标移动", {}, 0.85, ["移动"]),
        IntentSample("帮我移动鼠标", {}, 0.85, ["移动"]),
        IntentSample("请移动鼠标", {}, 0.85, ["移动"]),
        IntentSample("移动一下鼠标", {}, 0.85, ["移动"]),
        IntentSample("鼠标移一下", {}, 0.85, ["移动"]),
        IntentSample("光标移一下", {}, 0.85, ["移动"]),
        IntentSample("移动鼠标位置", {}, 0.85, ["移动"]),
        IntentSample("改变鼠标位置", {}, 0.85, ["移动"]),
        IntentSample("设置鼠标位置", {}, 0.85, ["移动"]),
    ])

    colloquial = [
        "移一下鼠标", "动一下鼠标", "鼠标移一下",
        "把鼠标移过去", "把光标移过去", "移过去",
        "鼠标往左", "鼠标往右", "鼠标往上", "鼠标往下",
        "帮我移一下", "给我移一下", "移一下呗",
        "鼠标挪一下", "光标挪一下", "挪一下鼠标",
        "鼠标动动", "光标动动", "动动鼠标",
    ]
    for text in colloquial:
        samples.append(IntentSample(text, {}, 0.7, [], is_colloquial=True))

    return samples


def create_mouse_scroll_samples() -> list[IntentSample]:
    samples = []

    directions = ["上", "下", "向上", "向下", "往上", "往下", "朝上", "朝下"]
    for direction in directions:
        samples.append(IntentSample(f"向{direction}滚动", {"direction": direction}, 0.85, ["滚动"]))
        samples.append(IntentSample(f"滚动{direction}", {"direction": direction}, 0.85, ["滚动"]))
        samples.append(IntentSample(f"鼠标向{direction}滚动", {"direction": direction}, 0.85, ["滚动"]))
        samples.append(IntentSample(f"滚轮向{direction}滚动", {"direction": direction}, 0.85, ["滚动"]))
        samples.append(IntentSample(f"页面{direction}滚", {"direction": direction}, 0.85, ["滚动"]))
        samples.append(IntentSample(f"屏幕{direction}滚", {"direction": direction}, 0.85, ["滚动"]))

    amounts = ["一点", "一页", "半页", "很多", "到底", "到顶", "少许", "大量", "几行", "几页"]
    for amount in amounts:
        samples.append(IntentSample(f"向上滚动{amount}", {"amount": amount}, 0.85, ["滚动"]))
        samples.append(IntentSample(f"向下滚动{amount}", {"amount": amount}, 0.85, ["滚动"]))
        samples.append(IntentSample(f"滚动{amount}", {"amount": amount}, 0.85, ["滚动"]))

    samples.extend([
        IntentSample("滚动", {}, 0.85, ["滚动"]),
        IntentSample("滚轮滚动", {}, 0.85, ["滚动"]),
        IntentSample("鼠标滚动", {}, 0.85, ["滚动"]),
        IntentSample("滚动页面", {}, 0.85, ["滚动"]),
        IntentSample("滚动屏幕", {}, 0.85, ["滚动"]),
        IntentSample("帮我滚动", {}, 0.85, ["滚动"]),
        IntentSample("请滚动", {}, 0.85, ["滚动"]),
        IntentSample("滚动一下", {}, 0.85, ["滚动"]),
        IntentSample("滚轮滚一下", {}, 0.85, ["滚动"]),
        IntentSample("鼠标滚一下", {}, 0.85, ["滚动"]),
        IntentSample("页面滚动", {}, 0.85, ["滚动"]),
        IntentSample("屏幕滚动", {}, 0.85, ["滚动"]),
        IntentSample("滚到顶部", {}, 0.85, ["滚动"]),
        IntentSample("滚到底部", {}, 0.85, ["滚动"]),
        IntentSample("滚到最上面", {}, 0.85, ["滚动"]),
        IntentSample("滚到最下面", {}, 0.85, ["滚动"]),
    ])

    colloquial = [
        "滚一下", "滚轮滚一下", "滚动一下",
        "往上滚", "往下滚", "滚上去", "滚下去",
        "帮我滚一下", "给我滚一下", "滚一下呗",
        "翻页", "翻一下", "往上翻", "往下翻",
        "滚一点", "滚很多", "滚几行", "滚几页",
        "页面往下", "页面往上", "屏幕往下", "屏幕往上",
        "滚轮往上", "滚轮往下", "鼠标滚轮往上", "鼠标滚轮往下",
    ]
    for text in colloquial:
        samples.append(IntentSample(text, {}, 0.7, [], is_colloquial=True))

    return samples


def create_keyboard_type_samples() -> list[IntentSample]:
    samples = []

    texts = [
        "Hello World", "你好世界", "测试文本", "示例内容", "这是一段文字",
        "print('hello')", "console.log('hi')", "def main():", "import os",
        "from typing import", "class MyClass:", "function test() {}", "const a = 1",
        "你好", "谢谢", "再见", "好的", "可以", "没问题", "好的好的",
        "测试测试", "示例示例", "内容内容", "文字文字", "代码代码",
        "用户名", "密码", "邮箱", "手机号", "地址", "姓名",
        "2024年", "2025年", "今天", "明天", "昨天", "现在",
    ]

    for text in texts:
        samples.append(IntentSample(f"输入{text}", {"text": text}, 0.9, ["输入"]))
        samples.append(IntentSample(f"打字{text}", {"text": text}, 0.85, ["打字"]))
        samples.append(IntentSample(f"键入{text}", {"text": text}, 0.85, ["键入"]))
        samples.append(IntentSample(f"帮我输入{text}", {"text": text}, 0.85, ["输入"]))
        samples.append(IntentSample(f"请输入{text}", {"text": text}, 0.85, ["输入"]))
        samples.append(IntentSample(f"打出{text}", {"text": text}, 0.85, ["打出"]))

    samples.extend([
        IntentSample("输入文字", {}, 0.85, ["输入"]),
        IntentSample("输入文本", {}, 0.85, ["输入"]),
        IntentSample("打字", {}, 0.85, ["打字"]),
        IntentSample("键入文字", {}, 0.85, ["键入"]),
        IntentSample("键盘输入", {}, 0.85, ["键盘"]),
        IntentSample("输入内容", {}, 0.85, ["输入"]),
        IntentSample("帮我打字", {}, 0.85, ["打字"]),
        IntentSample("请输入", {}, 0.85, ["输入"]),
        IntentSample("输入一下", {}, 0.85, ["输入"]),
        IntentSample("打字一下", {}, 0.85, ["打字"]),
        IntentSample("键入一下", {}, 0.85, ["键入"]),
        IntentSample("键盘打字", {}, 0.85, ["键盘"]),
        IntentSample("敲字", {}, 0.85, ["敲字"]),
        IntentSample("敲键盘", {}, 0.85, ["敲键盘"]),
        IntentSample("输入字符串", {}, 0.85, ["输入"]),
        IntentSample("输入一段话", {}, 0.85, ["输入"]),
        IntentSample("输入一句话", {}, 0.85, ["输入"]),
    ])

    colloquial = [
        "打几个字", "输几个字", "敲几个字",
        "帮我打字", "给我输入", "打字呗",
        "输入一下", "打一下字", "敲一下键盘",
        "写字", "写几个字", "敲字",
        "打字输入", "输入打字", "敲敲键盘",
        "键盘敲敲", "打打字", "输输入",
        "敲几个字符", "输几个字符", "打几个字符",
    ]
    for text in colloquial:
        samples.append(IntentSample(text, {}, 0.7, [], is_colloquial=True))

    return samples


def create_keyboard_press_samples() -> list[IntentSample]:
    samples = []

    keys = [
        "Enter", "回车", "空格", "Space", "Tab", "Escape", "Esc",
        "Backspace", "Delete", "Del", "Insert", "Home", "End",
        "Page Up", "Page Down", "上箭头", "下箭头", "左箭头", "右箭头",
        "Ctrl", "Alt", "Shift", "Win", "Command", "Option",
        "F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9", "F10", "F11", "F12",
    ]

    for key in keys:
        samples.append(IntentSample(f"按下{key}", {"key": key}, 0.9, [key]))
        samples.append(IntentSample(f"按{key}", {"key": key}, 0.9, [key]))
        samples.append(IntentSample(f"按一下{key}", {"key": key}, 0.9, [key]))
        samples.append(IntentSample(f"帮我按{key}", {"key": key}, 0.85, [key]))

    shortcuts = [
        ("Ctrl+C", "复制"), ("Ctrl+V", "粘贴"), ("Ctrl+X", "剪切"),
        ("Ctrl+Z", "撤销"), ("Ctrl+Y", "重做"), ("Ctrl+S", "保存"),
        ("Ctrl+A", "全选"), ("Ctrl+F", "查找"), ("Ctrl+P", "打印"),
        ("Alt+Tab", "切换窗口"), ("Alt+F4", "关闭窗口"),
        ("Win+D", "显示桌面"), ("Win+E", "打开资源管理器"),
    ]

    for shortcut, _desc in shortcuts:
        samples.append(IntentSample(f"按{shortcut}", {"key": shortcut}, 0.9, [shortcut]))
        samples.append(IntentSample(f"{shortcut}快捷键", {"key": shortcut}, 0.85, [shortcut]))
        samples.append(IntentSample(f"使用{shortcut}", {"key": shortcut}, 0.85, [shortcut]))

    colloquial = [
        "按一下键", "敲一下键", "按键",
        "回车一下", "空格一下", "Tab一下",
        "帮我按一下", "给我按一下", "按一下呗",
        "快捷键", "按快捷键", "用快捷键",
    ]
    for text in colloquial:
        samples.append(IntentSample(text, {}, 0.7, [], is_colloquial=True))

    return samples


def create_window_list_samples() -> list[IntentSample]:
    samples = []

    templates = [
        "列出所有窗口", "显示所有窗口", "查看所有窗口", "列举所有窗口",
        "列出当前窗口", "显示当前窗口", "查看当前窗口",
        "列出打开的窗口", "显示打开的窗口", "查看打开的窗口",
        "窗口列表", "窗口清单", "所有窗口",
        "有什么窗口", "有哪些窗口", "窗口都有什么",
        "帮我列出窗口", "帮我显示窗口", "帮我查看窗口",
        "请列出窗口", "请显示窗口", "请查看窗口",
        "列出活动窗口", "显示活动窗口", "查看活动窗口",
        "列出运行窗口", "显示运行窗口", "查看运行窗口",
        "窗口一览", "窗口概览", "窗口总览",
        "获取窗口列表", "获取窗口信息", "获取所有窗口",
    ]

    for text in templates:
        samples.append(IntentSample(text, {}, 0.85, ["窗口", "列出"]))

    samples.extend([
        IntentSample("窗口管理", {}, 0.8, ["窗口"]),
        IntentSample("查看窗口", {}, 0.85, ["窗口"]),
        IntentSample("显示窗口", {}, 0.85, ["窗口"]),
        IntentSample("浏览窗口", {}, 0.8, ["窗口"]),
        IntentSample("当前有哪些窗口", {}, 0.85, ["窗口"]),
        IntentSample("现在有什么窗口", {}, 0.85, ["窗口"]),
        IntentSample("窗口状态", {}, 0.85, ["窗口"]),
        IntentSample("窗口信息", {}, 0.85, ["窗口"]),
        IntentSample("所有打开的窗口", {}, 0.85, ["窗口"]),
        IntentSample("正在运行的窗口", {}, 0.85, ["窗口"]),
        IntentSample("活动的窗口列表", {}, 0.85, ["窗口"]),
        IntentSample("可见窗口列表", {}, 0.85, ["窗口"]),
        IntentSample("最小化的窗口", {}, 0.85, ["窗口"]),
        IntentSample("最大化的窗口", {}, 0.85, ["窗口"]),
    ])

    colloquial = [
        "看看窗口", "瞅瞅窗口", "瞧瞧窗口",
        "窗口呢", "都有啥窗口", "窗口列表看看",
        "帮我看看窗口", "给我看看窗口", "看看有什么窗口",
        "打开的窗口", "运行的窗口", "活动的窗口",
        "窗口都有啥", "啥窗口", "哪些窗口",
        "窗口一览表", "窗口清单看看", "窗口一览看看",
    ]
    for text in colloquial:
        samples.append(IntentSample(text, {}, 0.7, [], is_colloquial=True))

    return samples


def create_window_activate_samples() -> list[IntentSample]:
    samples = []

    for app in APP_NAMES[:20]:
        samples.append(IntentSample(f"切换到{app}", {"app_name": app}, 0.9, [app]))
        samples.append(IntentSample(f"激活{app}窗口", {"app_name": app}, 0.9, [app]))
        samples.append(IntentSample(f"转到{app}", {"app_name": app}, 0.85, [app]))
        samples.append(IntentSample(f"把{app}置前", {"app_name": app}, 0.85, [app]))

    samples.extend([
        IntentSample("切换窗口", {}, 0.85, ["切换"]),
        IntentSample("激活窗口", {}, 0.85, ["激活"]),
        IntentSample("切换到下一个窗口", {}, 0.85, ["切换"]),
        IntentSample("切换到上一个窗口", {}, 0.85, ["切换"]),
        IntentSample("切换到当前窗口", {}, 0.85, ["切换"]),
        IntentSample("激活当前窗口", {}, 0.85, ["激活"]),
        IntentSample("前置窗口", {}, 0.85, ["前置"]),
        IntentSample("窗口置前", {}, 0.85, ["置前"]),
        IntentSample("显示窗口", {}, 0.85, ["显示"]),
        IntentSample("聚焦窗口", {}, 0.85, ["聚焦"]),
    ])

    colloquial = [
        "切窗口", "换窗口", "跳窗口",
        "切到VS Code", "换到Chrome", "跳到微信",
        "帮我切换", "给我切换", "切换一下",
        "到那个窗口", "去那个窗口", "切过去",
    ]
    for text in colloquial:
        samples.append(IntentSample(text, {}, 0.7, [], is_colloquial=True))

    return samples


def create_window_close_samples() -> list[IntentSample]:
    samples = []

    for app in APP_NAMES[:25]:
        samples.append(IntentSample(f"关闭{app}窗口", {"app_name": app}, 0.9, [app]))
        samples.append(IntentSample(f"关掉{app}窗口", {"app_name": app}, 0.9, [app]))
        samples.append(IntentSample(f"关闭{app}", {"app_name": app}, 0.9, [app]))
        samples.append(IntentSample(f"把{app}窗口关了", {"app_name": app}, 0.85, [app]))
        samples.append(IntentSample(f"结束{app}窗口", {"app_name": app}, 0.85, [app]))

    samples.extend([
        IntentSample("关闭窗口", {}, 0.85, ["关闭"]),
        IntentSample("关掉窗口", {}, 0.85, ["关掉"]),
        IntentSample("关闭当前窗口", {}, 0.9, ["关闭"]),
        IntentSample("关闭这个窗口", {}, 0.9, ["关闭"]),
        IntentSample("关闭那个窗口", {}, 0.9, ["关闭"]),
        IntentSample("关闭所有窗口", {}, 0.85, ["关闭"]),
        IntentSample("关闭活动窗口", {}, 0.9, ["关闭"]),
        IntentSample("帮我关闭窗口", {}, 0.85, ["关闭"]),
        IntentSample("请关闭窗口", {}, 0.85, ["关闭"]),
        IntentSample("关闭焦点窗口", {}, 0.9, ["关闭"]),
        IntentSample("关闭前台窗口", {}, 0.9, ["关闭"]),
        IntentSample("关闭可见窗口", {}, 0.85, ["关闭"]),
        IntentSample("关闭最小化窗口", {}, 0.85, ["关闭"]),
        IntentSample("关闭最大化窗口", {}, 0.85, ["关闭"]),
        IntentSample("退出窗口", {}, 0.85, ["退出"]),
        IntentSample("结束窗口", {}, 0.85, ["结束"]),
        IntentSample("销毁窗口", {}, 0.85, ["销毁"]),
    ])

    colloquial = [
        "关窗口", "关掉窗口", "窗口关了",
        "把这个窗口关了", "把那个窗口关了", "关了这个窗口",
        "帮我关窗口", "给我关窗口", "关窗口呗",
        "这个关了", "那个关掉", "窗口关掉",
        "关了当前窗口", "关掉这个窗口", "关掉那个窗口",
        "窗口不要了", "这个窗口关掉", "那个窗口关掉",
        "关掉所有窗口", "全部关掉", "都关了",
    ]
    for text in colloquial:
        samples.append(IntentSample(text, {}, 0.7, [], is_colloquial=True))

    return samples


def create_ocr_recognize_samples() -> list[IntentSample]:
    samples = []

    verbs = ["识别", "识别一下", "OCR识别", "文字识别", "识别文字", "认字", "读字", "提取文字"]
    areas = ["屏幕上的文字", "图片中的文字", "当前屏幕", "选定区域", "截图区域",
             "屏幕文字", "图片文字", "屏幕内容", "图片内容", "区域文字",
             "全屏文字", "窗口文字", "桌面文字", "当前区域文字"]

    for verb in verbs:
        for area in areas:
            samples.append(IntentSample(f"{verb}{area}", {"area": area}, 0.85, ["识别"]))
            samples.append(IntentSample(f"帮我{verb}{area}", {"area": area}, 0.8, ["识别"]))

    samples.extend([
        IntentSample("OCR识别", {}, 0.9, ["OCR"]),
        IntentSample("文字识别", {}, 0.9, ["文字"]),
        IntentSample("识别文字", {}, 0.9, ["识别"]),
        IntentSample("识别屏幕文字", {}, 0.85, ["识别"]),
        IntentSample("识别图片文字", {}, 0.85, ["识别"]),
        IntentSample("提取文字", {}, 0.85, ["提取"]),
        IntentSample("提取文本", {}, 0.85, ["提取"]),
        IntentSample("读取文字", {}, 0.85, ["读取"]),
        IntentSample("识别中文字", {}, 0.85, ["识别"]),
        IntentSample("识别英文字", {}, 0.85, ["识别"]),
        IntentSample("帮我识别文字", {}, 0.85, ["识别"]),
        IntentSample("请识别文字", {}, 0.85, ["识别"]),
        IntentSample("OCR文字识别", {}, 0.9, ["OCR"]),
        IntentSample("OCR识别文字", {}, 0.9, ["OCR"]),
        IntentSample("文字提取", {}, 0.85, ["提取"]),
        IntentSample("文本提取", {}, 0.85, ["提取"]),
        IntentSample("识别屏幕上的字", {}, 0.85, ["识别"]),
        IntentSample("识别图片上的字", {}, 0.85, ["识别"]),
        IntentSample("读取屏幕文字", {}, 0.85, ["读取"]),
        IntentSample("读取图片文字", {}, 0.85, ["读取"]),
        IntentSample("识别当前屏幕文字", {}, 0.85, ["识别"]),
        IntentSample("识别选定区域文字", {}, 0.85, ["识别"]),
        IntentSample("识别截图中的文字", {}, 0.85, ["识别"]),
    ])

    colloquial = [
        "识别一下", "OCR一下", "文字识别一下",
        "看看是什么字", "读一下文字", "认一下字",
        "帮我识别", "给我识别", "识别呗",
        "这是什么字", "那是什么字", "文字是什么",
        "把文字读出来", "把字认出来", "认字",
        "读一下屏幕", "读一下图片", "认一下屏幕",
        "识别下文字", "识别下屏幕", "识别下图片",
        "OCR一下屏幕", "OCR一下图片", "文字识别下",
    ]
    for text in colloquial:
        samples.append(IntentSample(text, {}, 0.7, [], is_colloquial=True))

    return samples


def create_record_start_samples() -> list[IntentSample]:
    samples = []

    types = ["屏幕", "视频", "操作", "桌面", "窗口", "全屏", "区域", "指定区域", "当前窗口", "选定区域"]
    for rtype in types:
        samples.append(IntentSample(f"开始录制{rtype}", {"type": rtype}, 0.9, ["录制"]))
        samples.append(IntentSample(f"录制{rtype}", {"type": rtype}, 0.9, ["录制"]))
        samples.append(IntentSample(f"录{rtype}", {"type": rtype}, 0.85, ["录制"]))
        samples.append(IntentSample(f"帮我录制{rtype}", {"type": rtype}, 0.85, ["录制"]))
        samples.append(IntentSample(f"请录制{rtype}", {"type": rtype}, 0.85, ["录制"]))

    samples.extend([
        IntentSample("开始录制", {}, 0.9, ["录制"]),
        IntentSample("开始录屏", {}, 0.9, ["录屏"]),
        IntentSample("开始录像", {}, 0.9, ["录像"]),
        IntentSample("录制", {}, 0.85, ["录制"]),
        IntentSample("录屏", {}, 0.85, ["录屏"]),
        IntentSample("录像", {}, 0.85, ["录像"]),
        IntentSample("屏幕录制", {}, 0.85, ["录制"]),
        IntentSample("视频录制", {}, 0.85, ["录制"]),
        IntentSample("帮我开始录制", {}, 0.85, ["录制"]),
        IntentSample("请开始录制", {}, 0.85, ["录制"]),
        IntentSample("开始录音", {}, 0.85, ["录音"]),
        IntentSample("录制音频", {}, 0.85, ["录音"]),
        IntentSample("开始录", {}, 0.85, ["录"]),
        IntentSample("录起来", {}, 0.85, ["录"]),
        IntentSample("开启录制", {}, 0.85, ["录制"]),
        IntentSample("启动录制", {}, 0.85, ["录制"]),
        IntentSample("启动录屏", {}, 0.85, ["录屏"]),
        IntentSample("启动录像", {}, 0.85, ["录像"]),
        IntentSample("开始屏幕录制", {}, 0.9, ["录制"]),
        IntentSample("开始视频录制", {}, 0.9, ["录制"]),
        IntentSample("开始桌面录制", {}, 0.9, ["录制"]),
        IntentSample("开始窗口录制", {}, 0.9, ["录制"]),
        IntentSample("开始全屏录制", {}, 0.9, ["录制"]),
        IntentSample("开始区域录制", {}, 0.9, ["录制"]),
    ])

    colloquial = [
        "录一下", "录个屏", "录个视频",
        "开始录", "录起来", "开录",
        "帮我录屏", "给我录像", "录屏呗",
        "录屏幕", "录桌面", "录窗口",
        "录全屏", "录区域", "录指定区域",
        "开始录吧", "录起来吧", "开录吧",
        "录个全屏", "录个区域", "录个窗口",
    ]
    for text in colloquial:
        samples.append(IntentSample(text, {}, 0.7, [], is_colloquial=True))

    return samples


def create_record_stop_samples() -> list[IntentSample]:
    samples = []

    samples.extend([
        IntentSample("停止录制", {}, 0.9, ["停止"]),
        IntentSample("停止录屏", {}, 0.9, ["停止"]),
        IntentSample("停止录像", {}, 0.9, ["停止"]),
        IntentSample("结束录制", {}, 0.9, ["结束"]),
        IntentSample("结束录屏", {}, 0.9, ["结束"]),
        IntentSample("结束录像", {}, 0.9, ["结束"]),
        IntentSample("暂停录制", {}, 0.85, ["暂停"]),
        IntentSample("暂停录屏", {}, 0.85, ["暂停"]),
        IntentSample("保存录制", {}, 0.85, ["保存"]),
        IntentSample("保存录屏", {}, 0.85, ["保存"]),
        IntentSample("帮我停止录制", {}, 0.85, ["停止"]),
        IntentSample("请停止录制", {}, 0.85, ["停止"]),
        IntentSample("停止录音", {}, 0.85, ["停止"]),
        IntentSample("结束录音", {}, 0.85, ["结束"]),
        IntentSample("停止屏幕录制", {}, 0.9, ["停止"]),
        IntentSample("停止视频录制", {}, 0.9, ["停止"]),
        IntentSample("结束屏幕录制", {}, 0.9, ["结束"]),
        IntentSample("结束视频录制", {}, 0.9, ["结束"]),
        IntentSample("停止全屏录制", {}, 0.9, ["停止"]),
        IntentSample("停止区域录制", {}, 0.9, ["停止"]),
        IntentSample("暂停屏幕录制", {}, 0.85, ["暂停"]),
        IntentSample("暂停视频录制", {}, 0.85, ["暂停"]),
        IntentSample("保存屏幕录制", {}, 0.85, ["保存"]),
        IntentSample("保存视频录制", {}, 0.85, ["保存"]),
        IntentSample("录制完成", {}, 0.85, ["完成"]),
        IntentSample("录屏完成", {}, 0.85, ["完成"]),
        IntentSample("录像完成", {}, 0.85, ["完成"]),
        IntentSample("停止录", {}, 0.85, ["停止"]),
        IntentSample("结束录", {}, 0.85, ["结束"]),
        IntentSample("暂停录", {}, 0.85, ["暂停"]),
        IntentSample("录制结束", {}, 0.9, ["结束"]),
        IntentSample("录屏结束", {}, 0.9, ["结束"]),
        IntentSample("录像结束", {}, 0.9, ["结束"]),
        IntentSample("录制停止", {}, 0.9, ["停止"]),
        IntentSample("录屏停止", {}, 0.9, ["停止"]),
        IntentSample("录像停止", {}, 0.9, ["停止"]),
        IntentSample("终止录制", {}, 0.85, ["终止"]),
        IntentSample("终止录屏", {}, 0.85, ["终止"]),
        IntentSample("终止录像", {}, 0.85, ["终止"]),
        IntentSample("中断录制", {}, 0.85, ["中断"]),
        IntentSample("中断录屏", {}, 0.85, ["中断"]),
        IntentSample("中断录像", {}, 0.85, ["中断"]),
        IntentSample("完成录制", {}, 0.85, ["完成"]),
        IntentSample("完成录屏", {}, 0.85, ["完成"]),
        IntentSample("完成录像", {}, 0.85, ["完成"]),
        IntentSample("录制好了", {}, 0.85, ["好了"]),
        IntentSample("录屏好了", {}, 0.85, ["好了"]),
        IntentSample("录像好了", {}, 0.85, ["好了"]),
        IntentSample("停止桌面录制", {}, 0.9, ["停止"]),
        IntentSample("停止窗口录制", {}, 0.9, ["停止"]),
        IntentSample("结束桌面录制", {}, 0.9, ["结束"]),
        IntentSample("结束窗口录制", {}, 0.9, ["结束"]),
    ])

    colloquial = [
        "停一下", "别录了", "录完了",
        "停止录", "结束录", "暂停录",
        "帮我停一下", "给我停一下", "停一下呗",
        "录制结束", "录屏结束", "录像结束",
        "保存视频", "保存录屏", "保存录像",
        "录好了", "录完了", "不录了",
        "停录", "停录屏", "停录像",
        "结束录屏", "结束录像", "停掉录制",
        "录制停一下", "录屏停一下", "录像停一下",
        "不录屏幕了", "不录视频了", "不录桌面了",
        "录制暂停", "录屏暂停", "录像暂停",
        "终止录", "中断录", "完成录",
    ]
    for text in colloquial:
        samples.append(IntentSample(text, {}, 0.7, [], is_colloquial=True))

    return samples


def create_system_info_samples() -> list[IntentSample]:
    samples = []

    info_types = [
        ("系统信息", "系统"), ("系统状态", "状态"), ("电脑信息", "电脑"),
        ("设备信息", "设备"), ("硬件信息", "硬件"), ("CPU信息", "CPU"),
        ("内存信息", "内存"), ("磁盘信息", "磁盘"), ("网络信息", "网络"),
        ("显卡信息", "显卡"), ("GPU信息", "GPU"), ("操作系统信息", "操作系统"),
        ("处理器信息", "处理器"), ("存储信息", "存储"), ("内存使用情况", "内存"),
        ("CPU使用情况", "CPU"), ("GPU使用情况", "GPU"), ("磁盘使用情况", "磁盘"),
        ("系统配置", "配置"), ("电脑配置", "配置"), ("硬件配置", "配置"),
        ("系统版本", "版本"), ("操作系统版本", "版本"), ("系统详情", "详情"),
    ]

    for text, keyword in info_types:
        samples.append(IntentSample(f"查看{text}", {}, 0.85, [keyword]))
        samples.append(IntentSample(f"显示{text}", {}, 0.85, [keyword]))
        samples.append(IntentSample(f"获取{text}", {}, 0.85, [keyword]))
        samples.append(IntentSample(f"{text}", {}, 0.8, [keyword]))
        samples.append(IntentSample(f"帮我查看{text}", {}, 0.8, [keyword]))

    samples.extend([
        IntentSample("系统信息", {}, 0.85, ["系统"]),
        IntentSample("电脑配置", {}, 0.85, ["配置"]),
        IntentSample("查看配置", {}, 0.85, ["配置"]),
        IntentSample("设备状态", {}, 0.85, ["设备"]),
        IntentSample("系统状态", {}, 0.85, ["系统"]),
        IntentSample("CPU使用率", {}, 0.85, ["CPU"]),
        IntentSample("内存使用率", {}, 0.85, ["内存"]),
        IntentSample("磁盘使用率", {}, 0.85, ["磁盘"]),
        IntentSample("GPU使用率", {}, 0.85, ["GPU"]),
        IntentSample("显存使用率", {}, 0.85, ["显存"]),
        IntentSample("帮我查看系统信息", {}, 0.85, ["系统"]),
        IntentSample("请显示系统信息", {}, 0.85, ["系统"]),
        IntentSample("CPU占用", {}, 0.85, ["CPU"]),
        IntentSample("内存占用", {}, 0.85, ["内存"]),
        IntentSample("磁盘占用", {}, 0.85, ["磁盘"]),
        IntentSample("GPU占用", {}, 0.85, ["GPU"]),
        IntentSample("显存占用", {}, 0.85, ["显存"]),
        IntentSample("系统资源", {}, 0.85, ["资源"]),
        IntentSample("电脑资源", {}, 0.85, ["资源"]),
        IntentSample("硬件资源", {}, 0.85, ["资源"]),
        IntentSample("系统性能", {}, 0.85, ["性能"]),
        IntentSample("电脑性能", {}, 0.85, ["性能"]),
    ])

    colloquial = [
        "看看电脑", "瞅瞅系统", "瞧瞧配置",
        "电脑怎么样", "系统怎么样", "配置怎么样",
        "CPU多少", "内存多少", "硬盘多少",
        "帮我看看", "给我看看", "看看呗",
        "电脑啥配置", "系统啥版本", "硬件啥情况",
        "CPU啥样", "内存啥样", "显卡啥样",
        "电脑啥型号", "系统啥系统", "硬件啥牌子",
    ]
    for text in colloquial:
        samples.append(IntentSample(text, {}, 0.7, [], is_colloquial=True))

    return samples


def create_process_list_samples() -> list[IntentSample]:
    samples = []

    templates = [
        "列出所有进程", "显示所有进程", "查看所有进程", "列举所有进程",
        "列出运行进程", "显示运行进程", "查看运行进程",
        "进程列表", "进程清单", "所有进程",
        "有什么进程", "有哪些进程", "进程都有什么",
        "运行中的进程", "活动的进程", "当前进程",
        "帮我列出进程", "帮我显示进程", "帮我查看进程",
        "请列出进程", "请显示进程", "请查看进程",
        "列出活动进程", "显示活动进程", "查看活动进程",
        "列出后台进程", "显示后台进程", "查看后台进程",
        "进程一览", "进程概览", "进程总览",
        "获取进程列表", "获取进程信息", "获取所有进程",
        "查看正在运行的进程", "显示正在运行的进程", "列出正在运行的进程",
        "进程状态", "进程详情", "进程情况",
        "列出系统进程", "显示系统进程", "查看系统进程",
        "列出用户进程", "显示用户进程", "查看用户进程",
        "列出应用进程", "显示应用进程", "查看应用进程",
        "进程信息列表", "进程状态列表", "进程详情列表",
    ]

    for text in templates:
        samples.append(IntentSample(text, {}, 0.85, ["进程", "列出"]))

    samples.extend([
        IntentSample("进程管理", {}, 0.8, ["进程"]),
        IntentSample("查看进程", {}, 0.85, ["进程"]),
        IntentSample("显示进程", {}, 0.85, ["进程"]),
        IntentSample("浏览进程", {}, 0.8, ["进程"]),
        IntentSample("当前有哪些进程", {}, 0.85, ["进程"]),
        IntentSample("现在有什么进程", {}, 0.85, ["进程"]),
        IntentSample("任务管理器", {}, 0.85, ["任务"]),
        IntentSample("打开任务管理器", {}, 0.85, ["任务"]),
        IntentSample("查看任务", {}, 0.85, ["任务"]),
        IntentSample("显示任务", {}, 0.85, ["任务"]),
        IntentSample("列出任务", {}, 0.85, ["任务"]),
        IntentSample("任务列表", {}, 0.85, ["任务"]),
        IntentSample("运行程序列表", {}, 0.85, ["程序"]),
        IntentSample("查看运行程序", {}, 0.85, ["程序"]),
        IntentSample("显示运行程序", {}, 0.85, ["程序"]),
        IntentSample("列出运行程序", {}, 0.85, ["程序"]),
        IntentSample("进程监控", {}, 0.85, ["监控"]),
        IntentSample("进程查看器", {}, 0.85, ["查看器"]),
        IntentSample("任务监控", {}, 0.85, ["监控"]),
        IntentSample("任务查看器", {}, 0.85, ["查看器"]),
        IntentSample("运行程序监控", {}, 0.85, ["监控"]),
        IntentSample("系统进程列表", {}, 0.85, ["进程"]),
        IntentSample("用户进程列表", {}, 0.85, ["进程"]),
        IntentSample("应用进程列表", {}, 0.85, ["进程"]),
        IntentSample("后台进程列表", {}, 0.85, ["进程"]),
        IntentSample("前台进程列表", {}, 0.85, ["进程"]),
    ])

    colloquial = [
        "看看进程", "瞅瞅进程", "瞧瞧进程",
        "进程呢", "都有啥进程", "进程列表看看",
        "帮我看看进程", "给我看看进程", "看看有什么进程",
        "运行的程序", "活动的程序", "正在运行的",
        "进程都有啥", "啥进程", "哪些进程",
        "进程一览表", "进程清单看看", "进程一览看看",
        "看看任务", "瞅瞅任务", "任务列表看看",
        "任务都有啥", "啥任务", "哪些任务",
        "看看运行程序", "瞅瞅运行程序", "运行程序看看",
        "程序列表", "程序清单", "运行程序一览",
    ]
    for text in colloquial:
        samples.append(IntentSample(text, {}, 0.7, [], is_colloquial=True))

    return samples


def create_process_kill_samples() -> list[IntentSample]:
    samples = []

    verbs = ["结束", "终止", "杀掉", "关闭", "停止", "结束掉", "终止掉"]

    for verb in verbs:
        samples.append(IntentSample(f"{verb}进程", {}, 0.85, ["结束", "终止"]))
        samples.append(IntentSample(f"帮我{verb}进程", {}, 0.9, ["结束", "终止"]))

    process_names = ["chrome", "python", "node", "java", "vscode", "wechat", "qq"]
    for verb in verbs[:4]:
        for pname in process_names:
            samples.append(IntentSample(f"{verb}{pname}进程", {"process_name": pname}, 0.9, [pname]))
            samples.append(IntentSample(f"把{pname}{verb}", {"process_name": pname}, 0.9, [pname]))

    samples.extend([
        IntentSample("强制结束进程", {}, 0.85, ["强制"]),
        IntentSample("强制终止进程", {}, 0.85, ["强制"]),
        IntentSample("杀死进程", {}, 0.85, ["杀死"]),
        IntentSample("kill进程", {}, 0.85, ["kill"]),
        IntentSample("结束无响应进程", {}, 0.85, ["无响应"]),
        IntentSample("结束卡死的程序", {}, 0.85, ["卡死"]),
    ])

    colloquial = [
        "杀进程", "干掉进程", "结束掉", "终止掉",
        "把进程杀了", "把程序关了", "进程结束",
        "帮我杀掉", "给我结束", "结束呗",
        "这个进程不要了", "那个进程结束掉", "进程杀掉",
        "程序卡了", "程序没响应", "强制关闭",
    ]
    for text in colloquial:
        samples.append(IntentSample(text, {}, 0.7, [], is_colloquial=True))

    return samples


def create_clipboard_copy_samples() -> list[IntentSample]:
    samples = []

    verbs = ["复制", "拷贝", "copy", "复制一下", "拷贝一下", "复制一份", "拷贝一份"]
    nouns = ["内容", "文本", "文字", "代码", "选中的内容", "当前内容", "选中文字",
             "这段文字", "这段代码", "这个内容", "那个内容", "全部内容", "当前文本"]

    for verb in verbs:
        for noun in nouns:
            samples.append(IntentSample(f"{verb}{noun}", {}, 0.85, ["复制", "拷贝"]))
            samples.append(IntentSample(f"帮我{verb}{noun}", {}, 0.9, ["复制", "拷贝"]))
            samples.append(IntentSample(f"请{verb}{noun}", {}, 0.9, ["复制", "拷贝"]))

    samples.extend([
        IntentSample("复制", {}, 0.9, ["复制"]),
        IntentSample("拷贝", {}, 0.9, ["拷贝"]),
        IntentSample("copy", {}, 0.9, ["copy"]),
        IntentSample("复制到剪贴板", {}, 0.85, ["剪贴板"]),
        IntentSample("拷贝到剪贴板", {}, 0.85, ["剪贴板"]),
        IntentSample("复制选中内容", {}, 0.85, ["选中"]),
        IntentSample("复制当前行", {}, 0.85, ["当前行"]),
        IntentSample("复制全部", {}, 0.85, ["全部"]),
        IntentSample("Ctrl+C", {}, 0.85, ["Ctrl+C"]),
        IntentSample("复制这一行", {}, 0.85, ["行"]),
        IntentSample("复制这几行", {}, 0.85, ["行"]),
        IntentSample("复制选区", {}, 0.85, ["选区"]),
        IntentSample("复制选中部分", {}, 0.85, ["选中"]),
        IntentSample("复制整行", {}, 0.85, ["行"]),
        IntentSample("复制整段", {}, 0.85, ["段"]),
        IntentSample("复制全文", {}, 0.85, ["全文"]),
        IntentSample("复制所有", {}, 0.85, ["所有"]),
        IntentSample("复制文件内容", {}, 0.85, ["文件"]),
        IntentSample("复制代码片段", {}, 0.85, ["代码"]),
        IntentSample("复制文本内容", {}, 0.85, ["文本"]),
    ])

    colloquial = [
        "复制一下", "拷贝一下", "copy一下",
        "帮我复制", "给我拷贝", "复制呗",
        "把这个复制了", "把那个拷贝了", "复制它",
        "复制这段", "拷贝这块", "copy这个",
        "复制下来", "拷贝下来", "copy下来",
        "复制过去", "拷贝过去", "copy过去",
        "复制一份", "拷贝一份", "copy一份",
    ]
    for text in colloquial:
        samples.append(IntentSample(text, {}, 0.7, [], is_colloquial=True))

    return samples


def create_clipboard_paste_samples() -> list[IntentSample]:
    samples = []

    verbs = ["粘贴", "贴上", "paste", "粘贴一下", "贴上一下", "粘贴一份", "贴上一份"]
    nouns = ["内容", "文本", "文字", "代码", "剪贴板内容", "复制的内容", "剪贴板文字",
             "这段文字", "这段代码", "这个内容", "那个内容", "全部内容", "当前文本"]

    for verb in verbs:
        for noun in nouns:
            samples.append(IntentSample(f"{verb}{noun}", {}, 0.85, ["粘贴", "贴上"]))
            samples.append(IntentSample(f"帮我{verb}{noun}", {}, 0.9, ["粘贴", "贴上"]))
            samples.append(IntentSample(f"请{verb}{noun}", {}, 0.9, ["粘贴", "贴上"]))

    samples.extend([
        IntentSample("粘贴", {}, 0.9, ["粘贴"]),
        IntentSample("贴上", {}, 0.9, ["贴上"]),
        IntentSample("paste", {}, 0.9, ["paste"]),
        IntentSample("粘贴内容", {}, 0.85, ["粘贴"]),
        IntentSample("粘贴文本", {}, 0.85, ["粘贴"]),
        IntentSample("粘贴代码", {}, 0.85, ["粘贴"]),
        IntentSample("从剪贴板粘贴", {}, 0.85, ["剪贴板"]),
        IntentSample("粘贴到这里", {}, 0.85, ["这里"]),
        IntentSample("Ctrl+V", {}, 0.85, ["Ctrl+V"]),
        IntentSample("粘贴到当前位置", {}, 0.85, ["当前位置"]),
        IntentSample("粘贴到光标处", {}, 0.85, ["光标"]),
        IntentSample("粘贴到末尾", {}, 0.85, ["末尾"]),
        IntentSample("粘贴到开头", {}, 0.85, ["开头"]),
        IntentSample("粘贴到下一行", {}, 0.85, ["下一行"]),
        IntentSample("粘贴到上一行", {}, 0.85, ["上一行"]),
        IntentSample("粘贴选中内容", {}, 0.85, ["选中"]),
        IntentSample("粘贴全部", {}, 0.85, ["全部"]),
        IntentSample("粘贴所有", {}, 0.85, ["所有"]),
        IntentSample("粘贴文件内容", {}, 0.85, ["文件"]),
        IntentSample("粘贴代码片段", {}, 0.85, ["代码"]),
        IntentSample("粘贴文本内容", {}, 0.85, ["文本"]),
    ])

    colloquial = [
        "粘贴一下", "贴一下", "paste一下",
        "帮我粘贴", "给我贴上", "粘贴呗",
        "把这个粘贴了", "把那个贴上", "粘贴它",
        "贴上来", "粘过来", "paste这个",
        "粘贴下来", "贴上下来", "paste下来",
        "粘贴过去", "贴上过去", "paste过去",
        "粘贴一份", "贴上一份", "paste一份",
    ]
    for text in colloquial:
        samples.append(IntentSample(text, {}, 0.7, [], is_colloquial=True))

    return samples


def create_search_web_samples() -> list[IntentSample]:
    samples = []

    verbs = ["搜索", "查找", "查询", "搜一下", "查一下", "搜索一下"]

    for verb in verbs:
        for term in SEARCH_TERMS:
            samples.append(IntentSample(f"{verb}{term}", {"query": term}, 0.9, [term]))
            samples.append(IntentSample(f"帮我{verb}{term}", {"query": term}, 0.85, [term]))
            samples.append(IntentSample(f"请{verb}{term}", {"query": term}, 0.85, [term]))

    engines = ["百度", "谷歌", "必应", "Google", "Bing"]
    for engine in engines:
        for term in SEARCH_TERMS[:10]:
            samples.append(IntentSample(f"用{engine}搜索{term}", {"query": term, "engine": engine}, 0.9, [term]))

    samples.extend([
        IntentSample("搜索", {}, 0.85, ["搜索"]),
        IntentSample("网上搜索", {}, 0.85, ["搜索"]),
        IntentSample("网络搜索", {}, 0.85, ["搜索"]),
        IntentSample("搜索引擎", {}, 0.8, ["搜索"]),
        IntentSample("帮我搜索", {}, 0.85, ["搜索"]),
        IntentSample("请搜索", {}, 0.85, ["搜索"]),
        IntentSample("搜索一下", {}, 0.85, ["搜索"]),
        IntentSample("查一下", {}, 0.85, ["查"]),
        IntentSample("找一下", {}, 0.85, ["找"]),
    ])

    colloquial = [
        "搜一下", "查一下", "找一下",
        "帮我搜", "给我查", "搜搜看",
        "百度一下", "谷歌一下", "搜搜",
        "网上查查", "网上找找", "搜索看看",
        "搜个东西", "查个东西", "找个东西",
    ]
    for text in colloquial:
        samples.append(IntentSample(text, {}, 0.7, [], is_colloquial=True))

    return samples


INTENT_TRAINING_DATA_EXPANDED: dict[str, dict[str, Any]] = {
    "file_create": {
        "samples": create_file_create_samples(),
        "keywords_weight": {"创建": 0.3, "新建": 0.3, "生成": 0.25, "建立": 0.2},
    },
    "file_read": {
        "samples": create_file_read_samples(),
        "keywords_weight": {"读取": 0.3, "查看": 0.3, "打开": 0.25, "阅读": 0.2},
    },
    "file_write": {
        "samples": create_file_write_samples(),
        "keywords_weight": {"写入": 0.3, "修改": 0.3, "编辑": 0.25, "更新": 0.2},
    },
    "file_delete": {
        "samples": create_file_delete_samples(),
        "keywords_weight": {"删除": 0.35, "移除": 0.3, "删掉": 0.25},
    },
    "file_list": {
        "samples": create_file_list_samples(),
        "keywords_weight": {"列出": 0.3, "显示": 0.25, "查看": 0.2},
    },
    "file_copy": {
        "samples": create_file_copy_samples(),
        "keywords_weight": {"复制": 0.35, "拷贝": 0.3, "copy": 0.25},
    },
    "file_move": {
        "samples": create_file_move_samples(),
        "keywords_weight": {"移动": 0.35, "转移": 0.3, "搬移": 0.25},
    },
    "file_rename": {
        "samples": create_file_rename_samples(),
        "keywords_weight": {"重命名": 0.35, "改名": 0.3},
    },
    "app_open": {
        "samples": create_app_open_samples(),
        "keywords_weight": {"打开": 0.3, "启动": 0.3, "运行": 0.25},
    },
    "app_close": {
        "samples": create_app_close_samples(),
        "keywords_weight": {"关闭": 0.35, "关掉": 0.3, "退出": 0.25},
    },
    "url_open": {
        "samples": create_url_open_samples(),
        "keywords_weight": {"打开": 0.3, "访问": 0.3, "跳转": 0.2},
    },
    "screenshot": {
        "samples": create_screenshot_samples(),
        "keywords_weight": {"截图": 0.4, "截屏": 0.35, "抓图": 0.25},
    },
    "mouse_click": {
        "samples": create_mouse_click_samples(),
        "keywords_weight": {"点击": 0.35, "单击": 0.3, "双击": 0.25},
    },
    "mouse_move": {
        "samples": create_mouse_move_samples(),
        "keywords_weight": {"移动": 0.35, "鼠标": 0.2},
    },
    "mouse_scroll": {
        "samples": create_mouse_scroll_samples(),
        "keywords_weight": {"滚动": 0.4, "滚轮": 0.3},
    },
    "keyboard_type": {
        "samples": create_keyboard_type_samples(),
        "keywords_weight": {"输入": 0.35, "打字": 0.3, "键入": 0.25},
    },
    "keyboard_press": {
        "samples": create_keyboard_press_samples(),
        "keywords_weight": {"按下": 0.3, "按": 0.3, "快捷键": 0.2},
    },
    "window_list": {
        "samples": create_window_list_samples(),
        "keywords_weight": {"窗口": 0.3, "列出": 0.25},
    },
    "window_activate": {
        "samples": create_window_activate_samples(),
        "keywords_weight": {"切换": 0.35, "激活": 0.3},
    },
    "window_close": {
        "samples": create_window_close_samples(),
        "keywords_weight": {"关闭": 0.35, "窗口": 0.2},
    },
    "ocr_recognize": {
        "samples": create_ocr_recognize_samples(),
        "keywords_weight": {"识别": 0.35, "OCR": 0.3, "文字": 0.2},
    },
    "record_start": {
        "samples": create_record_start_samples(),
        "keywords_weight": {"录制": 0.35, "录屏": 0.3, "开始": 0.2},
    },
    "record_stop": {
        "samples": create_record_stop_samples(),
        "keywords_weight": {"停止": 0.35, "结束": 0.3, "录制": 0.2},
    },
    "system_info": {
        "samples": create_system_info_samples(),
        "keywords_weight": {"系统": 0.3, "信息": 0.2, "配置": 0.2},
    },
    "process_list": {
        "samples": create_process_list_samples(),
        "keywords_weight": {"进程": 0.35, "列出": 0.25},
    },
    "process_kill": {
        "samples": create_process_kill_samples(),
        "keywords_weight": {"结束": 0.3, "终止": 0.3, "进程": 0.2},
    },
    "clipboard_copy": {
        "samples": create_clipboard_copy_samples(),
        "keywords_weight": {"复制": 0.4, "拷贝": 0.35},
    },
    "clipboard_paste": {
        "samples": create_clipboard_paste_samples(),
        "keywords_weight": {"粘贴": 0.4, "贴上": 0.35},
    },
    "search_web": {
        "samples": create_search_web_samples(),
        "keywords_weight": {"搜索": 0.4, "查找": 0.3, "查询": 0.25},
    },
}


def get_all_samples() -> list[tuple]:
    all_samples = []
    for intent_name, data in INTENT_TRAINING_DATA_EXPANDED.items():
        for sample in data.get("samples", []):
            all_samples.append((intent_name, sample))
    return all_samples


def get_all_intent_names() -> list[str]:
    return list(INTENT_TRAINING_DATA_EXPANDED.keys())


def get_intent_stats() -> dict[str, Any]:
    stats = {}
    for intent_name, data in INTENT_TRAINING_DATA_EXPANDED.items():
        samples = data.get("samples", [])
        colloquial_count = sum(1 for s in samples if s.is_colloquial)
        stats[intent_name] = {
            "total": len(samples),
            "standard": len(samples) - colloquial_count,
            "colloquial": colloquial_count,
        }
    return stats


if __name__ == "__main__":
    stats = get_intent_stats()
    total = sum(s["total"] for s in stats.values())

    print("=" * 60)
    print("  扩充后的训练数据统计")
    print("=" * 60)
    print(f"总样本数: {total}")
    print(f"意图类型数: {len(stats)}")
    print()

    for intent, stat in stats.items():
        print(f"  {intent}: {stat['total']} (标准: {stat['standard']}, 口语: {stat['colloquial']})")
