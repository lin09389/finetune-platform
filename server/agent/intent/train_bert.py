"""
使用 modelscope 训练BERT意图分类器
支持意图分类和参数抽取（序列标注）多任务学习
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

os.environ['HF_HUB_DISABLE_SYMLINKS_WARNING'] = '1'

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@dataclass
class TrainingConfig:
    model_name: str = "bert-base-chinese"
    max_length: int = 128
    batch_size: int = 8
    epochs: int = 5
    learning_rate: float = 2e-5
    output_dir: str = "models/intent_bert"
    seed: int = 42
    device: str = "cuda"
    early_stopping_patience: int = 3
    intent_loss_weight: float = 1.0
    param_loss_weight: float = 2.0


def load_training_data():
    """加载训练数据（含参数标注）"""
    from sklearn.model_selection import train_test_split

    from agent.intent.bio_tagger import (
        create_annotated_dataset,
        get_param_tag_map,
    )
    from agent.intent.training_data_expanded import get_all_intent_names, get_all_samples

    samples = get_all_samples()
    intent_names = get_all_intent_names()

    label_to_id = {name: idx for idx, name in enumerate(intent_names)}
    label_map = {v: k for k, v in label_to_id.items()}

    param_tag_map = get_param_tag_map()

    annotated_samples = create_annotated_dataset(samples, auto_generate_params=True)

    print(f"总样本数: {len(annotated_samples)}")
    print(f"意图类型数: {len(intent_names)}")
    print(f"参数标签数: {len(param_tag_map)}")

    entity_count = 0
    for sample in annotated_samples:
        non_o_count = sum(1 for l in sample.labels if l != "O")
        entity_count += non_o_count
    print(f"参数实体标注数: {entity_count}")

    train_samples, val_samples = train_test_split(
        annotated_samples, test_size=0.2, random_state=42
    )

    print(f"训练集: {len(train_samples)} 样本")
    print(f"验证集: {len(val_samples)} 样本")

    return train_samples, val_samples, label_map, param_tag_map


def download_model_from_modelscope():
    """从 modelscope 下载模型"""
    try:
        from modelscope import snapshot_download

        print("正在从 ModelScope 下载 bert-base-chinese 模型...")
        model_dir = snapshot_download(
            'tiansz/bert-base-chinese',
            cache_dir='models/modelscope_cache',
            revision='master'
        )
        print(f"模型已下载到: {model_dir}")

        if os.path.exists(os.path.join(model_dir, 'pytorch_model.bin')):
            print("找到 pytorch_model.bin")
        elif os.path.exists(os.path.join(model_dir, 'model.safetensors')):
            print("找到 model.safetensors")
        else:
            print("警告: 未找到模型权重文件")
            print(f"模型目录内容: {os.listdir(model_dir)}")

        return model_dir
    except ImportError:
        print("ModelScope 未安装，尝试使用本地模型...")
        return None
    except Exception as e:
        print(f"下载模型失败: {e}")
        return None


class BERTTrainer:
    """BERT训练器（支持多任务学习）"""

    def __init__(self, config: TrainingConfig):
        self.config = config
        self.model = None
        self.tokenizer = None
        self.label_map = None
        self.param_tag_map = None
        self.id_to_param_tag = None
        self.device = config.device

    def load_model(self, num_labels: int, num_param_tags: int):
        """加载模型"""
        import torch
        from torch import nn
        from transformers import BertConfig, BertModel, BertTokenizer

        print(f"正在加载模型: {self.config.model_name}")

        model_dir = download_model_from_modelscope()

        if model_dir and os.path.exists(model_dir):
            print(f"从本地加载模型: {model_dir}")
            self.tokenizer = BertTokenizer.from_pretrained(model_dir)
            self.model = BertModel.from_pretrained(model_dir)
        else:
            print("使用预训练配置创建模型...")
            config = BertConfig.from_pretrained(self.config.model_name)
            self.tokenizer = BertTokenizer.from_pretrained(self.config.model_name)
            self.model = BertModel(config)

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

        self.model = IntentClassifierWithParamExtraction(
            self.model, num_labels, num_param_tags
        )

        if torch.cuda.is_available() and self.device == "cuda":
            self.model.to(self.device)
            print(f"模型已加载到 GPU: {torch.cuda.get_device_name(0)}")
        else:
            self.device = "cpu"
            self.model.to(self.device)
            print("模型已加载到 CPU")

    def train(self, train_samples, val_samples, label_map, param_tag_map):
        """训练模型"""
        import torch
        from torch.optim import AdamW
        from torch.utils.data import DataLoader, Dataset
        from tqdm import tqdm

        self.label_map = label_map
        self.param_tag_map = param_tag_map
        self.id_to_param_tag = {v: k for k, v in param_tag_map.items()}

        num_labels = len(label_map)
        num_param_tags = len(param_tag_map)

        self.load_model(num_labels, num_param_tags)

        label_to_id = {v: k for k, v in label_map.items()}

        class IntentParamDataset(Dataset):
            def __init__(self, samples, tokenizer, max_length, label_to_id, param_tag_map):
                self.samples = samples
                self.tokenizer = tokenizer
                self.max_length = max_length
                self.label_to_id = label_to_id
                self.param_tag_map = param_tag_map

            def __len__(self):
                return len(self.samples)

            def _align_labels_to_tokens(self, text: str, char_labels: list[str]) -> list[int]:
                encoding = self.tokenizer(
                    text,
                    max_length=self.max_length,
                    padding='max_length',
                    truncation=True,
                    return_offsets_mapping=True
                )

                input_ids = encoding['input_ids']
                offset_mapping = encoding['offset_mapping']
                tokens = self.tokenizer.convert_ids_to_tokens(input_ids)

                param_label_ids = []

                for i, (token, (start, end)) in enumerate(zip(tokens, offset_mapping)):
                    if token in ['[CLS]', '[SEP]', '[PAD]']:
                        param_label_ids.append(self.param_tag_map['O'])
                    elif start < len(text):
                        char_label = char_labels[start] if start < len(char_labels) else 'O'
                        param_label_ids.append(self.param_tag_map.get(char_label, self.param_tag_map['O']))
                    else:
                        param_label_ids.append(self.param_tag_map['O'])

                return param_label_ids

            def __getitem__(self, idx):
                sample = self.samples[idx]
                text = sample.text
                intent_label = self.label_to_id[sample.intent]
                char_labels = sample.char_labels

                encoding = self.tokenizer(
                    text,
                    max_length=self.max_length,
                    padding='max_length',
                    truncation=True,
                    return_tensors='pt'
                )

                input_ids = encoding['input_ids'].flatten()
                attention_mask = encoding['attention_mask'].flatten()

                param_label_ids = self._align_labels_to_tokens(text, char_labels)

                return {
                    'input_ids': input_ids,
                    'attention_mask': attention_mask,
                    'intent_labels': torch.tensor(intent_label, dtype=torch.long),
                    'param_labels': torch.tensor(param_label_ids[:self.max_length], dtype=torch.long)
                }

        train_dataset = IntentParamDataset(
            train_samples, self.tokenizer, self.config.max_length,
            label_to_id, param_tag_map
        )
        val_dataset = IntentParamDataset(
            val_samples, self.tokenizer, self.config.max_length,
            label_to_id, param_tag_map
        )

        train_loader = DataLoader(train_dataset, batch_size=self.config.batch_size, shuffle=True)
        val_loader = DataLoader(val_dataset, batch_size=self.config.batch_size, shuffle=False)

        optimizer = AdamW(self.model.parameters(), lr=self.config.learning_rate)
        intent_criterion = torch.nn.CrossEntropyLoss()
        param_criterion = torch.nn.CrossEntropyLoss(ignore_index=param_tag_map['O'])

        best_val_acc = 0.0
        best_val_f1 = 0.0
        best_epoch = 0
        patience_counter = 0
        start_time = datetime.now()

        print(f"\n开始训练，共 {self.config.epochs} 轮...")
        print(f"意图损失权重: {self.config.intent_loss_weight}")
        print(f"参数损失权重: {self.config.param_loss_weight}")

        for epoch in range(self.config.epochs):
            self.model.train()
            train_loss = 0.0
            train_intent_correct = 0
            train_param_correct = 0
            train_param_total = 0
            train_total = 0

            progress_bar = tqdm(train_loader, desc=f"Epoch {epoch + 1}/{self.config.epochs}")

            for batch in progress_bar:
                input_ids = batch['input_ids'].to(self.device)
                attention_mask = batch['attention_mask'].to(self.device)
                intent_labels = batch['intent_labels'].to(self.device)
                param_labels = batch['param_labels'].to(self.device)

                optimizer.zero_grad()

                intent_logits, param_logits = self.model(
                    input_ids=input_ids,
                    attention_mask=attention_mask
                )

                intent_loss = intent_criterion(intent_logits, intent_labels)

                param_logits_flat = param_logits.view(-1, param_logits.size(-1))
                param_labels_flat = param_labels.view(-1)
                param_loss = param_criterion(param_logits_flat, param_labels_flat)

                total_loss = (
                    self.config.intent_loss_weight * intent_loss +
                    self.config.param_loss_weight * param_loss
                )

                total_loss.backward()
                torch.nn.utils.clip_grad_norm_(self.model.parameters(), max_norm=1.0)
                optimizer.step()

                train_loss += total_loss.item()

                intent_predictions = torch.argmax(intent_logits, dim=-1)
                train_intent_correct += (intent_predictions == intent_labels).sum().item()

                param_predictions = torch.argmax(param_logits, dim=-1)
                non_o_mask = param_labels != param_tag_map['O']
                train_param_correct += ((param_predictions == param_labels) & non_o_mask).sum().item()
                train_param_total += non_o_mask.sum().item()

                train_total += intent_labels.size(0)

                progress_bar.set_postfix({
                    'loss': f'{total_loss.item():.4f}',
                    'intent_acc': f'{train_intent_correct/train_total:.4f}',
                    'param_acc': f'{train_param_correct/max(train_param_total, 1):.4f}'
                })

            train_intent_acc = train_intent_correct / train_total
            train_param_acc = train_param_correct / max(train_param_total, 1)

            val_intent_acc, val_param_f1 = self._evaluate(val_loader, intent_criterion, param_criterion, param_tag_map)

            print(f"Epoch {epoch + 1}:")
            print(f"  Train - Intent Acc: {train_intent_acc:.4f}, Param Acc: {train_param_acc:.4f}")
            print(f"  Val   - Intent Acc: {val_intent_acc:.4f}, Param F1: {val_param_f1:.4f}")

            if val_intent_acc > best_val_acc:
                best_val_acc = val_intent_acc
                best_val_f1 = val_param_f1
                best_epoch = epoch + 1
                patience_counter = 0
                self.save_model(self.config.output_dir)
            else:
                patience_counter += 1

            if patience_counter >= self.config.early_stopping_patience:
                print(f"Early stopping at epoch {epoch + 1}")
                break

        training_time = (datetime.now() - start_time).total_seconds()

        return {
            'intent_accuracy': best_val_acc,
            'param_f1': best_val_f1,
            'training_time': training_time,
            'epochs_trained': epoch + 1,
            'best_epoch': best_epoch
        }

    def _evaluate(self, data_loader, intent_criterion, param_criterion, param_tag_map):
        """评估模型"""
        from collections import defaultdict

        import torch

        self.model.eval()
        intent_correct = 0
        intent_total = 0

        param_tp = defaultdict(int)
        param_fp = defaultdict(int)
        param_fn = defaultdict(int)

        with torch.no_grad():
            for batch in data_loader:
                input_ids = batch['input_ids'].to(self.device)
                attention_mask = batch['attention_mask'].to(self.device)
                intent_labels = batch['intent_labels'].to(self.device)
                param_labels = batch['param_labels'].to(self.device)

                intent_logits, param_logits = self.model(
                    input_ids=input_ids,
                    attention_mask=attention_mask
                )

                intent_predictions = torch.argmax(intent_logits, dim=-1)
                intent_correct += (intent_predictions == intent_labels).sum().item()
                intent_total += intent_labels.size(0)

                param_predictions = torch.argmax(param_logits, dim=-1)

                for i in range(param_predictions.size(0)):
                    for j in range(param_predictions.size(1)):
                        pred_tag = self.id_to_param_tag.get(param_predictions[i, j].item(), 'O')
                        true_tag = self.id_to_param_tag.get(param_labels[i, j].item(), 'O')

                        if pred_tag != 'O' and true_tag != 'O':
                            if pred_tag == true_tag:
                                param_tp[true_tag] += 1
                            else:
                                param_fp[pred_tag] += 1
                                param_fn[true_tag] += 1
                        elif pred_tag != 'O' and true_tag == 'O':
                            param_fp[pred_tag] += 1
                        elif pred_tag == 'O' and true_tag != 'O':
                            param_fn[true_tag] += 1

        intent_acc = intent_correct / intent_total

        total_tp = sum(param_tp.values())
        total_fp = sum(param_fp.values())
        total_fn = sum(param_fn.values())

        precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0
        recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

        return intent_acc, f1

    def predict(self, text: str) -> tuple[str, float]:
        """预测意图"""
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
        intent_name = self.label_map.get(pred_idx, self.label_map.get(str(pred_idx), "unknown"))

        return intent_name, confidence

    def predict_with_params(self, text: str) -> dict[str, Any]:
        """预测意图并提取参数"""
        import torch

        self.model.eval()

        encoding = self.tokenizer(
            text,
            max_length=self.config.max_length,
            padding='max_length',
            truncation=True,
            return_tensors='pt',
            return_offsets_mapping=True
        )

        input_ids = encoding['input_ids'].to(self.device)
        attention_mask = encoding['attention_mask'].to(self.device)
        offset_mapping = encoding['offset_mapping'][0]

        with torch.no_grad():
            intent_logits, param_logits = self.model(
                input_ids=input_ids,
                attention_mask=attention_mask
            )

            intent_probs = torch.softmax(intent_logits, dim=-1)
            intent_pred = torch.argmax(intent_probs, dim=-1)
            intent_confidence = intent_probs[0, intent_pred].item()

            param_preds = torch.argmax(param_logits, dim=-1)

        intent_idx = intent_pred.item()
        intent_name = self.label_map.get(intent_idx, self.label_map.get(str(intent_idx), "unknown"))

        tokens = self.tokenizer.convert_ids_to_tokens(input_ids[0])
        param_tags = [self.id_to_param_tag.get(idx.item(), 'O') for idx in param_preds[0]]

        params = self._extract_params_from_tags(text, tokens, param_tags, offset_mapping)

        return {
            'intent': intent_name,
            'confidence': intent_confidence,
            'params': params,
            'tokens': tokens,
            'tags': param_tags
        }

    def _extract_params_from_tags(self, text: str, tokens: list[str], tags: list[str], offset_mapping=None) -> dict[str, str]:
        """从 BIO 标签提取参数"""
        params = {}
        current_entity = None
        current_start = None
        current_end = None

        for i, (token, tag) in enumerate(zip(tokens, tags)):
            if token in ['[CLS]', '[SEP]', '[PAD]']:
                continue

            if tag.startswith("B-"):
                if current_entity and current_start is not None:
                    entity_type = current_entity.lower()
                    if offset_mapping is not None and current_start < len(text) and current_end <= len(text):
                        entity_value = text[current_start:current_end]
                    else:
                        entity_value = ""

                    if entity_type in ['file_path', 'app_name', 'url', 'content', 'directory',
                                     'text', 'number', 'query', 'key', 'process_name',
                                     'destination', 'new_name', 'position', 'button',
                                     'direction', 'area', 'type']:
                        if entity_type not in params:
                            params[entity_type] = entity_value

                current_entity = tag[2:]
                if offset_mapping is not None:
                    current_start = offset_mapping[i][0].item()
                    current_end = offset_mapping[i][1].item()
                else:
                    current_start = None
                    current_end = None

            elif tag.startswith("I-") and current_entity == tag[2:]:
                if offset_mapping is not None and current_end is not None:
                    current_end = offset_mapping[i][1].item()

            else:
                if current_entity and current_start is not None:
                    entity_type = current_entity.lower()
                    if offset_mapping is not None and current_start < len(text) and current_end <= len(text):
                        entity_value = text[current_start:current_end]
                    else:
                        entity_value = ""

                    if entity_type in ['file_path', 'app_name', 'url', 'content', 'directory',
                                     'text', 'number', 'query', 'key', 'process_name',
                                     'destination', 'new_name', 'position', 'button',
                                     'direction', 'area', 'type']:
                        if entity_type not in params:
                            params[entity_type] = entity_value

                current_entity = None
                current_start = None
                current_end = None

        if current_entity and current_start is not None:
            entity_type = current_entity.lower()
            if offset_mapping is not None and current_start < len(text) and current_end <= len(text):
                entity_value = text[current_start:current_end]
            else:
                entity_value = ""

            if entity_type in ['file_path', 'app_name', 'url', 'content', 'directory',
                             'text', 'number', 'query', 'key', 'process_name',
                             'destination', 'new_name', 'position', 'button',
                             'direction', 'area', 'type']:
                if entity_type not in params:
                    params[entity_type] = entity_value

        return params

    def save_model(self, output_dir: str):
        """保存模型"""
        import torch

        os.makedirs(output_dir, exist_ok=True)

        torch.save(self.model.state_dict(), os.path.join(output_dir, 'model.pt'))
        self.tokenizer.save_pretrained(output_dir)

        with open(os.path.join(output_dir, 'label_map.json'), 'w', encoding='utf-8') as f:
            json.dump(self.label_map, f, ensure_ascii=False, indent=2)

        with open(os.path.join(output_dir, 'param_tag_map.json'), 'w', encoding='utf-8') as f:
            json.dump(self.param_tag_map, f, ensure_ascii=False, indent=2)

        print(f"模型已保存到: {output_dir}")


def main():
    print("=" * 60)
    print("  BERT 意图分类 + 参数抽取 训练")
    print("=" * 60)

    config = TrainingConfig()

    train_samples, val_samples, label_map, param_tag_map = load_training_data()

    trainer = BERTTrainer(config)
    result = trainer.train(train_samples, val_samples, label_map, param_tag_map)

    print("\n" + "=" * 60)
    print("  训练结果")
    print("=" * 60)
    print(f"最佳意图准确率: {result['intent_accuracy']:.4f}")
    print(f"最佳参数 F1: {result['param_f1']:.4f}")
    print(f"训练时间: {result['training_time']:.2f}秒")
    print(f"训练轮数: {result['epochs_trained']}")
    print(f"最佳轮次: {result['best_epoch']}")

    print("\n测试预测（含参数提取）:")
    test_cases = [
        "创建一个新文件",
        "读取config.json",
        "删除test.py文件",
        "打开VS Code",
        "截图",
        "复制这段代码",
        "粘贴内容",
        "关闭当前窗口",
        "帮我搜索一下Python教程",
        "创建main.py文件",
        "打开Chrome浏览器",
        "访问https://github.com",
    ]

    for text in test_cases:
        result = trainer.predict_with_params(text)
        params_str = ", ".join(f"{k}={v}" for k, v in result['params'].items()) if result['params'] else "无参数"
        print(f"  '{text}' -> {result['intent']} ({result['confidence']:.4f}) [{params_str}]")


if __name__ == "__main__":
    main()
