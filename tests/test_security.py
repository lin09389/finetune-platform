"""
安全模块测试 - 速率限制和 JWT 认证

测试覆盖：
- 速率限制器功能
- JWT Token 生成和验证
- Token 黑名单
- 角色权限系统
"""
import pytest
import sys
import time
from pathlib import Path
from datetime import datetime, timedelta

# 添加项目路径
server_path = Path(__file__).parent.parent / "server"
sys.path.insert(0, str(server_path))

from security.rate_limiter import RateLimiter, RateLimitConfig
from security.jwt_auth import JWTAuth, TokenPayload, Role
from security.auth_middleware import RateLimitMiddleware


# ==================== 速率限制器测试 ====================

class TestRateLimiter:
    """速率限制器测试"""

    def test_rate_limit_config_parse(self):
        """测试速率限制配置解析"""
        config = RateLimitConfig.parse("100/minute")
        assert config.requests == 100
        assert config.window == 60

        config = RateLimitConfig.parse("5/second")
        assert config.requests == 5
        assert config.window == 1

        config = RateLimitConfig.parse("1000/hour")
        assert config.requests == 1000
        assert config.window == 3600

    def test_rate_limit_config_invalid(self):
        """测试无效配置"""
        with pytest.raises(ValueError):
            RateLimitConfig.parse("invalid")

    def test_rate_limiter_basic(self):
        """测试基本速率限制"""
        limiter = RateLimiter(default_limit="5/minute")
        
        # 前 5 次请求应该允许
        for i in range(5):
            allowed, info = limiter.is_allowed("user1", "/api/test")
            assert allowed is True
        
        # 第 6 次请求应该被拒绝
        allowed, info = limiter.is_allowed("user1", "/api/test")
        assert allowed is False
        assert info['error'] == 'rate_limit_exceeded'

    def test_rate_limiter_different_endpoints(self):
        """测试不同端点的限制"""
        limiter = RateLimiter(
            default_limit="10/minute",
            api_limits={"/api/login": "3/minute"}
        )
        
        # 登录接口限制更严格
        for i in range(3):
            allowed, _ = limiter.is_allowed("user1", "/api/login")
            assert allowed is True
        
        allowed, info = limiter.is_allowed("user1", "/api/login")
        assert allowed is False
        
        # 其他接口限制较宽松
        for i in range(10):
            allowed, _ = limiter.is_allowed("user1", "/api/chat")
            assert allowed is True

    def test_rate_limiter_ban(self):
        """测试封禁机制"""
        limiter = RateLimiter(
            default_limit="2/minute",
            ban_threshold=3,
            ban_duration=60
        )
        
        # 触发 3 次违规
        for _ in range(5):  # 超过限制
            limiter.is_allowed("user1", "/api/test")
        
        # 现在应该被封禁
        allowed, info = limiter.is_allowed("user1", "/api/test")
        assert allowed is False
        assert info['error'] == 'rate_limit_banned'

    def test_rate_limiter_reset(self):
        """测试重置"""
        limiter = RateLimiter(default_limit="5/minute")
        
        # 使用一些配额
        for i in range(3):
            limiter.is_allowed("user1", "/api/test")
        
        # 重置
        limiter.reset("user1", "/api/test")
        
        # 应该恢复配额
        status = limiter.get_status("user1", "/api/test")
        assert status['remaining'] == 5

    def test_rate_limiter_manual_ban(self):
        """测试手动封禁"""
        limiter = RateLimiter()
        
        # 手动封禁
        limiter.ban("user1", duration=3600)
        
        # 应该被拒绝（需要指定相同的端点或空端点）
        allowed, info = limiter.is_allowed("user1", "")
        assert allowed is False
        assert info['error'] == 'rate_limit_banned'

    def test_rate_limiter_stats(self):
        """测试统计信息"""
        limiter = RateLimiter(
            default_limit="10/minute",
            api_limits={"/api/login": "5/minute"}
        )
        
        # 使用一些配额
        for i in range(3):
            limiter.is_allowed("user1", "/api/test")
        
        stats = limiter.get_stats()
        assert 'total_identifiers' in stats
        assert 'default_limit' in stats
        assert '/api/login' in stats['api_limits']


# ==================== JWT 认证测试 ====================

class TestJWTAuth:
    """JWT 认证测试"""

    def setup_method(self):
        """每个测试前执行"""
        self.auth = JWTAuth(
            secret_key="test-secret-key-123456",
            access_token_expire_minutes=5,
            refresh_token_expire_days=1
        )

    def test_register_user(self):
        """测试用户注册"""
        user_id = self.auth.register_user(
            username="testuser",
            password="password123",
            role=Role.USER
        )
        
        assert user_id is not None
        assert len(user_id) == 16

    def test_register_duplicate_user(self):
        """测试重复注册"""
        user_id1 = self.auth.register_user("testuser", "password123")
        user_id2 = self.auth.register_user("testuser", "password123")
        
        assert user_id1 is not None
        assert user_id2 is None  # 重复注册失败

    def test_authenticate_success(self):
        """测试认证成功"""
        self.auth.register_user("testuser", "password123")
        
        user_id = self.auth.authenticate("testuser", "password123")
        assert user_id is not None

    def test_authenticate_failure(self):
        """测试认证失败"""
        self.auth.register_user("testuser", "password123")
        
        user_id = self.auth.authenticate("testuser", "wrongpassword")
        assert user_id is None

    def test_create_token_pair(self):
        """测试创建 Token 对"""
        user_id = self.auth.register_user("testuser", "password123")
        
        tokens = self.auth.create_token_pair(user_id)
        
        assert tokens.access_token is not None
        assert tokens.refresh_token is not None
        assert tokens.token_type == "Bearer"
        assert tokens.expires_in == 300  # 5 分钟

    def test_verify_token_success(self):
        """测试验证 Token 成功"""
        user_id = self.auth.register_user("testuser", "password123")
        tokens = self.auth.create_token_pair(user_id)
        
        payload = self.auth.verify_token(tokens.access_token)
        
        assert payload.user_id == user_id
        assert payload.username == "testuser"
        assert payload.role == Role.USER

    def test_verify_token_expired(self):
        """测试验证过期 Token"""
        # 使用更短的过期时间创建 Token
        from security.jwt_auth import TokenPayload
        import jwt
        
        now = datetime.now()
        payload = TokenPayload(
            user_id="test",
            username="test",
            role=Role.USER,
            iat=now - timedelta(minutes=10),
            exp=now - timedelta(seconds=1),  # 1 秒前过期
            jti="test-jti"
        )
        
        token = jwt.encode(payload.to_dict(), self.auth.secret_key, algorithm="HS256")
        
        with pytest.raises(jwt.ExpiredSignatureError):
            self.auth.verify_token(token)

    def test_refresh_token(self):
        """测试刷新 Token"""
        user_id = self.auth.register_user("testuser", "password123")
        tokens = self.auth.create_token_pair(user_id)
        
        # 使用 Refresh Token 刷新
        new_tokens = self.auth.refresh_access_token(tokens.refresh_token)
        
        assert new_tokens.access_token != tokens.access_token
        assert new_tokens.refresh_token != tokens.refresh_token

    def test_logout(self):
        """测试注销"""
        user_id = self.auth.register_user("testuser", "password123")
        tokens = self.auth.create_token_pair(user_id)
        
        # 注销
        self.auth.logout(tokens.access_token, tokens.refresh_token)
        
        # Token 应该在黑名单中
        with pytest.raises(ValueError, match="已被注销"):
            self.auth.verify_token(tokens.access_token)

    def test_has_permission(self):
        """测试权限检查"""
        user_id = self.auth.register_user(
            "testuser",
            "password123",
            role=Role.USER,
            permissions=["read", "write"]
        )
        tokens = self.auth.create_token_pair(user_id)
        payload = self.auth.verify_token(tokens.access_token)
        
        assert self.auth.has_permission(payload, "read") is True
        assert self.auth.has_permission(payload, "delete") is False

    def test_has_role(self):
        """测试角色检查"""
        user_id = self.auth.register_user("admin", "password123", role=Role.ADMIN)
        tokens = self.auth.create_token_pair(user_id)
        payload = self.auth.verify_token(tokens.access_token)
        
        assert self.auth.has_role(payload, Role.USER) is True
        assert self.auth.has_role(payload, Role.ADMIN) is True
        assert self.auth.has_role(payload, Role.SUPER_ADMIN) is False

    def test_token_payload_serialization(self):
        """测试 Token 载荷序列化"""
        now = datetime.now()
        payload = TokenPayload(
            user_id="test",
            username="testuser",
            role=Role.ADMIN,
            permissions=["read", "write"],
            iat=now,
            exp=now + timedelta(hours=1),
            jti="test-jti"
        )
        
        data = payload.to_dict()
        # 注意：to_dict 会将 datetime 转为时间戳
        restored = TokenPayload.from_dict(data)
        
        assert restored.user_id == payload.user_id
        assert restored.username == payload.username
        assert restored.role == payload.role
        assert restored.permissions == payload.permissions

    def test_get_user_info(self):
        """测试获取用户信息"""
        user_id = self.auth.register_user(
            "testuser",
            "password123",
            role=Role.USER,
            permissions=["read"]
        )
        
        info = self.auth.get_user_info(user_id)
        
        assert info is not None
        assert info['username'] == 'testuser'
        assert 'password' not in info  # 密码不应返回

    def test_get_stats(self):
        """测试统计信息"""
        self.auth.register_user("user1", "pass1")
        self.auth.register_user("user2", "pass2")
        
        stats = self.auth.get_stats()
        
        assert stats['total_users'] == 2
        assert 'blacklist_stats' in stats
        assert 'access_token_expire_minutes' in stats


# ==================== 集成测试 ====================

class TestIntegration:
    """集成测试"""

    def test_rate_limiter_with_jwt(self):
        """测试速率限制和 JWT 集成"""
        # 创建速率限制器
        limiter = RateLimiter(default_limit="10/minute")
        
        # 创建 JWT 认证
        auth = JWTAuth(secret_key="test-key")
        
        # 注册用户并创建 Token
        user_id = auth.register_user("testuser", "password")
        tokens = auth.create_token_pair(user_id)
        
        # 验证 Token
        payload = auth.verify_token(tokens.access_token)
        
        # 使用用户 ID 进行速率限制
        for i in range(10):
            allowed, _ = limiter.is_allowed(f"user:{payload.user_id}", "/api/chat")
            assert allowed is True
        
        # 超过限制
        allowed, info = limiter.is_allowed(f"user:{payload.user_id}", "/api/chat")
        assert allowed is False


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
