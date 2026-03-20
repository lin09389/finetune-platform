"""
技能目录扫描器

提供自动扫描技能目录、发现技能模块、验证技能完整性的功能�?支持�?- 自动扫描指定目录下的技能模�?- 技能元数据验证
- 依赖检�?- 热加载检�?"""
import hashlib
import importlib
import importlib.util
import inspect
import sys
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Type

from .base import SkillBase
from .models import SkillCategory, SkillMetadata


class ScanStatus(str, Enum):
    """扫描状�?""
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    DUPLICATE = "duplicate"


class SkillLoadStatus(str, Enum):
    """技能加载状�?""
    LOADED = "loaded"
    UNLOADED = "unloaded"
    ERROR = "error"
    PENDING = "pending"


@dataclass
class SkillDependency:
    """技能依赖信�?""
    name: str
    version: Optional[str] = None
    required: bool = True
    resolved: bool = False
    resolved_by: Optional[str] = None


@dataclass
class SkillScanResult:
    """技能扫描结�?""
    skill_name: str
    module_path: str
    file_path: Path
    status: ScanStatus
    skill_class: Optional[Type[SkillBase]] = None
    metadata: Optional[SkillMetadata] = None
    error: Optional[str] = None
    dependencies: List[SkillDependency] = field(default_factory=list)
    file_hash: Optional[str] = None
    scanned_at: datetime = field(default_factory=datetime.now)


@dataclass
class ScanReport:
    """扫描报告"""
    total_scanned: int = 0
    successful: int = 0
    failed: int = 0
    skipped: int = 0
    duplicates: int = 0
    results: List[SkillScanResult] = field(default_factory=list)
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    
    @property
    def duration_ms(self) -> int:
        """扫描耗时（毫秒）"""
        end = self.completed_at or datetime.now()
        return int((end - self.started_at).total_seconds() * 1000)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字�?""
        return {
            "total_scanned": self.total_scanned,
            "successful": self.successful,
            "failed": self.failed,
            "skipped": self.skipped,
            "duplicates": self.duplicates,
            "duration_ms": self.duration_ms,
            "results": [
                {
                    "skill_name": r.skill_name,
                    "module_path": r.module_path,
                    "file_path": str(r.file_path),
                    "status": r.status.value,
                    "error": r.error,
                    "dependencies": [
                        {
                            "name": d.name,
                            "version": d.version,
                            "required": d.required,
                            "resolved": d.resolved,
                        }
                        for d in r.dependencies
                    ],
                }
                for r in self.results
            ],
        }


class SkillScanner:
    """技能目录扫描器"""
    
    def __init__(
        self,
        skills_dir: Optional[Path] = None,
        watch_enabled: bool = False,
        on_skill_found: Optional[Callable[[SkillScanResult], None]] = None,
        on_skill_updated: Optional[Callable[[str, Path], None]] = None,
        on_skill_removed: Optional[Callable[[str], None]] = None,
    ):
        self.skills_dir = skills_dir or Path(__file__).parent / "implemented"
        self.watch_enabled = watch_enabled
        self.on_skill_found = on_skill_found
        self.on_skill_updated = on_skill_updated
        self.on_skill_removed = on_skill_removed
        
        self._file_hashes: Dict[str, str] = {}
        self._skill_files: Dict[str, Path] = {}
        self._loaded_modules: Dict[str, str] = {}
        self._scanned_skills: Dict[str, SkillScanResult] = {}
        
    def _calculate_file_hash(self, file_path: Path) -> str:
        """计算文件哈希�?""
        hasher = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
    
    def _is_valid_skill_class(self, obj: Any) -> bool:
        """检查是否是有效的技能类"""
        return (
            inspect.isclass(obj)
            and issubclass(obj, SkillBase)
            and obj is not SkillBase
            and hasattr(obj, "get_metadata")
        )
    
    def _validate_skill_metadata(self, metadata: SkillMetadata) -> List[str]:
        """验证技能元数据"""
        errors = []
        
        if not metadata.name:
            errors.append("技能名称不能为�?)
        elif not metadata.name.replace("_", "").replace("-", "").isalnum():
            errors.append(f"技能名称格式无�? {metadata.name}")
        
        if not metadata.display_name:
            errors.append("技能显示名称不能为�?)
        
        if not metadata.description:
            errors.append("技能描述不能为�?)
        
        if metadata.timeout < 1:
            errors.append(f"超时时间必须大于0: {metadata.timeout}")
        
        param_names = set()
        for param in metadata.parameters:
            if param.name in param_names:
                errors.append(f"重复的参数名�? {param.name}")
            param_names.add(param.name)
        
        return errors
    
    def _check_dependencies(
        self,
        metadata: SkillMetadata,
        available_skills: Optional[Set[str]] = None
    ) -> List[SkillDependency]:
        """检查技能依�?""
        dependencies = []
        available = available_skills or set()
        
        for dep_name in metadata.dependencies:
            dependency = SkillDependency(
                name=dep_name,
                required=True,
                resolved=dep_name in available,
            )
            dependencies.append(dependency)
        
        return dependencies
    
    def _scan_file(self, file_path: Path) -> List[SkillScanResult]:
        """扫描单个文件"""
        results = []
        module_name = f"skills.implemented.{file_path.stem}"
        
        if file_path.name.startswith("_"):
            return [
                SkillScanResult(
                    skill_name="",
                    module_path=module_name,
                    file_path=file_path,
                    status=ScanStatus.SKIPPED,
                    error="跳过以下划线开头的文件",
                )
            ]
        
        file_hash = self._calculate_file_hash(file_path)
        
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if spec is None or spec.loader is None:
            return [
                SkillScanResult(
                    skill_name="",
                    module_path=module_name,
                    file_path=file_path,
                    status=ScanStatus.FAILED,
                    error="无法创建模块规范",
                )
            ]
        
        try:
            if module_name in sys.modules:
                module = importlib.reload(sys.modules[module_name])
            else:
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                spec.loader.exec_module(module)
            
            self._loaded_modules[module_name] = str(file_path)
            
            for name, obj in inspect.getmembers(module):
                if not self._is_valid_skill_class(obj):
                    continue
                
                try:
                    metadata = obj.get_metadata()
                    validation_errors = self._validate_skill_metadata(metadata)
                    
                    if validation_errors:
                        results.append(SkillScanResult(
                            skill_name=metadata.name or name,
                            module_path=module_name,
                            file_path=file_path,
                            status=ScanStatus.FAILED,
                            skill_class=obj,
                            metadata=metadata,
                            error="元数据验证失�? " + "; ".join(validation_errors),
                            file_hash=file_hash,
                        ))
                        continue
                    
                    self._file_hashes[metadata.name] = file_hash
                    self._skill_files[metadata.name] = file_path
                    
                    results.append(SkillScanResult(
                        skill_name=metadata.name,
                        module_path=module_name,
                        file_path=file_path,
                        status=ScanStatus.SUCCESS,
                        skill_class=obj,
                        metadata=metadata,
                        file_hash=file_hash,
                    ))
                
                except Exception as e:
                    results.append(SkillScanResult(
                        skill_name=name,
                        module_path=module_name,
                        file_path=file_path,
                        status=ScanStatus.FAILED,
                        error=f"获取元数据失�? {str(e)}",
                        file_hash=file_hash,
                    ))
        
        except Exception as e:
            results.append(SkillScanResult(
                skill_name="",
                module_path=module_name,
                file_path=file_path,
                status=ScanStatus.FAILED,
                error=f"加载模块失败: {str(e)}",
            ))
        
        return results
    
    def scan_directory(
        self,
        directory: Optional[Path] = None,
        recursive: bool = True,
        pattern: str = "*.py"
    ) -> ScanReport:
        """扫描目录"""
        target_dir = directory or self.skills_dir
        report = ScanReport()
        
        if not target_dir.exists():
            target_dir.mkdir(parents=True, exist_ok=True)
            report.completed_at = datetime.now()
            return report
        
        files = target_dir.rglob(pattern) if recursive else target_dir.glob(pattern)
        
        for file_path in files:
            if not file_path.is_file():
                continue
            
            results = self._scan_file(file_path)
            
            for result in results:
                report.total_scanned += 1
                report.results.append(result)
                
                if result.status == ScanStatus.SUCCESS:
                    report.successful += 1
                    self._scanned_skills[result.skill_name] = result
                    if self.on_skill_found:
                        self.on_skill_found(result)
                elif result.status == ScanStatus.FAILED:
                    report.failed += 1
                elif result.status == ScanStatus.SKIPPED:
                    report.skipped += 1
                elif result.status == ScanStatus.DUPLICATE:
                    report.duplicates += 1
        
        report.completed_at = datetime.now()
        return report
    
    def scan_package(self, package_path: str) -> ScanReport:
        """扫描 Python �?""
        report = ScanReport()
        
        try:
            package = importlib.import_module(package_path)
            package_dir = Path(package.__file__).parent if package.__file__ else None
            
            if package_dir is None or not package_dir.exists():
                report.completed_at = datetime.now()
                return report
            
            return self.scan_directory(package_dir)
        
        except ImportError as e:
            report.failed += 1
            report.results.append(SkillScanResult(
                skill_name="",
                module_path=package_path,
                file_path=Path("."),
                status=ScanStatus.FAILED,
                error=f"导入包失�? {str(e)}",
            ))
            report.completed_at = datetime.now()
            return report
    
    def check_for_updates(self) -> Dict[str, Dict[str, Any]]:
        """检查技能文件更�?""
        updates = {
            "modified": [],
            "added": [],
            "removed": [],
        }
        
        current_files = {}
        for skill_name, file_path in self._skill_files.items():
            current_files[str(file_path)] = skill_name
        
        if self.skills_dir.exists():
            for file_path in self.skills_dir.glob("**/*.py"):
                if file_path.name.startswith("_"):
                    continue
                
                file_path_str = str(file_path)
                new_hash = self._calculate_file_hash(file_path)
                
                if file_path_str in current_files:
                    skill_name = current_files[file_path_str]
                    old_hash = self._file_hashes.get(skill_name)
                    
                    if old_hash != new_hash:
                        updates["modified"].append({
                            "skill_name": skill_name,
                            "file_path": str(file_path),
                            "old_hash": old_hash,
                            "new_hash": new_hash,
                        })
                else:
                    updates["added"].append({
                        "file_path": str(file_path),
                        "hash": new_hash,
                    })
        
        for file_path_str, skill_name in current_files.items():
            if not Path(file_path_str).exists():
                updates["removed"].append({
                    "skill_name": skill_name,
                    "file_path": file_path_str,
                })
        
        return updates
    
    def get_skill_info(self, skill_name: str) -> Optional[SkillScanResult]:
        """获取技能扫描信�?""
        return self._scanned_skills.get(skill_name)
    
    def get_all_skills_info(self) -> Dict[str, SkillScanResult]:
        """获取所有技能扫描信�?""
        return self._scanned_skills.copy()
    
    def validate_dependencies(
        self,
        skill_name: str,
        available_skills: Set[str]
    ) -> Dict[str, Any]:
        """验证技能依�?""
        result = self._scanned_skills.get(skill_name)
        if result is None or result.metadata is None:
            return {
                "valid": False,
                "error": f"技能不存在: {skill_name}",
                "missing": [],
            }
        
        missing = []
        for dep in result.metadata.dependencies:
            if dep not in available_skills:
                missing.append(dep)
        
        return {
            "valid": len(missing) == 0,
            "missing": missing,
            "dependencies": result.metadata.dependencies,
        }
    
    def get_dependency_order(self, skill_names: List[str]) -> List[str]:
        """获取依赖排序（拓扑排序）"""
        visited = set()
        order = []
        temp_marks = set()
        
        def visit(name: str):
            if name in temp_marks:
                raise ValueError(f"检测到循环依赖: {name}")
            if name in visited:
                return
            
            temp_marks.add(name)
            
            result = self._scanned_skills.get(name)
            if result and result.metadata:
                for dep in result.metadata.dependencies:
                    if dep in skill_names:
                        visit(dep)
            
            temp_marks.remove(name)
            visited.add(name)
            order.append(name)
        
        for name in skill_names:
            if name not in visited:
                visit(name)
        
        return order
    
    def clear_cache(self):
        """清除缓存"""
        self._file_hashes.clear()
        self._skill_files.clear()
        self._scanned_skills.clear()
        
        for module_name in list(self._loaded_modules.keys()):
            if module_name in sys.modules:
                del sys.modules[module_name]
        
        self._loaded_modules.clear()


def create_scanner(
    skills_dir: Optional[Path] = None,
    **kwargs
) -> SkillScanner:
    """创建扫描器实�?""
    return SkillScanner(skills_dir=skills_dir, **kwargs)
