"""
BERT 意图分类模型加载器
加载训练好的模型进行预测
支持意图分类和参数抽取（序列标注）
"""
import json
import logging
import os
import sys
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

MODEL_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'models', 'intent_bert')
BERT_CACHE_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'models', 'modelscope_cache', 'tiansz', 'bert-base-chinese')


class ParamTag(str, Enum):
    """参数标签（BIO 标注）"""
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


PARAM_TAG_MAP = {
    "FILE_PATH": "file_path",
    "APP_NAME": "app_name",
    "URL": "url",
    "CONTENT": "content",
    "DIRECTORY": "directory",
    "TEXT": "text",
    "NUMBER": "number",
    "QUERY": "query",
    "KEY": "key",
    "PROCESS_NAME": "process_name",
    "DESTINATION": "destination",
    "NEW_NAME": "new_name",
    "POSITION": "position",
    "BUTTON": "button",
    "DIRECTION": "direction",
    "AREA": "area",
    "TYPE": "type",
}


@dataclass
class BERTConfig:
    model_dir: str = MODEL_DIR
    max_length: int = 128
    device: str = "cuda"
    enable_param_extraction: bool = True


@dataclass
class ParamExtraction:
    """参数提取结果"""
    param_type: str
    value: str
    start: int
    end: int
    confidence: float = 1.0


@dataclass
class PredictionResult:
    """预测结果（包含意图和参数）"""
    intent: str
    confidence: float
    params: dict[str, Any] = field(default_factory=dict)
    param_extractions: list[ParamExtraction] = field(default_factory=list)


class BERTIntentClassifier:
    """BERT 意图分类器（支持参数抽取）"""

    _instance = None
    _initialized = False

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, config: BERTConfig | None = None):
        if self._initialized:
            return

        self.config = config or BERTConfig()
        self.model = None
        self.tokenizer = None
        self.label_map = None
        self.id_to_label = None
        self.param_tag_map = None
        self.id_to_param_tag = None
        self.device = self.config.device

        self._load_model()
        self._initialized = True

    def _load_model(self):
        """加载模型"""
        try:
            import torch
            from torch import nn
            from transformers import BertModel, BertTokenizer

            model_dir = self.config.model_dir

            if not os.path.exists(model_dir):
                logger.warning(f"模型目录不存在: {model_dir}")
                return

            label_map_path = os.path.join(model_dir, 'label_map.json')
            if os.path.exists(label_map_path):
                with open(label_map_path, encoding='utf-8') as f:
                    self.label_map = json.load(f)
                self.id_to_label = {int(k): v for k, v in self.label_map.items()}
                logger.info(f"加载标签映射: {len(self.label_map)} 个意图")

            param_tag_map_path = os.path.join(model_dir, 'param_tag_map.json')
            if os.path.exists(param_tag_map_path):
                with open(param_tag_map_path, encoding='utf-8') as f:
                    loaded_map = json.load(f)

                first_key = next(iter(loaded_map.keys()))
                if first_key.isdigit() or (isinstance(first_key, int)):
                    self.param_tag_map = {int(k): v for k, v in loaded_map.items()}
                    self.id_to_param_tag = self.param_tag_map
                else:
                    self.param_tag_map = loaded_map
                    self.id_to_param_tag = {v: k for k, v in loaded_map.items()}

                logger.info(f"加载参数标签映射: {len(self.param_tag_map)} 个标签")
            else:
                self.param_tag_map = {i: tag.value for i, tag in enumerate(ParamTag)}
                self.id_to_param_tag = {i: tag.value for i, tag in enumerate(ParamTag)}
                logger.info("使用默认参数标签映射")

            tokenizer_path = model_dir if os.path.exists(os.path.join(model_dir, 'vocab.txt')) else BERT_CACHE_DIR
            self.tokenizer = BertTokenizer.from_pretrained(tokenizer_path)
            logger.info(f"加载分词器: {tokenizer_path}")

            bert_model_path = BERT_CACHE_DIR if os.path.exists(BERT_CACHE_DIR) else model_dir
            bert_model = BertModel.from_pretrained(bert_model_path)
            logger.info(f"加载 BERT 模型: {bert_model_path}")

            num_labels = len(self.label_map) if self.label_map else 29
            num_param_tags = len(self.param_tag_map) if self.param_tag_map else len(ParamTag)

            class IntentClassifierWithParamExtraction(nn.Module):
                def __init__(self, bert_model, num_labels, num_param_tags, dropout=0.1):
                    super().__init__()
                    self.bert = bert_model
                    self.dropout = nn.Dropout(dropout)
                    self.intent_classifier = nn.Linear(bert_model.config.hidden_size, num_labels)
                    self.param_tagger = nn.Linear(bert_model.config.hidden_size, num_param_tags)

                def forward(self, input_ids, attention_mask):
                    outputs = self.bert(input_ids=input_ids, attention_mask=attention_mask)
                    sequence_output = outputs.last_hidden_state
                    pooled_output = outputs.pooler_output

                    pooled_output = self.dropout(pooled_output)
                    sequence_output = self.dropout(sequence_output)

                    intent_logits = self.intent_classifier(pooled_output)
                    param_logits = self.param_tagger(sequence_output)

                    return intent_logits, param_logits

            self.model = IntentClassifierWithParamExtraction(bert_model, num_labels, num_param_tags)

            model_path = os.path.join(model_dir, 'model.pt')
            if os.path.exists(model_path):
                state_dict = torch.load(model_path, map_location='cpu')
                self.model.load_state_dict(state_dict)
                logger.info(f"加载模型权重: {model_path}")
            else:
                logger.warning(f"模型权重文件不存在: {model_path}")
                return

            if torch.cuda.is_available() and self.device == "cuda":
                self.model.to(self.device)
                logger.info("模型已加载到 GPU")
            else:
                self.device = "cpu"
                self.model.to(self.device)
                logger.info("模型已加载到 CPU")

            self.model.eval()
            logger.info("BERT 意图分类器加载完成（支持参数抽取）")

        except Exception as e:
            logger.error(f"加载 BERT 模型失败: {e}")
            import traceback
            traceback.print_exc()
            self.model = None
            self.tokenizer = None

    def is_loaded(self) -> bool:
        """检查模型是否已加载"""
        return self.model is not None and self.tokenizer is not None

    def predict(self, text: str) -> tuple[str, float]:
        """预测意图"""
        if not self.is_loaded():
            return "unknown", 0.0

        try:
            import torch

            self.model.eval()

            encoding = self.tokenizer(
                text,
                max_length=self.config.max_length,
                padding='max_length',
                truncation=True,
                return_tensors='pt'
            )

            input_ids = encoding['input_ids'].to(self.device)
            attention_mask = encoding['attention_mask'].to(self.device)

            with torch.no_grad():
                intent_logits, _ = self.model(input_ids=input_ids, attention_mask=attention_mask)
                probs = torch.softmax(intent_logits, dim=-1)
                prediction = torch.argmax(probs, dim=-1)
                confidence = probs[0, prediction].item()

            pred_idx = prediction.item()
            intent_name = self.id_to_label.get(pred_idx, "unknown")

            return intent_name, confidence

        except Exception as e:
            logger.error(f"预测失败: {e}")
            return "unknown", 0.0

    def predict_with_params(self, text: str) -> PredictionResult:
        """预测意图并提取参数"""
        if not self.is_loaded():
            return PredictionResult(intent="unknown", confidence=0.0)

        try:
            import torch

            self.model.eval()

            encoding = self.tokenizer(
                text,
                max_length=self.config.max_length,
                padding='max_length',
                truncation=True,
                return_tensors='pt'
            )

            input_ids = encoding['input_ids'].to(self.device)
            attention_mask = encoding['attention_mask'].to(self.device)

            with torch.no_grad():
                intent_logits, param_logits = self.model(input_ids=input_ids, attention_mask=attention_mask)

                intent_probs = torch.softmax(intent_logits, dim=-1)
                intent_pred = torch.argmax(intent_probs, dim=-1)
                intent_confidence = intent_probs[0, intent_pred].item()

                param_probs = torch.softmax(param_logits, dim=-1)
                param_preds = torch.argmax(param_probs, dim=-1)
                param_confidences = torch.max(param_probs, dim=-1).values

            intent_idx = intent_pred.item()
            intent_name = self.id_to_label.get(intent_idx, "unknown")

            param_extractions = self._extract_params_from_tags(
                text,
                input_ids[0],
                param_preds[0],
                param_confidences[0]
            )

            params = {}
            for extraction in param_extractions:
                if extraction.param_type not in params:
                    params[extraction.param_type] = extraction.value

            return PredictionResult(
                intent=intent_name,
                confidence=intent_confidence,
                params=params,
                param_extractions=param_extractions
            )

        except Exception as e:
            logger.error(f"预测失败: {e}")
            return PredictionResult(intent="unknown", confidence=0.0)

    def _extract_params_from_tags(
        self,
        text: str,
        input_ids,
        param_preds,
        param_confidences
    ) -> list[ParamExtraction]:
        """从 BIO 标签提取参数"""
        extractions = []

        tokens = self.tokenizer.convert_ids_to_tokens(input_ids)
        tags = [self.id_to_param_tag.get(idx.item(), "O") for idx in param_preds]

        current_entity = None
        current_tokens = []
        current_start = None
        current_confidences = []

        for i, (token, tag) in enumerate(zip(tokens, tags)):
            if token in ['[CLS]', '[SEP]', '[PAD]']:
                continue

            if tag.startswith("B-"):
                if current_entity and current_tokens:
                    extractions.append(self._create_extraction(
                        text, current_entity, current_tokens,
                        current_start, current_confidences
                    ))

                current_entity = tag[2:]
                current_tokens = [token]
                current_start = i
                current_confidences = [param_confidences[i].item()]

            elif tag.startswith("I-") and current_entity == tag[2:]:
                current_tokens.append(token)
                current_confidences.append(param_confidences[i].item())

            else:
                if current_entity and current_tokens:
                    extractions.append(self._create_extraction(
                        text, current_entity, current_tokens,
                        current_start, current_confidences
                    ))
                current_entity = None
                current_tokens = []
                current_start = None
                current_confidences = []

        if current_entity and current_tokens:
            extractions.append(self._create_extraction(
                text, current_entity, current_tokens,
                current_start, current_confidences
            ))

        return extractions

    def _create_extraction(
        self,
        text: str,
        entity_type: str,
        tokens: list[str],
        start_idx: int,
        confidences: list[float]
    ) -> ParamExtraction:
        """创建参数提取结果"""
        value = self._decode_tokens(tokens)

        param_type = PARAM_TAG_MAP.get(entity_type, entity_type.lower())

        avg_confidence = sum(confidences) / len(confidences) if confidences else 1.0

        return ParamExtraction(
            param_type=param_type,
            value=value,
            start=start_idx,
            end=start_idx + len(tokens),
            confidence=avg_confidence
        )

    def _decode_tokens(self, tokens: list[str]) -> str:
        """将 BERT tokens 解码为文本"""
        text = ""
        for token in tokens:
            if token.startswith("##"):
                text += token[2:]
            elif token.startswith("▁"):
                text += token[1:]
            else:
                if text:
                    text += token
                else:
                    text = token
        return text

    def predict_batch(self, texts: list[str]) -> list[tuple[str, float]]:
        """批量预测"""
        results = []
        for text in texts:
            intent, confidence = self.predict(text)
            results.append((intent, confidence))
        return results

    def predict_batch_with_params(self, texts: list[str]) -> list[PredictionResult]:
        """批量预测（含参数提取）"""
        results = []
        for text in texts:
            result = self.predict_with_params(text)
            results.append(result)
        return results

    def get_top_k_intents(self, text: str, k: int = 3) -> list[tuple[str, float]]:
        """获取 top-k 意图"""
        if not self.is_loaded():
            return [("unknown", 0.0)]

        try:
            import torch

            self.model.eval()

            encoding = self.tokenizer(
                text,
                max_length=self.config.max_length,
                padding='max_length',
                truncation=True,
                return_tensors='pt'
            )

            input_ids = encoding['input_ids'].to(self.device)
            attention_mask = encoding['attention_mask'].to(self.device)

            with torch.no_grad():
                intent_logits, _ = self.model(input_ids=input_ids, attention_mask=attention_mask)
                probs = torch.softmax(intent_logits, dim=-1)

            probs = probs[0].cpu().numpy()
            top_k_indices = np.argsort(probs)[::-1][:k]

            results = []
            for idx in top_k_indices:
                intent_name = self.id_to_label.get(idx, "unknown")
                confidence = probs[idx]
                results.append((intent_name, float(confidence)))

            return results

        except Exception as e:
            logger.error(f"预测失败: {e}")
            return [("unknown", 0.0)]


_classifier_instance = None


def get_bert_classifier(config: BERTConfig | None = None) -> BERTIntentClassifier:
    """获取 BERT 分类器单例"""
    global _classifier_instance
    if _classifier_instance is None:
        _classifier_instance = BERTIntentClassifier(config)
    return _classifier_instance


def predict_intent(text: str) -> tuple[str, float]:
    """预测意图（便捷函数）"""
    classifier = get_bert_classifier()
    return classifier.predict(text)


def predict_intent_with_params(text: str) -> PredictionResult:
    """预测意图并提取参数（便捷函数）"""
    classifier = get_bert_classifier()
    return classifier.predict_with_params(text)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("=" * 60)
    print("  测试 BERT 意图分类器（含参数抽取）")
    print("=" * 60)

    classifier = get_bert_classifier()

    if not classifier.is_loaded():
        print("模型未加载，请先训练模型")
        sys.exit(1)

    test_cases = [
        "创建一个test.py文件",
        "读取config.json",
        "删除test.py文件",
        "打开VS Code",
        "截图",
        "复制这段代码",
        "粘贴内容",
        "关闭当前窗口",
        "帮我搜索一下Python教程",
        "列出当前目录文件",
        "识别屏幕上的文字",
        "开始录屏",
        "停止录制",
        "查看系统信息",
        "列出所有进程",
        "结束chrome进程",
    ]

    print("\n预测结果（含参数提取）:")
    for text in test_cases:
        result = classifier.predict_with_params(text)
        params_str = ", ".join(f"{k}={v}" for k, v in result.params.items()) if result.params else "无参数"
        print(f"  '{text}' -> {result.intent} ({result.confidence:.4f}) [{params_str}]")

    print("\nTop-3 预测:")
    text = "帮我创建一个文件"
    top_k = classifier.get_top_k_intents(text, k=3)
    for intent, conf in top_k:
        print(f"  {intent}: {conf:.4f}")
