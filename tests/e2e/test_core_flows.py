"""
核心功能 E2E 测试
"""
import re

import pytest
from playwright.sync_api import Page, expect

BASE_URL = "http://localhost:5173"


class TestHealthCheck:
    """健康检查测试"""
    
    def test_backend_health(self, api_context):
        """测试后端健康检查"""
        response = api_context.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
    
    def test_api_info(self, api_context):
        """测试 API 信息"""
        response = api_context.get("/api/info")
        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "version" in data


class TestCUAOperations:
    """CUA 操作测试"""
    
    def test_screenshot(self, api_context):
        """测试截图功能"""
        response = api_context.post("/cua/screenshot", json={"monitor": 0})
        assert response.status_code == 200
        data = response.json()
        assert "width" in data
        assert "height" in data
        assert data["width"] > 0
        assert data["height"] > 0
    
    def test_mouse_position(self, api_context):
        """测试获取鼠标位置"""
        response = api_context.get("/cua/mouse/position")
        assert response.status_code == 200
        data = response.json()
        assert "x" in data
        assert "y" in data
    
    def test_window_list(self, api_context):
        """测试窗口列表"""
        response = api_context.get("/cua/window/list")
        assert response.status_code == 200
        data = response.json()
        assert "windows" in data
        assert isinstance(data["windows"], list)
    
    def test_safety_status(self, api_context):
        """测试安全状态"""
        response = api_context.get("/cua/safety/status")
        assert response.status_code == 200
        data = response.json()
        assert "permission_level" in data


class TestSmartAgent:
    """智能 Agent 测试"""
    
    def test_screenshot_intent(self, api_context):
        """测试截图意图检测"""
        response = api_context.post(
            "/smart-agent/smart-execute",
            json={
                "message": "截图",
                "auto_execute": True
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["detected"] is True
        assert data["action"] == "screenshot"
    
    def test_mouse_position_intent(self, api_context):
        """测试鼠标位置意图检测"""
        response = api_context.post(
            "/smart-agent/smart-execute",
            json={
                "message": "鼠标在哪里",
                "auto_execute": True
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["detected"] is True
        assert data["action"] == "mouse_position"
    
    def test_window_list_intent(self, api_context):
        """测试窗口列表意图检测"""
        response = api_context.post(
            "/smart-agent/smart-execute",
            json={
                "message": "列出所有窗口",
                "auto_execute": True
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["detected"] is True
        assert data["action"] == "window_list"
    
    def test_supported_operations(self, api_context):
        """测试支持的操作列表"""
        response = api_context.get("/smart-agent/supported-operations")
        assert response.status_code == 200
        data = response.json()
        assert "cua_operations" in data
        assert "file_operations" in data


class TestFileOperations:
    """文件操作测试"""
    
    def test_create_and_read_file(self, api_context):
        """测试创建和读取文件"""
        # 创建文件
        create_response = api_context.post(
            "/smart-agent/smart-execute",
            json={
                "message": "创建 e2e_test.txt 文件",
                "auto_execute": True,
                "auto_confirm_safe": True
            }
        )
        assert create_response.status_code == 200
        
        # 写入内容
        write_response = api_context.post(
            "/smart-agent/smart-execute",
            json={
                "message": "把 e2e_test.txt 的内容改成 Hello E2E Test",
                "auto_execute": True,
                "auto_confirm_safe": True
            }
        )
        assert write_response.status_code == 200
        
        # 读取文件
        read_response = api_context.post(
            "/smart-agent/smart-execute",
            json={
                "message": "读取 e2e_test.txt",
                "auto_execute": True
            }
        )
        assert read_response.status_code == 200
        data = read_response.json()
        assert data["success"] is True


class TestSkillsAPI:
    """技能系统测试"""
    
    def test_list_skills(self, api_context):
        """测试技能列表"""
        response = api_context.get("/skills")
        assert response.status_code == 200
        data = response.json()
        assert "skills" in data
        assert isinstance(data["skills"], list)
    
    def test_skill_stats(self, api_context):
        """测试技能统计"""
        response = api_context.get("/skills/stats")
        assert response.status_code == 200
        data = response.json()
        assert "total_skills" in data


class TestMCPAPI:
    """MCP 模块测试"""
    
    def test_mcp_status(self, api_context):
        """测试 MCP 状态"""
        response = api_context.get("/mcp/status")
        assert response.status_code == 200
        data = response.json()
        assert "total_servers" in data
        assert "total_tools" in data


class TestFrontendPages:
    """前端页面测试"""
    
    @pytest.mark.skip(reason="需要启动前端服务")
    def test_home_page(self, page: Page):
        """测试首页加载"""
        page.goto(BASE_URL)
        expect(page).to_have_title(re.compile("Finetune Platform"))
    
    @pytest.mark.skip(reason="需要启动前端服务")
    def test_cua_control_page(self, page: Page):
        """测试 CUA 控制页面"""
        page.goto(f"{BASE_URL}/cua-control")
        expect(page.locator("text=CUA")).to_be_visible()
    
    @pytest.mark.skip(reason="需要启动前端服务")
    def test_mcp_tools_page(self, page: Page):
        """测试 MCP 工具页面"""
        page.goto(f"{BASE_URL}/mcp")
        expect(page.locator("text=MCP")).to_be_visible()
