"""
推理引擎单元测试
"""

import pytest

from core.inference.engine_base import (
    BaseInferenceEngine,
    ChatMessage,
    ChatRequest,
    InferenceBackend,
    InferenceRequest,
    InferenceResponse,
)
from core.inference.engine_factory import (
    InferenceEngineFactory,
)


class MockInferenceEngine(BaseInferenceEngine):
    """Mock 推理引擎"""

    @property
    def backend(self) -> InferenceBackend:
        return InferenceBackend.CUSTOM

    @property
    def name(self) -> str:
        return "Mock Engine"

    def is_available(self) -> bool:
        return True

    async def generate(self, request: InferenceRequest) -> InferenceResponse:
        return InferenceResponse(
            text=f"Generated: {request.prompt[:20]}...",
            tokens_generated=10,
            processing_time_ms=100.0,
            model_id=request.model_id,
            backend=self.backend.value,
        )

    async def chat(self, request: ChatRequest) -> InferenceResponse:
        return InferenceResponse(
            text="Chat response",
            tokens_generated=5,
            processing_time_ms=50.0,
            model_id=request.model_id,
            backend=self.backend.value,
        )

    def get_available_models(self) -> list:
        return ["mock-model-1", "mock-model-2"]

    def load_model(self, model_id: str) -> bool:
        self._loaded_models[model_id] = {"id": model_id}
        return True

    def unload_model(self, model_id: str) -> bool:
        if model_id in self._loaded_models:
            del self._loaded_models[model_id]
        return True


class TestInferenceRequest:
    """推理请求测试"""

    def test_create_request(self):
        """测试创建请求"""
        request = InferenceRequest(
            model_id="test-model",
            prompt="Hello",
        )

        assert request.model_id == "test-model"
        assert request.prompt == "Hello"
        assert request.max_tokens == 1024
        assert request.temperature == 0.7

    def test_request_with_custom_params(self):
        """测试自定义参数"""
        request = InferenceRequest(
            model_id="test-model",
            prompt="Hello",
            max_tokens=2048,
            temperature=0.5,
            top_p=0.8,
        )

        assert request.max_tokens == 2048
        assert request.temperature == 0.5
        assert request.top_p == 0.8


class TestInferenceResponse:
    """推理响应测试"""

    def test_create_response(self):
        """测试创建响应"""
        response = InferenceResponse(
            text="Generated text",
            tokens_generated=10,
            processing_time_ms=100.0,
            model_id="test-model",
            backend="mock",
        )

        assert response.text == "Generated text"
        assert response.tokens_generated == 10
        assert response.finish_reason == "stop"

    def test_response_to_dict(self):
        """测试响应转字典"""
        response = InferenceResponse(
            text="Test",
            tokens_generated=5,
            processing_time_ms=50.0,
            model_id="model",
            backend="test",
        )

        data = response.to_dict()

        assert data["text"] == "Test"
        assert data["tokens_generated"] == 5
        assert data["backend"] == "test"


class TestMockInferenceEngine:
    """Mock 推理引擎测试"""

    @pytest.fixture
    def engine(self):
        return MockInferenceEngine()

    def test_engine_properties(self, engine):
        """测试引擎属性"""
        assert engine.backend == InferenceBackend.CUSTOM
        assert engine.name == "Mock Engine"
        assert engine.is_available() is True

    def test_get_available_models(self, engine):
        """测试获取可用模型"""
        models = engine.get_available_models()

        assert len(models) == 2
        assert "mock-model-1" in models

    def test_load_model(self, engine):
        """测试加载模型"""
        result = engine.load_model("new-model")

        assert result is True
        assert "new-model" in engine._loaded_models

    def test_unload_model(self, engine):
        """测试卸载模型"""
        engine.load_model("test-model")
        result = engine.unload_model("test-model")

        assert result is True
        assert "test-model" not in engine._loaded_models

    @pytest.mark.asyncio
    async def test_generate(self, engine):
        """测试生成"""
        request = InferenceRequest(
            model_id="mock-model-1",
            prompt="Hello world",
        )

        response = await engine.generate(request)

        assert "Generated" in response.text
        assert response.tokens_generated == 10

    @pytest.mark.asyncio
    async def test_chat(self, engine):
        """测试聊天"""
        request = ChatRequest(
            model_id="mock-model-1",
            messages=[
                ChatMessage(role="user", content="Hello"),
            ],
        )

        response = await engine.chat(request)

        assert response.text == "Chat response"

    @pytest.mark.asyncio
    async def test_stream(self, engine):
        """测试流式生成"""
        request = InferenceRequest(
            model_id="mock-model-1",
            prompt="Hello",
        )

        chunks = []
        async for chunk in engine.stream(request):
            chunks.append(chunk)

        assert len(chunks) == 1
        assert chunks[0].done is True

    def test_get_stats(self, engine):
        """测试获取统计"""
        stats = engine.get_stats()

        assert stats["backend"] == "custom"
        assert stats["available"] is True


class TestInferenceEngineFactory:
    """推理引擎工厂测试"""

    def test_register_engine(self):
        """测试注册引擎"""
        InferenceEngineFactory.register("mock", MockInferenceEngine)

        assert "mock" in InferenceEngineFactory.get_registered_engines()

    def test_create_engine(self):
        """测试创建引擎"""
        InferenceEngineFactory.register("mock", MockInferenceEngine)

        engine = InferenceEngineFactory.create("mock")

        assert isinstance(engine, MockInferenceEngine)

    def test_get_or_create(self):
        """测试获取或创建"""
        InferenceEngineFactory.register("mock", MockInferenceEngine)

        engine1 = InferenceEngineFactory.get_or_create("mock")
        engine2 = InferenceEngineFactory.get_or_create("mock")

        assert engine1 is engine2

    def test_set_default(self):
        """测试设置默认引擎"""
        InferenceEngineFactory.register("mock", MockInferenceEngine)
        InferenceEngineFactory.set_default("mock")

        assert InferenceEngineFactory._default_engine == "mock"

    def test_get_default(self):
        """测试获取默认引擎"""
        InferenceEngineFactory.register("mock", MockInferenceEngine)
        InferenceEngineFactory.set_default("mock")

        engine = InferenceEngineFactory.get_default()

        assert isinstance(engine, MockInferenceEngine)

    def test_create_unregistered_engine(self):
        """测试创建未注册的引擎"""
        with pytest.raises(ValueError):
            InferenceEngineFactory.create("nonexistent")

    def test_get_stats(self):
        """测试获取统计"""
        InferenceEngineFactory.register("mock", MockInferenceEngine)

        stats = InferenceEngineFactory.get_stats()

        assert "mock" in stats["registered_engines"]
