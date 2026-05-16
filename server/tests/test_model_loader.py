"""
模型加载模块单元测试
测试目标模块解析、缓存键构建、配置对象、显存估算等纯逻辑
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from training_engine.model_loader import (
    ModelLoadConfig,
    _build_cache_key,
    _resolve_target_modules,
    _estimate_vram_required,
)


class TestResolveTargetModules:
    def test_all_returns_full_list(self):
        result = _resolve_target_modules("all")
        assert result == [
            "q_proj",
            "k_proj",
            "v_proj",
            "o_proj",
            "gate_proj",
            "up_proj",
            "down_proj",
        ]

    def test_attn_returns_attention_modules(self):
        result = _resolve_target_modules("attn")
        assert result == ["q_proj", "v_proj", "k_proj", "o_proj"]

    def test_mlp_returns_mlp_modules(self):
        result = _resolve_target_modules("mlp")
        assert result == ["gate_proj", "up_proj", "down_proj"]

    def test_custom_comma_separated(self):
        result = _resolve_target_modules("q_proj, v_proj")
        assert result == ["q_proj", "v_proj"]

    def test_custom_with_spaces(self):
        result = _resolve_target_modules(" q_proj , k_proj ")
        assert result == ["q_proj", "k_proj"]

    def test_empty_string_returns_empty(self):
        result = _resolve_target_modules("")
        assert result == []


class TestBuildCacheKey:
    def test_cache_key_includes_all_params(self):
        config = ModelLoadConfig(
            model_path="meta-llama/Llama-2-7b",
            method="qlora",
            quantize=4,
            rank=8,
            alpha=16,
            target_modules="all",
            use_dora=False,
            use_flash_attn=True,
        )
        key = _build_cache_key(config)
        assert "meta-llama/Llama-2-7b" in key
        assert "qlora" in key
        assert "4" in key
        assert "8" in key
        assert "16" in key
        assert "all" in key
        assert "False" in key
        assert "True" in key

    def test_same_config_same_key(self):
        config1 = ModelLoadConfig(model_path="model-a", method="lora", rank=16)
        config2 = ModelLoadConfig(model_path="model-a", method="lora", rank=16)
        assert _build_cache_key(config1) == _build_cache_key(config2)

    def test_different_config_different_key(self):
        config1 = ModelLoadConfig(model_path="model-a", method="lora", rank=8)
        config2 = ModelLoadConfig(model_path="model-a", method="lora", rank=16)
        assert _build_cache_key(config1) != _build_cache_key(config2)


class TestEstimateVramRequired:
    def test_qlora_4bit_lowest(self):
        config = ModelLoadConfig(method="qlora", quantize=4)
        assert _estimate_vram_required(config) == pytest.approx(3.14, abs=0.1)

    def test_qlora_8bit_higher(self):
        config = ModelLoadConfig(method="qlora", quantize=8)
        assert _estimate_vram_required(config) == pytest.approx(3.39, abs=0.1)

    def test_lora_estimate(self):
        config = ModelLoadConfig(method="lora")
        assert _estimate_vram_required(config) == pytest.approx(5.94, abs=0.1)

    def test_dora_same_as_lora(self):
        config = ModelLoadConfig(method="dora")
        assert _estimate_vram_required(config) == pytest.approx(5.94, abs=0.1)

    def test_full_finetune_highest(self):
        config = ModelLoadConfig(method="full")
        assert _estimate_vram_required(config) == pytest.approx(31.28, abs=0.1)

    def test_flash_attn_reduces_estimate(self):
        config = ModelLoadConfig(method="lora", use_flash_attn=True)
        assert _estimate_vram_required(config) == pytest.approx(5.81, abs=0.1)


class TestModelLoadConfig:
    def test_default_values(self):
        config = ModelLoadConfig(model_path="test-model")
        assert config.method == "qlora"
        assert config.quantize == 4
        assert config.rank == 8
        assert config.alpha == 16
        assert config.lora_dropout == 0.05
        assert config.target_modules == "all"
        assert config.use_dora is False
        assert config.use_flash_attn is False
        assert config.gradient_checkpointing is True
        assert config.trust_remote_code is True
        assert config.bf16 is True

    def test_custom_values(self):
        config = ModelLoadConfig(
            model_path="test-model",
            method="dora",
            quantize=8,
            rank=32,
            alpha=64,
            use_flash_attn=True,
            bf16=False,
        )
        assert config.method == "dora"
        assert config.quantize == 8
        assert config.rank == 32
        assert config.alpha == 64
        assert config.use_flash_attn is True
        assert config.bf16 is False
