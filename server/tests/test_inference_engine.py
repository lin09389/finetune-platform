"""
推理引擎单元测试

测试覆盖�?- 引擎抽象�?- 引擎工厂
- HuggingFace 引擎
- vLLM 引擎
- Flash Attention 检�?"""
import pytest
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from dataclasses import asdict
from pathlib import Path
import asyncio
import tempfile
import os

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.inference.engine_base import (
    InferenceEngine,
    EngineConfig,
    GenerationConfig,
    GenerationResult,
)
from core.inference.engine_factory import (
    EngineFactory,
    EngineType,
    create_engine,
    create_engine_with_fallback,
)


class TestEngineConfig:
    """引擎配置测试"""

    def test_engine_config_creation(self):
        config = EngineConfig(model_id="test_model")
        assert config.model_id == "test_model"
        assert config.device == "auto"
        assert config.torch_dtype == "float16"
        assert config.trust_remote_code is True

    def test_engine_config_custom(self):
        config = EngineConfig(
            model_id="test_model",
            device="cuda:0",
            torch_dtype="bfloat16",
            trust_remote_code=False,
            low_cpu_mem_usage=False,
            max_cache_size=5,
            lora_path="/path/to/lora"
        )
        assert config.device == "cuda:0"
        assert config.torch_dtype == "bfloat16"
        assert config.max_cache_size == 5
        assert config.lora_path == "/path/to/lora"


class TestGenerationConfig:
    """生成配置测试"""

    def test_generation_config_creation(self):
        config = GenerationConfig()
        assert config.max_new_tokens == 1024
        assert config.temperature == 0.7
        assert config.top_p == 0.9
        assert config.do_sample is True

    def test_generation_config_custom(self):
        config = GenerationConfig(
            max_new_tokens=2048,
            temperature=0.5,
            top_p=0.8,
            top_k=40,
            repetition_penalty=1.2,
            do_sample=False
        )
        assert config.max_new_tokens == 2048
        assert config.temperature == 0.5
        assert config.do_sample is False

    def test_generation_config_to_dict(self):
        config = GenerationConfig(
            max_new_tokens=512,
            temperature=0.8
        )
        data = config.to_dict()
        assert data["max_new_tokens"] == 512
        assert data["temperature"] == 0.8
        assert "top_p" in data


class TestGenerationResult:
    """生成结果测试"""

    def test_generation_result_creation(self):
        result = GenerationResult(
            text="Hello world",
            tokens=10,
            time=1.5,
            model_id="test_model",
            backend="huggingface"
        )
        assert result.text == "Hello world"
        assert result.tokens == 10
        assert result.time == 1.5
        assert result.model_id == "test_model"
        assert result.backend == "huggingface"

    def test_generation_result_with_metadata(self):
        result = GenerationResult(
            text="Test",
            tokens=5,
            time=0.5,
            model_id="test",
            backend="vllm",
            metadata={"prompt_tokens": 10, "finish_reason": "stop"}
        )
        assert result.metadata["prompt_tokens"] == 10
        assert result.metadata["finish_reason"] == "stop"

    def test_generation_result_to_dict(self):
        result = GenerationResult(
            text="Test",
            tokens=5,
            time=0.5,
            model_id="test",
            backend="huggingface"
        )
        data = result.to_dict()
        assert data["text"] == "Test"
        assert data["tokens"] == 5
        assert data["backend"] == "huggingface"


class MockEngine(InferenceEngine):
    """模拟引擎用于测试"""

    engine_type: str = "mock"

    async def load(self) -> None:
        self._is_loaded = True
        self._load_time = 0.1

    async def unload(self) -> None:
        self._is_loaded = False

    async def generate(self, prompt: str, config=None, **kwargs) -> GenerationResult:
        return GenerationResult(
            text=f"Generated: {prompt[:20]}",
            tokens=10,
            time=0.5,
            model_id=self.config.model_id,
            backend=self.engine_type
        )

    async def stream(self, prompt: str, config=None, **kwargs):
        for word in ["Hello", " ", "World"]:
            yield word

    async def apply_lora(self, lora_path: str) -> None:
        self._lora_path = lora_path

    async def remove_lora(self) -> None:
        self._lora_path = None


class TestInferenceEngine:
    """推理引擎基类测试"""

    def test_engine_creation(self):
        config = EngineConfig(model_id="test_model")
        engine = MockEngine(config)
        assert engine.config.model_id == "test_model"
        assert engine.is_loaded is False

    @pytest.mark.asyncio
    async def test_engine_load(self):
        config = EngineConfig(model_id="test_model")
        engine = MockEngine(config)
        await engine.load()
        assert engine.is_loaded is True
        assert engine._load_time == 0.1

    @pytest.mark.asyncio
    async def test_engine_unload(self):
        config = EngineConfig(model_id="test_model")
        engine = MockEngine(config)
        await engine.load()
        await engine.unload()
        assert engine.is_loaded is False

    @pytest.mark.asyncio
    async def test_engine_generate(self):
        config = EngineConfig(model_id="test_model")
        engine = MockEngine(config)
        result = await engine.generate("Hello")
        assert result.text.startswith("Generated:")
        assert result.tokens == 10

    @pytest.mark.asyncio
    async def test_engine_stream(self):
        config = EngineConfig(model_id="test_model")
        engine = MockEngine(config)
        chunks = []
        async for chunk in engine.stream("Hello"):
            chunks.append(chunk)
        assert chunks == ["Hello", " ", "World"]

    @pytest.mark.asyncio
    async def test_engine_apply_lora(self):
        config = EngineConfig(model_id="test_model")
        engine = MockEngine(config)
        await engine.apply_lora("/path/to/lora")
        assert engine._lora_path == "/path/to/lora"

    @pytest.mark.asyncio
    async def test_engine_remove_lora(self):
        config = EngineConfig(model_id="test_model")
        engine = MockEngine(config)
        await engine.apply_lora("/path/to/lora")
        await engine.remove_lora()
        assert engine._lora_path is None

    def test_engine_model_info(self):
        config = EngineConfig(model_id="test_model")
        engine = MockEngine(config)
        info = engine.model_info
        assert info["model_id"] == "test_model"
        assert info["engine_type"] == "mock"
        assert info["is_loaded"] is False

    def test_engine_repr(self):
        config = EngineConfig(model_id="test_model")
        engine = MockEngine(config)
        repr_str = repr(engine)
        assert "MockEngine" in repr_str
        assert "test_model" in repr_str


class TestEngineFactory:
    """引擎工厂测试"""

    def setup_method(self):
        EngineFactory._registry = {}
        EngineFactory._availability_cache = {}
        EngineFactory.register("mock", MockEngine)

    def test_register_engine(self):
        assert "mock" in EngineFactory._registry
        assert EngineFactory._registry["mock"] == MockEngine

    def test_create_engine(self):
        config = EngineConfig(model_id="test_model")
        engine = EngineFactory.create("mock", config)
        assert isinstance(engine, MockEngine)
        assert engine.config.model_id == "test_model"

    def test_create_unsupported_engine(self):
        config = EngineConfig(model_id="test_model")
        with pytest.raises(ValueError) as excinfo:
            EngineFactory.create("unsupported", config)
        assert "不支持的引擎类型" in str(excinfo.value)

    def test_is_available_registered(self):
        available = EngineFactory.is_available("mock")
        assert available is True

    def test_is_available_unregistered(self):
        available = EngineFactory.is_available("nonexistent")
        assert available is False

    @patch("core.inference.engine_factory.EngineFactory.is_available")
    def test_create_with_fallback(self, mock_is_available):
        mock_is_available.return_value = True
        config = EngineConfig(model_id="test_model")
        
        engine = EngineFactory.create_with_fallback("mock", config)
        assert isinstance(engine, MockEngine)

    @patch("core.inference.engine_factory.EngineFactory.is_available")
    def test_create_with_fallback_uses_fallback(self, mock_is_available):
        mock_is_available.return_value = True
        config = EngineConfig(model_id="test_model")
        
        EngineFactory.register("fallback", MockEngine)
        
        engine = EngineFactory.create_with_fallback(
            "nonexistent",
            config,
            fallback_types=["mock"]
        )
        assert isinstance(engine, MockEngine)

    def test_get_available_engines(self):
        engines = EngineFactory.get_available_engines()
        assert "mock" in engines
        assert engines["mock"]["available"] is True

    def test_clear_cache(self):
        EngineFactory._availability_cache["test"] = True
        EngineFactory.clear_cache()
        assert len(EngineFactory._availability_cache) == 0


class TestChatTemplate:
    """聊天模板测试"""

    def test_apply_chat_template_qwen(self):
        config = EngineConfig(model_id="Qwen/Qwen2.5-7B-Instruct")
        engine = MockEngine(config)
        
        formatted = engine.apply_chat_template("Hello")
        assert "<|im_start|>user" in formatted
        assert "<|im_end|>" in formatted

    def test_apply_chat_template_qwen3(self):
        config = EngineConfig(model_id="Qwen/Qwen3.5-7B-Instruct")
        engine = MockEngine(config)
        
        formatted = engine.apply_chat_template("Hello")
        assert "<|im_start|>user" in formatted

    def test_apply_chat_template_already_formatted(self):
        config = EngineConfig(model_id="Qwen/Qwen2.5-7B-Instruct")
        engine = MockEngine(config)
        
        already_formatted = "<|im_start|>user\nHello<|im_end|>\n<|im_start|>assistant\n"
        formatted = engine.apply_chat_template(already_formatted)
        assert formatted == already_formatted


class TestFlashAttention:
    """Flash Attention 检测测�?""

    def test_get_gpu_compute_capability_no_cuda(self):
        with patch("torch.cuda.is_available", return_value=False):
            from core.inference.flash_attention import get_gpu_compute_capability
            capability = get_gpu_compute_capability()
            assert capability is None

    def test_get_gpu_compute_capability_with_cuda(self):
        with patch("torch.cuda.is_available", return_value=True), \
             patch("torch.cuda.current_device", return_value=0), \
             patch("torch.cuda.get_device_capability", return_value=(8, 6)):
            from core.inference.flash_attention import get_gpu_compute_capability, reset_detection_cache
            reset_detection_cache()
            capability = get_gpu_compute_capability()
            assert capability == (8, 6)

    def test_is_gpu_architecture_supported_ampere(self):
        with patch("core.inference.flash_attention.get_gpu_compute_capability", return_value=(8, 0)):
            from core.inference.flash_attention import is_gpu_architecture_supported, reset_detection_cache
            reset_detection_cache()
            supported = is_gpu_architecture_supported()
            assert supported is True

    def test_is_gpu_architecture_supported_older_gpu(self):
        with patch("core.inference.flash_attention.get_gpu_compute_capability", return_value=(7, 5)):
            from core.inference.flash_attention import is_gpu_architecture_supported, reset_detection_cache
            reset_detection_cache()
            supported = is_gpu_architecture_supported()
            assert supported is False

    def test_is_flash_attn_2_installed_true(self):
        mock_flash_attn = MagicMock()
        mock_flash_attn.__version__ = "2.0.0"
        
        with patch.dict("sys.modules", {"flash_attn": mock_flash_attn}):
            from core.inference.flash_attention import is_flash_attn_2_installed, reset_detection_cache
            reset_detection_cache()
            installed, version = is_flash_attn_2_installed()
            assert installed is True
            assert version == "2.0.0"

    def test_is_flash_attn_2_installed_false(self):
        with patch.dict("sys.modules", {}):
            from core.inference.flash_attention import is_flash_attn_2_installed, reset_detection_cache
            reset_detection_cache()
            
            import importlib
            import core.inference.flash_attention as fa_module
            importlib.reload(fa_module)
            
            installed, version = fa_module.is_flash_attn_2_installed()
            assert installed is False
            assert version is None

    def test_get_attention_implementation_force_eager(self):
        from core.inference.flash_attention import get_attention_implementation
        impl = get_attention_implementation(force_eager=True)
        assert impl == "eager"

    def test_get_flash_attention_info(self):
        with patch("core.inference.flash_attention.is_flash_attn_2_available", return_value=False), \
             patch("core.inference.flash_attention.is_gpu_architecture_supported", return_value=True), \
             patch("core.inference.flash_attention.is_flash_attn_2_installed", return_value=(False, None)), \
             patch("core.inference.flash_attention.get_gpu_compute_capability", return_value=(8, 6)):
            from core.inference.flash_attention import get_flash_attention_info, reset_detection_cache
            reset_detection_cache()
            info = get_flash_attention_info()
            assert "available" in info
            assert "gpu_architecture_supported" in info
            assert "recommended_implementation" in info

    def test_reset_detection_cache(self):
        from core.inference.flash_attention import reset_detection_cache, _flash_attn_available, _flash_attn_version, _gpu_architecture_supported
        
        import core.inference.flash_attention as fa_module
        fa_module._flash_attn_available = True
        fa_module._flash_attn_version = "2.0.0"
        fa_module._gpu_architecture_supported = True
        
        reset_detection_cache()
        
        assert fa_module._flash_attn_available is None
        assert fa_module._flash_attn_version is None
        assert fa_module._gpu_architecture_supported is None


class TestEngineIntegration:
    """引擎集成测试"""

    def setup_method(self):
        EngineFactory._registry = {}
        EngineFactory._availability_cache = {}
        EngineFactory.register("mock", MockEngine)

    @patch("core.inference.engine_factory.get_settings")
    def test_create_engine_convenience_function(self, mock_get_settings):
        mock_settings = MagicMock()
        mock_settings.inference_backend = "mock"
        mock_get_settings.return_value = mock_settings
        
        engine = create_engine("test_model", engine_type="mock")
        assert isinstance(engine, MockEngine)
        assert engine.config.model_id == "test_model"

    @patch("core.inference.engine_factory.get_settings")
    def test_create_engine_with_fallback_convenience(self, mock_get_settings):
        mock_settings = MagicMock()
        mock_settings.inference_backend = "mock"
        mock_get_settings.return_value = mock_settings
        
        engine = create_engine_with_fallback("test_model", preferred_type="mock")
        assert isinstance(engine, MockEngine)
