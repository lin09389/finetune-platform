"""
BIO 标签生成器
将训练数据中的参数转换为 BIO 序列标注格式
用于训练 BERT 参数抽取模型
"""
import re
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
from enum import Enum


class ParamTag(str, Enum):
    O = "O"
    B_FILE_PATH = "B-FILE_PATH"
    I_FILE_PATH = "I-FILE_PATH"
    B_APP_NAME = "B-APP_NAME"
    I_APP_NAME = "I-APP_NAME"
    B_URL = "B-URL"
    I_URL = "I-URL"
    B_CONTENT = "B-CONTENT"
    I_CONTENT = "I-CONTENT"
    B_DIRECTORY = "B-DIRECTORY"
    I_DIRECTORY = "I-DIRECTORY"
    B_TEXT = "B-TEXT"
    I_TEXT = "I-TEXT"
    B_NUMBER = "B-NUMBER"
    I_NUMBER = "I-NUMBER"
    B_QUERY = "B-QUERY"
    I_QUERY = "I-QUERY"
    B_KEY = "B-KEY"
    I_KEY = "I-KEY"
    B_PROCESS_NAME = "B-PROCESS_NAME"
    I_PROCESS_NAME = "I-PROCESS_NAME"
    B_DESTINATION = "B-DESTINATION"
    I_DESTINATION = "I-DESTINATION"
    B_NEW_NAME = "B-NEW_NAME"
    I_NEW_NAME = "I-NEW_NAME"
    B_POSITION = "B-POSITION"
    I_POSITION = "I-POSITION"
    B_BUTTON = "B-BUTTON"
    I_BUTTON = "I-BUTTON"
    B_DIRECTION = "B-DIRECTION"
    I_DIRECTION = "I-DIRECTION"
    B_AREA = "B-AREA"
    I_AREA = "I-AREA"
    B_TYPE = "B-TYPE"
    I_TYPE = "I-TYPE"


PARAM_TYPE_TO_TAG = {
    "file_path": "FILE_PATH",
    "app_name": "APP_NAME",
    "url": "URL",
    "content": "CONTENT",
    "directory": "DIRECTORY",
    "text": "TEXT",
    "number": "NUMBER",
    "query": "QUERY",
    "key": "KEY",
    "process_name": "PROCESS_NAME",
    "destination": "DESTINATION",
    "new_name": "NEW_NAME",
    "position": "POSITION",
    "button": "BUTTON",
    "direction": "DIRECTION",
    "area": "AREA",
    "type": "TYPE",
    "amount": "NUMBER",
    "engine": "TEXT",
}


@dataclass
class TokenLabel:
    token: str
    label: str
    start: int
    end: int


@dataclass
class BIOAnnotatedSample:
    text: str
    intent: str
    tokens: List[str]
    labels: List[str]
    char_labels: List[str]
    params: Dict[str, Any]


def get_all_param_tags() -> List[str]:
    tags = ["O"]
    for tag in ParamTag:
        if tag != ParamTag.O:
            tags.append(tag.value)
    return tags


def get_param_tag_map() -> Dict[str, int]:
    tags = get_all_param_tags()
    return {tag: i for i, tag in enumerate(tags)}


def find_param_spans(text: str, params: Dict[str, Any]) -> List[Tuple[int, int, str]]:
    spans = []
    
    for param_type, param_value in params.items():
        if not param_value or not isinstance(param_value, str):
            continue
        
        tag_type = PARAM_TYPE_TO_TAG.get(param_type, param_type.upper())
        
        value_str = str(param_value)
        
        start = 0
        while True:
            pos = text.find(value_str, start)
            if pos == -1:
                break
            
            end = pos + len(value_str)
            spans.append((pos, end, tag_type))
            start = end
    
    spans.sort(key=lambda x: x[0])
    
    merged_spans = []
    for span in spans:
        if merged_spans and span[0] < merged_spans[-1][1]:
            continue
        merged_spans.append(span)
    
    return merged_spans


def tokenize_with_spans(text: str) -> List[Tuple[str, int, int]]:
    tokens = []
    pattern = r'[\w\u4e00-\u9fff]+|[^\w\s\u4e00-\u9fff]'
    
    for match in re.finditer(pattern, text):
        token = match.group()
        start = match.start()
        end = match.end()
        tokens.append((token, start, end))
    
    return tokens


def generate_bio_labels(
    text: str, 
    params: Dict[str, Any]
) -> Tuple[List[str], List[Tuple[str, int, int]]]:
    tokens_with_spans = tokenize_with_spans(text)
    labels = ["O"] * len(tokens_with_spans)
    
    spans = find_param_spans(text, params)
    
    for span_start, span_end, tag_type in spans:
        first_token = True
        for i, (token, tok_start, tok_end) in enumerate(tokens_with_spans):
            if tok_start >= span_start and tok_end <= span_end:
                if first_token:
                    labels[i] = f"B-{tag_type}"
                    first_token = False
                else:
                    labels[i] = f"I-{tag_type}"
            elif tok_start < span_end and tok_end > span_start:
                if first_token:
                    labels[i] = f"B-{tag_type}"
                    first_token = False
                else:
                    labels[i] = f"I-{tag_type}"
    
    return labels, tokens_with_spans


def annotate_sample(
    text: str, 
    intent: str, 
    params: Dict[str, Any]
) -> BIOAnnotatedSample:
    labels, tokens_with_spans = generate_bio_labels(text, params)
    tokens = [t[0] for t in tokens_with_spans]
    
    char_labels = generate_char_level_labels(text, params)
    
    return BIOAnnotatedSample(
        text=text,
        intent=intent,
        tokens=tokens,
        labels=labels,
        char_labels=char_labels,
        params=params
    )


def generate_char_level_labels(text: str, params: Dict[str, Any]) -> List[str]:
    spans = find_param_spans(text, params)
    
    char_labels = ['O'] * len(text)
    
    for span_start, span_end, tag_type in spans:
        for i in range(span_start, min(span_end, len(text))):
            if i == span_start:
                char_labels[i] = f"B-{tag_type}"
            else:
                char_labels[i] = f"I-{tag_type}"
    
    return char_labels


def generate_synthetic_params(text: str, intent: str) -> Dict[str, Any]:
    params = {}
    
    file_patterns = [
        r'([a-zA-Z_][a-zA-Z0-9_]*\.(py|js|ts|html|css|json|yaml|yml|xml|md|txt|log|csv|xlsx))',
        r'([a-zA-Z_][a-zA-Z0-9_]*\.[a-zA-Z]{1,4})',
    ]
    
    for pattern in file_patterns:
        matches = re.findall(pattern, text)
        for match in matches:
            file_name = match[0] if isinstance(match, tuple) else match
            if file_name and len(file_name) > 2:
                params['file_path'] = file_name
                break
        if 'file_path' in params:
            break
    
    app_patterns = [
        r'(VS\s*Code|Visual\s*Studio\s*Code|VSCode|Chrome|Firefox|Edge|Safari|Opera|PyCharm|IntelliJ|WebStorm|Sublime|Atom|Notepad\+\+|Vim|Neovim|Terminal|PowerShell|CMD|微信|QQ|钉钉|飞书|Word|Excel|PowerPoint|Photoshop|Figma|Docker|Postman)',
        r'打开\s*([a-zA-Z\u4e00-\u9fff]+)',
        r'启动\s*([a-zA-Z\u4e00-\u9fff]+)',
        r'关闭\s*([a-zA-Z\u4e00-\u9fff]+)',
    ]
    
    for pattern in app_patterns:
        matches = re.findall(pattern, text)
        for match in matches:
            app_name = match if isinstance(match, str) else match[0]
            if app_name and len(app_name) > 1:
                params['app_name'] = app_name
                break
        if 'app_name' in params:
            break
    
    url_pattern = r'(https?://[^\s]+)'
    url_matches = re.findall(url_pattern, text)
    if url_matches:
        params['url'] = url_matches[0]
    
    number_pattern = r'\b(\d+(?:\.\d+)?)\b'
    number_matches = re.findall(number_pattern, text)
    if number_matches:
        for num in number_matches:
            if float(num) > 0:
                params['number'] = num
                break
    
    if '搜索' in text or '查找' in text or '查询' in text:
        search_patterns = [
            r'搜索\s*([a-zA-Z\u4e00-\u9fff\u0030-\u0039]+)',
            r'查找\s*([a-zA-Z\u4e00-\u9fff\u0030-\u0039]+)',
            r'查询\s*([a-zA-Z\u4e00-\u9fff\u0030-\u0039]+)',
            r'搜\s*([a-zA-Z\u4e00-\u9fff\u0030-\u0039]+)',
        ]
        for pattern in search_patterns:
            matches = re.findall(pattern, text)
            if matches:
                params['query'] = matches[0]
                break
    
    return params


def create_annotated_dataset(
    samples: List[Tuple[str, Any]], 
    auto_generate_params: bool = True
) -> List[BIOAnnotatedSample]:
    annotated = []
    
    for intent_name, sample in samples:
        text = sample.text
        params = sample.params_template.copy() if hasattr(sample, 'params_template') else {}
        
        if auto_generate_params and not params:
            params = generate_synthetic_params(text, intent_name)
        
        annotated_sample = annotate_sample(text, intent_name, params)
        annotated.append(annotated_sample)
    
    return annotated


def validate_bio_labels(labels: List[str]) -> bool:
    for i, label in enumerate(labels):
        if label.startswith("I-"):
            tag_type = label[2:]
            if i == 0:
                return False
            prev_label = labels[i - 1]
            if not (prev_label == f"B-{tag_type}" or prev_label == f"I-{tag_type}"):
                return False
    return True


def bio_labels_to_spans(tokens: List[str], labels: List[str]) -> List[Dict[str, Any]]:
    spans = []
    current_entity = None
    current_tokens = []
    current_start = None
    
    for i, (token, label) in enumerate(zip(tokens, labels)):
        if label.startswith("B-"):
            if current_entity and current_tokens:
                spans.append({
                    "type": current_entity,
                    "tokens": current_tokens,
                    "text": "".join(current_tokens),
                    "start": current_start,
                    "end": i - 1
                })
            
            current_entity = label[2:]
            current_tokens = [token]
            current_start = i
            
        elif label.startswith("I-") and current_entity == label[2:]:
            current_tokens.append(token)
            
        else:
            if current_entity and current_tokens:
                spans.append({
                    "type": current_entity,
                    "tokens": current_tokens,
                    "text": "".join(current_tokens),
                    "start": current_start,
                    "end": i - 1
                })
            current_entity = None
            current_tokens = []
            current_start = None
    
    if current_entity and current_tokens:
        spans.append({
            "type": current_entity,
            "tokens": current_tokens,
            "text": "".join(current_tokens),
            "start": current_start,
            "end": len(tokens) - 1
        })
    
    return spans


if __name__ == "__main__":
    from training_data_expanded import get_all_samples, get_all_intent_names
    
    print("=" * 60)
    print("  BIO 标签生成器测试")
    print("=" * 60)
    
    samples = get_all_samples()
    print(f"\n总样本数: {len(samples)}")
    
    test_samples = [
        ("创建一个test.py文件", "file_create", {"file_path": "test.py"}),
        ("读取config.json文件", "file_read", {"file_path": "config.json"}),
        ("打开VS Code", "app_open", {"app_name": "VS Code"}),
        ("搜索Python教程", "search_web", {"query": "Python教程"}),
        ("帮我搜索一下React开发", "search_web", {"query": "React开发"}),
    ]
    
    print("\n测试 BIO 标签生成:")
    for text, intent, params in test_samples:
        annotated = annotate_sample(text, intent, params)
        print(f"\n文本: {text}")
        print(f"意图: {intent}")
        print(f"参数: {params}")
        print(f"Tokens: {annotated.tokens}")
        print(f"Labels: {annotated.labels}")
        
        spans = bio_labels_to_spans(annotated.tokens, annotated.labels)
        print(f"提取的实体: {spans}")
        
        is_valid = validate_bio_labels(annotated.labels)
        print(f"标签有效性: {'✓' if is_valid else '✗'}")
    
    print("\n" + "=" * 60)
    print("  生成完整标注数据集")
    print("=" * 60)
    
    annotated_dataset = create_annotated_dataset(samples[:100])
    
    entity_count = 0
    for sample in annotated_dataset:
        spans = bio_labels_to_spans(sample.tokens, sample.labels)
        entity_count += len(spans)
    
    print(f"\n标注样本数: {len(annotated_dataset)}")
    print(f"实体总数: {entity_count}")
    print(f"平均每样本实体数: {entity_count / len(annotated_dataset):.2f}")
    
    tag_map = get_param_tag_map()
    print(f"\n参数标签数: {len(tag_map)}")
    print(f"标签列表: {list(tag_map.keys())}")
