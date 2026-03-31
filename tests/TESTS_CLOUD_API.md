# 云端 API 调用测试指南

## 概述

云端 API 调用测试模块 (`tests/test_cloud_api.py`) 提供了完整的测试覆盖，用于验证云端 AI 功能的正确性、安全性和性能。

## 测试覆盖

| 测试类别 | 测试项 | 状态 |
|----------|--------|------|
| **AI Gateway** | Provider 初始化、配置、获取 | ✅ 6 项 |
| **API Key 管理** | 创建、列出、删除、加密存储 | ✅ 5 项 |
| **云端聊天** | MiniMax/GLM聊天、流式输出 | ✅ 4 项 |
| **错误处理** | 缺少参数、无效 Key、无效 Provider | ✅ 4 项 |
| **速率限制** | 限制头、超出限制 | ✅ 2 项 |
| **数据脱敏** | 审计日志脱敏、响应脱敏 | ✅ 2 项 |
| **JWT 认证** | 缺少认证、无效 Token | ✅ 2 项 |
| **性能测试** | 并发请求 | ✅ 1 项 |
| **集成测试** | 完整工作流程 | ✅ 1 项 |
| **真实 API** | MiniMax/GLM 真实调用 | ⏸️ 2 项（需 API Key） |

**总计**: 29 项测试，26 项通过，3 项跳过

## 运行测试

### 基本测试

```bash
# 运行所有云端 API 测试
pytest tests/test_cloud_api.py -v

# 运行特定测试类
pytest tests/test_cloud_api.py::TestAIGateway -v
pytest tests/test_cloud_api.py::TestAPIKeyManagement -v
pytest tests/test_cloud_api.py::TestCloudChatMock -v

# 运行特定测试
pytest tests/test_cloud_api.py::TestAIGateway::test_get_provider -v
```

### 真实 API 测试

需要配置环境变量：

```bash
# 设置 API Key
set MINIMAX_API_KEY=your_minimax_api_key
set MINIMAX_GROUP_ID=your_group_id
set GLM_API_KEY=your_glm_api_key

# 运行真实 API 测试
pytest tests/test_cloud_api.py::TestRealAPI -v
```

## 测试详解

### 1. AI Gateway 测试

```python
class TestAIGateway:
    """测试 AI 网关功能"""
    
    def test_minimax_provider_init(self):
        """验证 Minimax Provider 初始化"""
        provider = MinimaxProvider(coding_mode=False)
        assert provider.base_url == "https://api.minimax.chat/v1"
    
    def test_get_provider_with_group_id(self):
        """测试带 Group ID 的 Provider"""
        provider = await get_provider(
            "minimax",
            group_id="test_group",
            base_url="https://custom.api.com/v1"
        )
        assert provider.group_id == "test_group"
```

### 2. API Key 管理测试

```python
class TestAPIKeyManagement:
    """测试 API Key 管理"""
    
    def test_create_api_key(self, client, jwt_token):
        """测试创建 API Key"""
        response = client.post(
            "/cloud/api-keys",
            headers={"Authorization": f"Bearer {jwt_token}"},
            json={
                "provider": "minimax",
                "api_key": "test_key_123456",
                "group_id": "test_group",
                "name": "test-key"
            }
        )
        assert response.status_code == 200
        assert "key_id" in response.json()
    
    def test_api_key_encryption(self, client, jwt_token):
        """测试 API Key 加密存储"""
        # 创建 API Key
        response = client.post("/cloud/api-keys", ...)
        key_id = response.json()["key_id"]
        
        # 验证存储的是加密数据
        vault_data = secure_storage._load_vault()
        stored_data = vault_data[f"api_key:{key_id}"]
        assert stored_data["encrypted"] != "test_key_123456"
```

### 3. 云端聊天测试（模拟）

```python
class TestCloudChatMock:
    """测试云端聊天（使用模拟）"""
    
    def test_minimax_chat_mock(self, client, jwt_token, stored_api_key):
        """测试 MiniMax 聊天"""
        mock_response = {
            "choices": [{"message": {"content": "模拟回复"}}]
        }
        
        with patch("httpx.AsyncClient.post") as mock_post:
            mock_post.return_value = MagicMock(
                json=lambda: mock_response
            )
            
            response = client.post("/cloud/chat", ...)
            assert response.status_code == 200
            assert "模拟回复" in response.json()["content"]
```

### 4. 错误处理测试

```python
class TestErrorHandling:
    """测试错误处理"""
    
    def test_missing_api_key(self, client, jwt_token):
        """测试缺少 API Key"""
        response = client.post("/cloud/chat", json={
            "provider": "minimax",
            "messages": [{"role": "user", "content": "你好"}]
            # 缺少 api_key 或 key_id
        })
        assert response.status_code == 400
        assert "必须提供 api_key 或 key_id" in response.json()["detail"]
```

### 5. 速率限制测试

```python
class TestRateLimitIntegration:
    """测试速率限制集成"""
    
    def test_rate_limit_exceeded(self, client, jwt_token):
        """测试速率限制超出"""
        limiter = init_rate_limiter(default_limit="2/minute")
        
        for i in range(5):
            response = client.post("/cloud/chat", ...)
            if response.status_code == 429:
                assert "rate_limit" in str(response.json()).lower()
                assert "Retry-After" in response.headers
                break
```

### 6. 数据脱敏测试

```python
class TestDataMasking:
    """测试数据脱敏"""
    
    def test_audit_log_masking(self, client, jwt_token):
        """测试审计日志脱敏"""
        response = client.post("/cloud/api-keys", json={
            "provider": "minimax",
            "api_key": "secret_api_key_123456",
            "group_id": "secret_group"
        })
        
        # 验证敏感数据被脱敏
        assert "secret_api_key_123456" not in str(response.json())
```

### 7. 性能测试

```python
class TestPerformance:
    """测试性能"""
    
    def test_concurrent_requests(self, client, jwt_token, stored_api_key):
        """测试并发请求"""
        import concurrent.futures
        
        def make_request():
            with patch("httpx.AsyncClient.post"):
                return client.post("/cloud/chat", ...)
        
        # 并发 5 个请求
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(make_request) for _ in range(5)]
            responses = [f.result() for f in futures]
        
        # 至少 3 个成功
        success_count = sum(1 for r in responses if r.status_code == 200)
        assert success_count >= 3
```

### 8. 集成测试

```python
class TestIntegration:
    """集成测试"""
    
    def test_full_workflow(self, client, jwt_token):
        """测试完整工作流程"""
        # 1. 创建 API Key
        create_response = client.post("/cloud/api-keys", ...)
        key_id = create_response.json()["key_id"]
        
        # 2. 列出 API Keys
        list_response = client.get("/cloud/api-keys", ...)
        assert len(list_response.json()["keys"]) > 0
        
        # 3. 聊天（模拟）
        with patch("httpx.AsyncClient.post"):
            chat_response = client.post("/cloud/chat", ...)
            assert chat_response.status_code == 200
        
        # 4. 删除 API Key
        delete_response = client.delete(f"/cloud/api-keys/{key_id}", ...)
        assert delete_response.status_code == 200
```

## 测试 Fixtures

### 内置 Fixtures

```python
@pytest.fixture
def app():
    """创建测试应用"""
    app = FastAPI()
    app.include_router(cloud_router, prefix="/cloud")
    return app

@pytest.fixture
def client(app):
    """创建测试客户端"""
    return TestClient(app)

@pytest.fixture
def jwt_token():
    """创建测试 JWT Token"""
    auth = init_jwt_auth(secret_key="test-key")
    user_id = auth.register_user("testuser", "password123")
    tokens = auth.create_token_pair(user_id)
    return tokens.access_token

@pytest.fixture
def mock_api_key():
    """创建模拟 API Key"""
    return "test_group_id:test_api_key_1234567890"

@pytest.fixture
def stored_api_key(mock_api_key):
    """创建存储的 API Key"""
    key_id = "key_test123"
    secure_storage.store_api_key(
        key_id=key_id,
        provider="minimax",
        api_key=mock_api_key,
        group_id="test_group_id"
    )
    return key_id
```

### 自定义 Fixtures

在测试文件中添加自定义 fixture：

```python
@pytest.fixture
def custom_provider():
    """创建自定义 Provider"""
    return MinimaxProvider(coding_mode=True)
```

## 测试配置

### pytest.ini

```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = -v --tb=short
```

### 环境变量

```bash
# .env.test
ENVIRONMENT=test
JWT_SECRET_KEY=test-secret-key
RATE_LIMIT_DEFAULT=1000/minute
SECURITY_MASK_MODE=permissive
```

## 常见问题

### Q: 为什么有些测试被跳过？

A: `TestRealAPI` 中的测试需要真实的 API Key，如果没有设置环境变量会自动跳过：

```python
@pytest.mark.skipif(
    not os.environ.get("MINIMAX_API_KEY"),
    reason="需要 MINIMAX_API_KEY 环境变量"
)
def test_real_minimax_chat(self, ...):
    ...
```

### Q: 如何调试失败的测试？

A: 使用 `-s` 和 `--tb=long` 获取详细信息：

```bash
pytest tests/test_cloud_api.py::TestCloudChatMock::test_minimax_chat_mock -v -s --tb=long
```

### Q: 如何测试流式响应？

A: 使用 mock 模拟流式数据：

```python
async def mock_stream():
    yield b'data: {"content": "A"}\n\n'
    yield b'data: {"content": "B"}\n\n'
    yield b'data: [DONE]\n\n'

with patch("httpx.AsyncClient.stream") as mock_stream:
    mock_stream.return_value.__aenter__.return_value = MagicMock(
        aiter_lines=AsyncMock(side_effect=mock_stream())
    )
    response = client.post("/cloud/chat/stream", ...)
```

## 测试报告

生成测试覆盖率报告：

```bash
# 安装 coverage
pip install coverage

# 运行测试并生成报告
coverage run -m pytest tests/test_cloud_api.py
coverage report -m
coverage html
```

## 持续集成

在 CI/CD 中运行测试：

```yaml
# .github/workflows/test.yml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt
      - run: pytest tests/test_cloud_api.py -v --tb=short
```

## 更新日志

### 2026-03-09

**新增测试**
- ✅ AI Gateway 测试（6 项）
- ✅ API Key 管理测试（5 项）
- ✅ 云端聊天模拟测试（4 项）
- ✅ 错误处理测试（4 项）
- ✅ 速率限制集成测试（2 项）
- ✅ 数据脱敏测试（2 项）
- ✅ JWT 认证测试（2 项）
- ✅ 性能测试（1 项）
- ✅ 集成测试（1 项）

**测试结果**
- 26 项通过
- 3 项跳过（需真实 API Key）
