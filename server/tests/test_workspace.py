"""
工作空间模块单元测试
"""
import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from workspace.models import (
    Project,
    ProjectStatus,
    Task,
    TaskPriority,
    TaskStatus,
    FileVersion,
)


class TestModels:
    """模型测试"""
    
    def test_project_creation(self):
        """测试项目创建"""
        project = Project(
            id="proj_1",
            name="Test Project",
            path="/tmp/test_project",
            description="A test project"
        )
        assert project.id == "proj_1"
        assert project.name == "Test Project"
        assert project.status == ProjectStatus.ACTIVE
    
    def test_project_model_dump(self):
        """测试项目序列化"""
        project = Project(
            id="proj_2",
            name="Test",
            path="/tmp/test"
        )
        data = project.model_dump()
        assert data["id"] == "proj_2"
        assert data["name"] == "Test"
    
    def test_task_creation(self):
        """测试任务创建"""
        task = Task(
            id="task_1",
            project_id="proj_1",
            title="Test Task",
            description="A test task"
        )
        assert task.id == "task_1"
        assert task.status == TaskStatus.PENDING
        assert task.priority == TaskPriority.NORMAL
    
    def test_task_model_dump(self):
        """测试任务序列化"""
        task = Task(
            id="task_2",
            project_id="proj_1",
            title="Test"
        )
        data = task.model_dump()
        assert data["id"] == "task_2"
        assert data["status"] == "pending"
    
    def test_file_version(self):
        """测试文件版本"""
        version = FileVersion(
            file_id="file_1",
            version_number=1,
            content_hash="abc123",
            size=100
        )
        assert version.version_number == 1
        assert version.content_hash == "abc123"
    
    def test_project_status_values(self):
        """测试项目状态枚举值"""
        assert ProjectStatus.ACTIVE.value == "active"
        assert ProjectStatus.ARCHIVED.value == "archived"
        assert ProjectStatus.DELETED.value == "deleted"
    
    def test_task_status_values(self):
        """测试任务状态枚举值"""
        assert TaskStatus.PENDING.value == "pending"
        assert TaskStatus.IN_PROGRESS.value == "in_progress"
        assert TaskStatus.COMPLETED.value == "completed"
    
    def test_task_priority_values(self):
        """测试任务优先级枚举值"""
        assert TaskPriority.LOW.value == "low"
        assert TaskPriority.NORMAL.value == "normal"
        assert TaskPriority.HIGH.value == "high"
        assert TaskPriority.URGENT.value == "urgent"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
