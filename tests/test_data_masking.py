"""
数据脱敏模块测试

测试覆盖：
- API Key 脱敏
- 密码脱敏
- 邮箱脱敏
- 手机号脱敏
- IP 地址脱敏
- 文本脱敏
- 字典/列表递归脱敏
- 审计日志脱敏集成
"""
import pytest
import sys
from pathlib import Path

# 添加项目路径
server_path = Path(__file__).parent.parent / "server"
sys.path.insert(0, str(server_path))

from security.data_masking import DataMasker, data_masker, mask, mask_text, mask_api_key


class TestDataMasker:
    """数据脱敏器测试"""

    def setup_method(self):
        """每个测试前执行"""
        self.masker = DataMasker(mode='strict')

    # ==================== API Key 脱敏测试 ====================

    def test_mask_api_key_simple(self):
        """测试简单 API Key 脱敏"""
        api_key = "sk-1234567890abcdefghijklmnop"
        masked = self.masker.mask_api_key(api_key)
        
        assert masked[0:4] == api_key[0:4]  # 保留前 4 位
        assert masked[-4:] == api_key[-4:]  # 保留后 4 位
        assert '*' in masked  # 包含星号
        assert len(masked) == len(api_key)

    def test_mask_api_key_minimax_format(self):
        """测试 MiniMax 格式 API Key 脱敏（group_id:api_key）"""
        api_key = "1234567890:abcdefghijklmnopqrstuvwx"
        masked = self.masker.mask_api_key(api_key)
        
        assert ':' in masked  # 保留分隔符
        assert '*' in masked  # 包含星号

    def test_mask_api_key_short(self):
        """测试短 API Key 脱敏"""
        api_key = "short"
        masked = self.masker.mask_api_key(api_key)
        
        assert '*' in masked

    def test_mask_api_key_empty(self):
        """测试空 API Key"""
        masked = self.masker.mask_api_key("")
        assert masked == '*' * 8

    # ==================== 密码脱敏测试 ====================

    def test_mask_password(self):
        """测试密码脱敏"""
        password = "MySecretPassword123"
        masked = self.masker.mask_password(password)
        
        assert masked == '*' * len(password)
        assert '*' * len(password) == masked

    def test_mask_password_empty(self):
        """测试空密码"""
        masked = self.masker.mask_password("")
        assert masked == '*' * 8

    # ==================== 邮箱脱敏测试 ====================

    def test_mask_email(self):
        """测试邮箱脱敏"""
        email = "user@example.com"
        masked = self.masker.mask_email(email)
        
        assert masked.startswith("us")
        assert masked.endswith("@example.com")
        assert '**' in masked

    def test_mask_email_short(self):
        """测试短邮箱脱敏"""
        email = "a@b.com"
        masked = self.masker.mask_email(email)
        
        assert '*' in masked

    def test_mask_email_invalid(self):
        """测试无效邮箱"""
        masked = self.masker.mask_email("not-an-email")
        assert '*' in masked

    # ==================== 手机号脱敏测试 ====================

    def test_mask_phone(self):
        """测试手机号脱敏"""
        phone = "13812345678"
        masked = self.masker.mask_phone(phone)
        
        assert masked.startswith("138")
        assert masked.endswith("5678")
        assert masked == "138****5678"

    def test_mask_phone_short(self):
        """测试短手机号"""
        phone = "12345"
        masked = self.masker.mask_phone(phone)
        assert '*' in masked

    # ==================== IP 地址脱敏测试 ====================

    def test_mask_ip(self):
        """测试 IP 地址脱敏"""
        ip = "192.168.1.100"
        masked = self.masker.mask_ip(ip)
        
        assert masked.startswith("192.168.")
        assert masked.endswith("*.*")
        assert masked == "192.168.*.*"

    def test_mask_ip_invalid(self):
        """测试无效 IP"""
        masked = self.masker.mask_ip("not-an-ip")
        assert '*' in masked

    # ==================== 文本脱敏测试 ====================

    def test_mask_text_with_api_key(self):
        """测试文本中的 API Key 脱敏"""
        text = "My API key is: sk-1234567890abcdefghijklmnop"
        masked = self.masker.mask_text(text)
        
        # API Key 应该被脱敏
        assert '****' in masked or 'sk-1234' in masked
        # 原始完整 key 不应存在
        assert masked != text

    def test_mask_text_with_email(self):
        """测试文本中的邮箱脱敏"""
        text = "Contact me at user@example.com"
        masked = self.masker.mask_text(text)
        
        assert 'user@example.com' not in masked
        assert '@example.com' in masked

    def test_mask_text_with_phone(self):
        """测试文本中的手机号脱敏"""
        text = "My phone is 13812345678"
        masked = self.masker.mask_text(text)
        
        assert '13812345678' not in masked
        assert '138' in masked
        assert '5678' in masked

    def test_mask_text_with_ip(self):
        """测试文本中的 IP 脱敏"""
        text = "Server IP: 192.168.1.100"
        masked = self.masker.mask_text(text)
        
        assert '192.168.1.100' not in masked
        assert '192.168' in masked

    def test_mask_text_clean(self):
        """测试无敏感信息的文本"""
        text = "Hello, this is a normal text."
        masked = self.masker.mask_text(text)
        
        assert masked == text  # 不变

    # ==================== 字典脱敏测试 ====================

    def test_mask_dict_with_sensitive_keys(self):
        """测试字典敏感键脱敏"""
        data = {
            'username': 'john',
            'api_key': 'sk-1234567890abcdefghijklmnop',
            'password': 'MyPassword123',
            'email': 'john@example.com'
        }
        masked = self.masker.mask_dict(data)
        
        assert masked['username'] == 'john'  # 非敏感字段不变
        assert masked['api_key'] != 'sk-1234567890abcdefghijklmnop'
        assert masked['password'] == '*' * len('MyPassword123')
        # email 不是敏感键名，不会自动脱敏值
        assert masked['email'] == 'john@example.com'

    def test_mask_dict_nested(self):
        """测试嵌套字典脱敏"""
        data = {
            'user': {
                'name': 'john',
                'credentials': {
                    'api_key': 'sk-1234567890abcdefghijklmnop',
                    'token': 'abc123xyz789'
                }
            }
        }
        masked = self.masker.mask_dict(data)
        
        assert masked['user']['name'] == 'john'
        assert masked['user']['credentials']['api_key'] != 'sk-1234567890abcdefghijklmnop'
        assert masked['user']['credentials']['token'] != 'abc123xyz789'

    # ==================== 列表脱敏测试 ====================

    def test_mask_list_with_dicts(self):
        """测试包含字典的列表脱敏"""
        data = [
            {'name': 'user1', 'api_key': 'key123456789'},
            {'name': 'user2', 'api_key': 'key987654321'}
        ]
        masked = self.masker.mask_list(data)
        
        assert masked[0]['name'] == 'user1'
        assert masked[0]['api_key'] != 'key123456789'
        assert masked[1]['api_key'] != 'key987654321'

    # ==================== 智能脱敏测试 ====================

    def test_mask_auto_detect_dict(self):
        """测试自动检测字典脱敏"""
        data = {'config': 'value', 'secret_key': 'sensitive'}
        masked = self.masker.mask(data)
        
        assert isinstance(masked, dict)
        assert masked['secret_key'] != 'sensitive'

    def test_mask_auto_detect_list(self):
        """测试自动检测列表脱敏"""
        data = ['item1', 'item2']
        masked = self.masker.mask(data)
        
        assert isinstance(masked, list)
        assert len(masked) == 2

    def test_mask_auto_detect_string(self):
        """测试自动检测字符串脱敏"""
        text = "Contact: test@example.com"
        masked = self.masker.mask(text)
        
        assert isinstance(masked, str)
        assert 'test@example.com' not in masked

    def test_mask_none(self):
        """测试 None 值"""
        assert self.masker.mask(None) is None


class TestGlobalFunctions:
    """全局函数测试"""

    def test_mask_function(self):
        """测试 mask 全局函数"""
        data = {'api_key': 'sk-1234567890'}
        masked = mask(data)
        assert masked['api_key'] != 'sk-1234567890'

    def test_mask_text_function(self):
        """测试 mask_text 全局函数"""
        text = "Phone: 13812345678"
        masked = mask_text(text)
        assert '13812345678' not in masked

    def test_mask_api_key_function(self):
        """测试 mask_api_key 全局函数"""
        api_key = "sk-1234567890abcdefghijklmnop"
        masked = mask_api_key(api_key)
        assert '*' in masked


class TestAuditLogIntegration:
    """审计日志集成测试"""

    def test_audit_log_masks_sensitive_data(self, tmp_path):
        """测试审计日志自动脱敏"""
        from security.audit_log import AuditLogger
        from security.data_masking import data_masker

        # 创建临时日志目录
        log_dir = tmp_path / "audit"
        logger = AuditLogger(log_dir=str(log_dir))

        # 记录包含敏感信息的日志
        sensitive_data = {
            'api_key': 'sk-1234567890abcdefghijklmnop',
            'password': 'MyPassword123',
            'user': 'john'
        }
        logger.log_action(
            action='test_action',
            user_id='user123',
            details=sensitive_data
        )

        # 读取日志文件
        log_files = list(log_dir.glob("*.log"))
        assert len(log_files) > 0

        with open(log_files[0], 'r', encoding='utf-8') as f:
            log_content = f.read()

        # 验证敏感信息已被脱敏
        assert 'sk-1234567890abcdefghijklmnop' not in log_content
        assert 'MyPassword123' not in log_content
        assert '****' in log_content or '[MASKED]' in log_content


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
