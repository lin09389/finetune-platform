"""
推理引擎测试

测试覆盖：
- 基础引擎类
- 引擎工厂
- Flash Attention 检测
- 聊天模板应用
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class MockEngine:
    """模拟引擎"""
    
    def __init__(self, config):
        self.config = config
        self.model_id = config.model_id
    
    def generate(self, prompt: str, **kwargs):
        return f"Generated: {prompt[:20]}..."
    
    def apply_chat_template(self, prompt: str) -> str:
        if "qwen" in self.model_id.lower():
            if "<|im_start|>" in prompt:
                return prompt
            return f"<|im_start|>user\n{prompt}<|im_end|>\n<|im_start|>assistant\n"
        return prompt


class MockEngineConfig:
    """模拟引擎配置"""
    
    def __init__(self, model_id: str = "test_model"):
        self.model_id = model_id
        self.max_tokens = 1024
        self.temperature = 0.7


class TestEngineBase:
    """引擎基类测试"""
    
    def test_mock_engine_creation(self):
        """测试模拟引擎创建"""
        config = MockEngineConfig(model_id="test_model")
        engine = MockEngine(config)
        assert engine.model_id == "test_model"
    
    def test_mock_engine_generate(self):
        """测试模拟引擎生成"""
        config = MockEngineConfig(model_id="test_model")
        engine = MockEngine(config)
        result = engine.generate("Hello World")
        assert "Generated:" in result
    
    def test_mock_engine_chat_template(self):
        """测试聊天模板"""
        config = MockEngineConfig(model_id="Qwen/Qwen2.5-7B-Instruct")
        engine = MockEngine(config)
        formatted = engine.apply_chat_template("Hello")
        assert "<|im_start|>user" in formatted


class TestEngineFactory:
    """引擎工厂测试"""
    
    def test_register_engine(self):
        """测试注册引擎"""
        from core.inference.engine_factory import EngineFactory
        
        EngineFactory._registry = {}
        EngineFactory.register("mock", MockEngine)
        
        assert "mock" in EngineFactory._registry
        assert EngineFactory._registry["mock"] == MockEngine
    
    def test_create_engine(self):
        """测试创建引擎"""
        from core.inference.engine_factory import EngineFactory
        
        EngineFactory._registry = {}
        EngineFactory.register("mock", MockEngine)
        
        config = MockEngineConfig(model_id="test_model")
        engine = EngineFactory.create("mock", config)
        
        assert isinstance(engine, MockEngine)
        assert engine.config.model_id == "test_model"
    
    def test_create_unsupported_engine(self):
        """测试创建不支持的引擎"""
        from core.inference.engine_factory import EngineFactory
        
        EngineFactory._registry = {}
        
        config = MockEngineConfig(model_id="test_model")
        
        with pytest.raises(ValueError) as excinfo:
            EngineFactory.create("unsupported", config)
        assert "不支持的引擎类型" in str(excinfo.value)
    
    def test_is_available_registered(self):
        """测试检查已注册引擎可用性"""
        from core.inference.engine_factory import EngineFactory
        
        EngineFactory._registry = {}
        EngineFactory._availability_cache = {}
        EngineFactory.register("mock", MockEngine)
        
        available = EngineFactory.is_available("mock")
        assert available is True
    
    def test_is_available_unregistered(self):
        """测试检查未注册引擎可用性"""
        from core.inference.engine_factory import EngineFactory
        
        EngineFactory._registry = {}
        EngineFactory._availability_cache = {}
        
        available = EngineFactory.is_available("nonexistent")
        assert available is False
    
    def test_get_available_engines(self):
        """测试获取可用引擎列表"""
        from core.inference.engine_factory import EngineFactory
        
        EngineFactory._registry = {}
        EngineFactory._availability_cache = {}
        EngineFactory.register("mock", MockEngine)
        
        engines = EngineFactory.get_available_engines()
        assert "mock" in engines
        assert engines["mock"]["available"] is True
    
    def test_clear_cache(self):
        """测试清除缓存"""
        from core.inference.engine_factory import EngineFactory
        
        EngineFactory._availability_cache["test"] = True
        EngineFactory.clear_cache()
        
        assert len(EngineFactory._availability_cache) == 0


class TestChatTemplate:
    """聊天模板测试"""
    
    def test_apply_chat_template_qwen(self):
        """测试 Qwen 模型聊天模板"""
        config = MockEngineConfig(model_id="Qwen/Qwen2.5-7B-Instruct")
        engine = MockEngine(config)
        
        formatted = engine.apply_chat_template("Hello")
        assert "<|im_start|>user" in formatted
        assert "<|im_end|>" in formatted
    
    def test_apply_chat_template_qwen3(self):
        """测试 Qwen3 模型聊天模板"""
        config = MockEngineConfig(model_id="Qwen/Qwen3.5-7B-Instruct")
        engine = MockEngine(config)
        
        formatted = engine.apply_chat_template("Hello")
        assert "<|im_start|>user" in formatted
    
    def test_apply_chat_template_already_formatted(self):
        """测试已格式化的文本"""
        config = MockEngineConfig(model_id="Qwen/Qwen2.5-7B-Instruct")
        engine = MockEngine(config)
        
        already_formatted = "<|im_start|>user\nHello<|im_end|>\n<|im_start|>assistant\n"
        formatted = engine.apply_chat_template(already_formatted)
        assert formatted == already_formatted


class TestFlashAttention:
    """Flash Attention 检测测试"""
    
    def test_get_gpu_compute_capability_no_cuda(self):
        """测试无 CUDA 环境"""
        with patch("torch.cuda.is_available", return_value=False):
            from core.inference.flash_attention import get_gpu_compute_capability
            capability = get_gpu_compute_capability()
            assert capability is None
    
    def test_get_gpu_compute_capability_with_cuda(self):
        """测试有 CUDA 环境"""
        with patch("torch.cuda.is_available", return_value=True), \
             patch("torch.cuda.current_device", return_value=0), \
             patch("torch.cuda.get_device_capability", return_value=(8, 6)):
            from core.inference.flash_attention import get_gpu_compute_capability, reset_detection_cache
            reset_detection_cache()
            capability = get_gpu_compute_capability()
            assert capability == (8, 6)
    
    def test_is_gpu_architecture_supported_ampere(self):
        """测试 Ampere 架构支持"""
        with patch("core.inference.flash_attention.get_gpu_compute_capability", return_value=(8, 0)):
            from core.inference.flash_attention import is_gpu_architecture_supported, reset_detection_cache
            reset_detection_cache()
            supported = is_gpu_architecture_supported()
            assert supported is True
    
    def test_is_gpu_architecture_supported_older_gpu(self):
        """测试旧架构不支持"""
        with patch("core.inference.flash_attention.get_gpu_compute_capability", return_value=(7, 5)):
            from core.inference.flash_attention import is_gpu_architecture_supported, reset_detection_cache
            reset_detection_cache()
            supported = is_gpu_architecture_supported()
            assert supported is False
    
    def test_is_flash_attn_2_installed_true(self):
        """测试 Flash Attention 2 已安装"""
        mock_flash_attn = MagicMock()
        mock_flash_attn.__version__ = "2.0.0"
        
        with patch.dict("sys.modules", {"flash_attn": mock_flash_attn}):
            from core.inference.flash_attention import is_flash_attn_2_installed, reset_detection_cache
            reset_detection_cache()
            installed, version = is_flash_attn_2_installed()
            assert installed is True
            assert version == "2.0.0"
    
    def test_is_flash_attn_2_installed_false(self):
        """测试 Flash Attention 2 未安装"""
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
        """测试强制使用 eager 实现"""
        from core.inference.flash_attention import get_attention_implementation
        impl = get_attention_implementation(force_eager=True)
        assert impl == "eager"
    
    def test_get_flash_attention_info(self):
        """测试获取 Flash Attention 信息"""
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
        """测试重置检测缓存"""
        from core.inference.flash_attention import reset_detection_cache
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
        from core.inference.engine_factory import EngineFactory
        EngineFactory._registry = {}
        EngineFactory._availability_cache = {}
        EngineFactory.register("mock", MockEngine)
    
    @patch("core.inference.engine_factory.get_settings")
    def test_create_engine_convenience_function(self, mock_get_settings):
        """测试便捷创建引擎函数"""
        from core.inference.engine_factory import create_engine, EngineFactory
        
        mock_settings = MagicMock()
        mock_settings.inference_backend = "mock"
        mock_get_settings.return_value = mock_settings
        
        engine = create_engine("test_model", engine_type="mock")
        assert isinstance(engine, MockEngine)
        assert engine.config.model_id == "test_model"
    
    @patch("core.inference.engine_factory.get_settings")
    def test_create_engine_with_fallback_convenience(self, mock_get_settings):
        """测试带回退的便捷创建引擎函数"""
        from core.inference.engine_factory import create_engine_with_fallback, EngineFactory
        
        mock_settings = MagicMock()
        mock_settings.inference_backend = "mock"
        mock_get_settings.return_value = mock_settings
        
        engine = create_engine_with_fallback("test_model", preferred_type="mock")
        assert isinstance(engine, MockEngine)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
