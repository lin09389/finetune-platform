"""
使用 modelscope 训练BERT意图分类器
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

os.environ['HF_HUB_DISABLE_SYMLINKS_WARNING'] = '1'

import json
import random
import logging
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
from datetime import datetime
import numpy as np
from collections import Counter

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


def load_training_data():
    """加载训练数据"""
    from sklearn.model_selection import train_test_split
    
    from agent.intent.training_data_expanded import get_all_samples, get_all_intent_names
    
    samples = get_all_samples()
    intent_names = get_all_intent_names()
    
    label_to_id = {name: idx for idx, name in enumerate(intent_names)}
    label_map = {v: k for k, v in label_to_id.items()}
    
    texts = [sample.text for intent_name, sample in samples]
    labels = [label_to_id[intent_name] for intent_name, sample in samples]
    
    print(f"总样本数: {len(texts)}")
    print(f"意图类型数: {len(intent_names)}")
    
    train_texts, val_texts, train_labels, val_labels = train_test_split(
        texts, labels, test_size=0.2, random_state=42, stratify=labels
    )
    
    print(f"训练集: {len(train_texts)} 样本")
    print(f"验证集: {len(val_texts)} 样本")
    
    return train_texts, val_texts, train_labels, val_labels, label_map


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
    """BERT训练器"""
    
    def __init__(self, config: TrainingConfig):
        self.config = config
        self.model = None
        self.tokenizer = None
        self.label_map = None
        self.device = config.device
    
    def load_model(self, num_labels: int):
        """加载模型"""
        import torch
        from transformers import BertModel, BertConfig, BertTokenizer
        from torch import nn
        
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
        
        class IntentClassifier(nn.Module):
            def __init__(self, bert_model, num_labels, dropout=0.1):
                super().__init__()
                self.bert = bert_model
                self.dropout = nn.Dropout(dropout)
                self.classifier = nn.Linear(bert_model.config.hidden_size, num_labels)
            
            def forward(self, input_ids, attention_mask):
                outputs = self.bert(input_ids=input_ids, attention_mask=attention_mask)
                pooled_output = outputs.pooler_output
                pooled_output = self.dropout(pooled_output)
                logits = self.classifier(pooled_output)
                return logits
        
        self.model = IntentClassifier(self.model, num_labels)
        
        if torch.cuda.is_available() and self.device == "cuda":
            self.model.to(self.device)
            print(f"模型已加载到 GPU: {torch.cuda.get_device_name(0)}")
        else:
            self.device = "cpu"
            self.model.to(self.device)
            print("模型已加载到 CPU")
    
    def train(self, train_texts, train_labels, val_texts, val_labels, label_map):
        """训练模型"""
        import torch
        from torch.utils.data import Dataset, DataLoader
        from torch.optim import AdamW
        from tqdm import tqdm
        
        self.label_map = label_map
        num_labels = len(label_map)
        
        self.load_model(num_labels)
        
        class IntentDataset(Dataset):
            def __init__(self, texts, labels, tokenizer, max_length):
                self.texts = texts
                self.labels = labels
                self.tokenizer = tokenizer
                self.max_length = max_length
            
            def __len__(self):
                return len(self.texts)
            
            def __getitem__(self, idx):
                text = self.texts[idx]
                label = self.labels[idx]
                
                encoding = self.tokenizer(
                    text,
                    max_length=self.max_length,
                    padding='max_length',
                    truncation=True,
                    return_tensors='pt'
                )
                
                return {
                    'input_ids': encoding['input_ids'].flatten(),
                    'attention_mask': encoding['attention_mask'].flatten(),
                    'labels': torch.tensor(label, dtype=torch.long)
                }
        
        train_dataset = IntentDataset(train_texts, train_labels, self.tokenizer, self.config.max_length)
        val_dataset = IntentDataset(val_texts, val_labels, self.tokenizer, self.config.max_length)
        
        train_loader = DataLoader(train_dataset, batch_size=self.config.batch_size, shuffle=True)
        val_loader = DataLoader(val_dataset, batch_size=self.config.batch_size, shuffle=False)
        
        optimizer = AdamW(self.model.parameters(), lr=self.config.learning_rate)
        criterion = torch.nn.CrossEntropyLoss()
        
        best_val_acc = 0.0
        best_epoch = 0
        patience_counter = 0
        start_time = datetime.now()
        
        print(f"\n开始训练，共 {self.config.epochs} 轮...")
        
        for epoch in range(self.config.epochs):
            self.model.train()
            train_loss = 0.0
            train_correct = 0
            train_total = 0
            
            progress_bar = tqdm(train_loader, desc=f"Epoch {epoch + 1}/{self.config.epochs}")
            
            for batch in progress_bar:
                input_ids = batch['input_ids'].to(self.device)
                attention_mask = batch['attention_mask'].to(self.device)
                labels = batch['labels'].to(self.device)
                
                optimizer.zero_grad()
                
                logits = self.model(input_ids=input_ids, attention_mask=attention_mask)
                loss = criterion(logits, labels)
                
                loss.backward()
                optimizer.step()
                
                train_loss += loss.item()
                predictions = torch.argmax(logits, dim=-1)
                train_correct += (predictions == labels).sum().item()
                train_total += labels.size(0)
                
                progress_bar.set_postfix({
                    'loss': f'{loss.item():.4f}',
                    'acc': f'{train_correct/train_total:.4f}'
                })
            
            train_acc = train_correct / train_total
            
            val_acc = self._evaluate(val_loader, criterion)
            
            print(f"Epoch {epoch + 1}: Train Acc={train_acc:.4f}, Val Acc={val_acc:.4f}")
            
            if val_acc > best_val_acc:
                best_val_acc = val_acc
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
            'accuracy': best_val_acc,
            'training_time': training_time,
            'epochs_trained': epoch + 1,
            'best_epoch': best_epoch
        }
    
    def _evaluate(self, data_loader, criterion) -> float:
        """评估模型"""
        import torch
        
        self.model.eval()
        correct = 0
        total = 0
        
        with torch.no_grad():
            for batch in data_loader:
                input_ids = batch['input_ids'].to(self.device)
                attention_mask = batch['attention_mask'].to(self.device)
                labels = batch['labels'].to(self.device)
                
                logits = self.model(input_ids=input_ids, attention_mask=attention_mask)
                predictions = torch.argmax(logits, dim=-1)
                correct += (predictions == labels).sum().item()
                total += labels.size(0)
        
        return correct / total
    
    def predict(self, text: str) -> Tuple[str, float]:
        """预测"""
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
            logits = self.model(input_ids=input_ids, attention_mask=attention_mask)
            probs = torch.softmax(logits, dim=-1)
            prediction = torch.argmax(probs, dim=-1)
            confidence = probs[0, prediction].item()
        
        pred_idx = prediction.item()
        intent_name = self.label_map.get(pred_idx, self.label_map.get(str(pred_idx), "unknown"))
        
        return intent_name, confidence
    
    def save_model(self, output_dir: str):
        """保存模型"""
        import torch
        
        os.makedirs(output_dir, exist_ok=True)
        
        torch.save(self.model.state_dict(), os.path.join(output_dir, 'model.pt'))
        self.tokenizer.save_pretrained(output_dir)
        
        with open(os.path.join(output_dir, 'label_map.json'), 'w', encoding='utf-8') as f:
            json.dump(self.label_map, f, ensure_ascii=False, indent=2)
        
        print(f"模型已保存到: {output_dir}")


def main():
    print("=" * 60)
    print("  BERT 意图分类训练")
    print("=" * 60)
    
    config = TrainingConfig()
    
    train_texts, val_texts, train_labels, val_labels, label_map = load_training_data()
    
    trainer = BERTTrainer(config)
    result = trainer.train(train_texts, train_labels, val_texts, val_labels, label_map)
    
    print("\n" + "=" * 60)
    print("  训练结果")
    print("=" * 60)
    print(f"最佳准确率: {result['accuracy']:.4f}")
    print(f"训练时间: {result['training_time']:.2f}秒")
    print(f"训练轮数: {result['epochs_trained']}")
    print(f"最佳轮次: {result['best_epoch']}")
    
    print("\n测试预测:")
    test_cases = [
        "创建一个新文件",
        "读取config.json",
        "删除test.py文件",
        "打开VS Code",
        "截图",
        "复制这段代码",
        "粘贴内容",
        "关闭当前窗口",
    ]
    
    for text in test_cases:
        intent, confidence = trainer.predict(text)
        print(f"  '{text}' -> {intent} ({confidence:.4f})")


if __name__ == "__main__":
    main()
