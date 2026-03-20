"""
åºç¨ç½ååç®¡çæ¨¡å?"""
import json
import platform
from pathlib import Path
from typing import Dict, List, Optional, Set
from datetime import datetime
from pydantic import BaseModel, Field
from dataclasses import dataclass, field


@dataclass
class WhitelistEntry:
    name: str
    executable: str
    aliases: List[str] = field(default_factory=list)
    description: str = ""
    category: str = "general"
    added_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def matches(self, query: str) -> bool:
        query_lower = query.lower().strip()
        if self.name.lower() == query_lower:
            return True
        if self.executable.lower() == query_lower:
            return True
        return any(alias.lower() == query_lower for alias in self.aliases)


class WhitelistConfig(BaseModel):
    version: str = "1.0.0"
    platform: str = Field(default_factory=lambda: platform.system())
    entries: Dict[str, WhitelistEntry] = Field(default_factory=dict)
    categories: Set[str] = Field(default_factory=lambda: {"general", "development", "browser", "office", "system", "media"})
    
    class Config:
        arbitrary_types_allowed = True


DEFAULT_WINDOWS_APPS: Dict[str, WhitelistEntry] = {
    "vscode": WhitelistEntry(
        name="Visual Studio Code",
        executable="code",
        aliases=["vscode", "visual studio code", "code editor"],
        description="ä»£ç ç¼è¾å?,
        category="development"
    ),
    "notepad": WhitelistEntry(
        name="Notepad",
        executable="notepad",
        aliases=["è®°äºæ?],
        description="ç³»ç»è®°äºæ?,
        category="system"
    ),
    "notepad++": WhitelistEntry(
        name="Notepad++",
        executable="notepad++",
        aliases=["npp"],
        description="é«çº§ææ¬ç¼è¾å?,
        category="development"
    ),
    "chrome": WhitelistEntry(
        name="Google Chrome",
        executable="chrome",
        aliases=["google chrome", "è°·æ­æµè§å?],
        description="Google æµè§å?,
        category="browser"
    ),
    "edge": WhitelistEntry(
        name="Microsoft Edge",
        executable="msedge",
        aliases=["å¾®è½¯æµè§å?],
        description="Microsoft æµè§å?,
        category="browser"
    ),
    "firefox": WhitelistEntry(
        name="Firefox",
        executable="firefox",
        aliases=["ç«çæµè§å?, "mozilla firefox"],
        description="Firefox æµè§å?,
        category="browser"
    ),
    "word": WhitelistEntry(
        name="Microsoft Word",
        executable="winword",
        aliases=["word", "å¾®è½¯ææ¡£"],
        description="Microsoft Word ææ¡£ç¼è¾å?,
        category="office"
    ),
    "excel": WhitelistEntry(
        name="Microsoft Excel",
        executable="excel",
        aliases=["excel", "å¾®è½¯è¡¨æ ¼"],
        description="Microsoft Excel è¡¨æ ¼ç¼è¾å?,
        category="office"
    ),
    "powerpoint": WhitelistEntry(
        name="Microsoft PowerPoint",
        executable="powerpnt",
        aliases=["ppt", "powerpoint", "å¾®è½¯æ¼ç¤º"],
        description="Microsoft PowerPoint æ¼ç¤ºæç¨¿",
        category="office"
    ),
    "cmd": WhitelistEntry(
        name="Command Prompt",
        executable="cmd",
        aliases=["å½ä»¤æç¤ºç¬?, "command prompt"],
        description="Windows å½ä»¤æç¤ºç¬?,
        category="system"
    ),
    "powershell": WhitelistEntry(
        name="PowerShell",
        executable="powershell",
        aliases=["powershell", "ps"],
        description="Windows PowerShell",
        category="system"
    ),
    "explorer": WhitelistEntry(
        name="File Explorer",
        executable="explorer",
        aliases=["æä»¶èµæºç®¡çå?, "file explorer"],
        description="Windows æä»¶èµæºç®¡çå?,
        category="system"
    ),
    "calculator": WhitelistEntry(
        name="Calculator",
        executable="calc",
        aliases=["è®¡ç®å?, "calculator"],
        description="Windows è®¡ç®å?,
        category="system"
    ),
    "paint": WhitelistEntry(
        name="Paint",
        executable="mspaint",
        aliases=["ç»å¾", "paint"],
        description="Windows ç»å¾",
        category="media"
    ),
}

DEFAULT_MACOS_APPS: Dict[str, WhitelistEntry] = {
    "vscode": WhitelistEntry(
        name="Visual Studio Code",
        executable="Visual Studio Code",
        aliases=["vscode", "visual studio code", "code editor"],
        description="ä»£ç ç¼è¾å?,
        category="development"
    ),
    "safari": WhitelistEntry(
        name="Safari",
        executable="Safari",
        aliases=["safari", "è¹ææµè§å?],
        description="Apple Safari æµè§å?,
        category="browser"
    ),
    "chrome": WhitelistEntry(
        name="Google Chrome",
        executable="Google Chrome",
        aliases=["google chrome", "è°·æ­æµè§å?],
        description="Google æµè§å?,
        category="browser"
    ),
    "finder": WhitelistEntry(
        name="Finder",
        executable="Finder",
        aliases=["è®¿è¾¾", "finder"],
        description="macOS æä»¶ç®¡çå?,
        category="system"
    ),
    "terminal": WhitelistEntry(
        name="Terminal",
        executable="Terminal",
        aliases=["ç»ç«¯", "terminal"],
        description="macOS ç»ç«¯",
        category="system"
    ),
    "calculator": WhitelistEntry(
        name="Calculator",
        executable="Calculator",
        aliases=["è®¡ç®å?, "calculator"],
        description="macOS è®¡ç®å?,
        category="system"
    ),
}


class AppWhitelist:
    def __init__(self, config_path: Optional[Path] = None):
        self._platform = platform.system()
        self._config_path = config_path
        self._config: Optional[WhitelistConfig] = None
        self._initialized = False
    
    def initialize(self) -> None:
        if self._initialized:
            return
        
        if self._config_path and self._config_path.exists():
            self._load_config()
        else:
            self._create_default_config()
        
        self._initialized = True
    
    def _create_default_config(self) -> None:
        default_apps = DEFAULT_WINDOWS_APPS if self._platform == "Windows" else DEFAULT_MACOS_APPS
        self._config = WhitelistConfig(
            entries=default_apps
        )
    
    def _load_config(self) -> None:
        try:
            with open(self._config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            entries = {}
            for key, entry_data in data.get("entries", {}).items():
                if isinstance(entry_data, dict):
                    entries[key] = WhitelistEntry(
                        name=entry_data.get("name", key),
                        executable=entry_data.get("executable", ""),
                        aliases=entry_data.get("aliases", []),
                        description=entry_data.get("description", ""),
                        category=entry_data.get("category", "general"),
                        added_at=entry_data.get("added_at", datetime.now().isoformat()),
                    )
            
            self._config = WhitelistConfig(
                version=data.get("version", "1.0.0"),
                platform=data.get("platform", self._platform),
                entries=entries,
                categories=set(data.get("categories", ["general", "development", "browser", "office", "system", "media"])),
            )
        except Exception:
            self._create_default_config()
    
    def _save_config(self) -> bool:
        if not self._config_path:
            return False
        
        try:
            self._config_path.parent.mkdir(parents=True, exist_ok=True)
            
            data = {
                "version": self._config.version,
                "platform": self._config.platform,
                "entries": {
                    key: {
                        "name": entry.name,
                        "executable": entry.executable,
                        "aliases": entry.aliases,
                        "description": entry.description,
                        "category": entry.category,
                        "added_at": entry.added_at,
                    }
                    for key, entry in self._config.entries.items()
                },
                "categories": list(self._config.categories),
            }
            
            with open(self._config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            return True
        except Exception:
            return False
    
    def is_allowed(self, app_name: str) -> bool:
        if not self._initialized:
            self.initialize()
        
        return self._find_entry(app_name) is not None
    
    def get_executable(self, app_name: str) -> Optional[str]:
        if not self._initialized:
            self.initialize()
        
        entry = self._find_entry(app_name)
        return entry.executable if entry else None
    
    def _find_entry(self, query: str) -> Optional[WhitelistEntry]:
        if not self._config:
            return None
        
        for entry in self._config.entries.values():
            if entry.matches(query):
                return entry
        
        return None
    
    def get_entry(self, app_name: str) -> Optional[WhitelistEntry]:
        if not self._initialized:
            self.initialize()
        
        return self._find_entry(app_name)
    
    def list_all(self) -> List[WhitelistEntry]:
        if not self._initialized:
            self.initialize()
        
        return list(self._config.entries.values())
    
    def list_by_category(self, category: str) -> List[WhitelistEntry]:
        if not self._initialized:
            self.initialize()
        
        return [
            entry for entry in self._config.entries.values()
            if entry.category == category
        ]
    
    def get_categories(self) -> Set[str]:
        if not self._initialized:
            self.initialize()
        
        return self._config.categories
    
    def add(
        self,
        name: str,
        executable: str,
        aliases: Optional[List[str]] = None,
        description: str = "",
        category: str = "general",
    ) -> bool:
        if not self._initialized:
            self.initialize()
        
        key = name.lower().replace(" ", "_")
        
        if key in self._config.entries:
            return False
        
        entry = WhitelistEntry(
            name=name,
            executable=executable,
            aliases=aliases or [],
            description=description,
            category=category,
        )
        
        self._config.entries[key] = entry
        
        if category not in self._config.categories:
            self._config.categories.add(category)
        
        self._save_config()
        return True
    
    def remove(self, app_name: str) -> bool:
        if not self._initialized:
            self.initialize()
        
        entry = self._find_entry(app_name)
        if not entry:
            return False
        
        keys_to_remove = [
            key for key, e in self._config.entries.items()
            if e == entry
        ]
        
        for key in keys_to_remove:
            del self._config.entries[key]
        
        self._save_config()
        return True
    
    def update(
        self,
        app_name: str,
        executable: Optional[str] = None,
        aliases: Optional[List[str]] = None,
        description: Optional[str] = None,
        category: Optional[str] = None,
    ) -> bool:
        if not self._initialized:
            self.initialize()
        
        entry = self._find_entry(app_name)
        if not entry:
            return False
        
        if executable is not None:
            entry.executable = executable
        if aliases is not None:
            entry.aliases = aliases
        if description is not None:
            entry.description = description
        if category is not None:
            entry.category = category
            if category not in self._config.categories:
                self._config.categories.add(category)
        
        self._save_config()
        return True
    
    def export_to_dict(self) -> Dict:
        if not self._initialized:
            self.initialize()
        
        return {
            "version": self._config.version,
            "platform": self._config.platform,
            "entries": {
                key: {
                    "name": entry.name,
                    "executable": entry.executable,
                    "aliases": entry.aliases,
                    "description": entry.description,
                    "category": entry.category,
                    "added_at": entry.added_at,
                }
                for key, entry in self._config.entries.items()
            },
            "categories": list(self._config.categories),
        }
    
    def import_from_dict(self, data: Dict, merge: bool = True) -> int:
        if not self._initialized:
            self.initialize()
        
        imported_count = 0
        entries_data = data.get("entries", {})
        
        for key, entry_data in entries_data.items():
            if not merge and key in self._config.entries:
                continue
            
            entry = WhitelistEntry(
                name=entry_data.get("name", key),
                executable=entry_data.get("executable", ""),
                aliases=entry_data.get("aliases", []),
                description=entry_data.get("description", ""),
                category=entry_data.get("category", "general"),
                added_at=entry_data.get("added_at", datetime.now().isoformat()),
            )
            
            self._config.entries[key] = entry
            imported_count += 1
            
            category = entry.category
            if category not in self._config.categories:
                self._config.categories.add(category)
        
        if imported_count > 0:
            self._save_config()
        
        return imported_count
    
    def export_to_file(self, file_path: Path) -> bool:
        try:
            data = self.export_to_dict()
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            return True
        except Exception:
            return False
    
    def import_from_file(self, file_path: Path, merge: bool = True) -> int:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            return self.import_from_dict(data, merge)
        except Exception:
            return 0
    
    def validate_app(self, app_name: str) -> "ValidationResult":
        from dataclasses import dataclass
        
        @dataclass
        class ValidationResult:
            is_valid: bool
            error: Optional[str] = None
            sanitized_value: Optional[str] = None
            entry: Optional[WhitelistEntry] = None
        
        if not app_name:
            return ValidationResult(False, "åºç¨åç§°ä¸è½ä¸ºç©º")
        
        entry = self._find_entry(app_name)
        if not entry:
            allowed_list = ", ".join(sorted(set(e.name for e in self._config.entries.values())))
            return ValidationResult(
                False,
                f"ä¸åè®¸æå¼æ­¤åºç¨ãåè®¸çåºç¨ï¼{allowed_list}"
            )
        
        return ValidationResult(True, sanitized_value=entry.executable, entry=entry)


_whitelist_instance: Optional[AppWhitelist] = None


def get_whitelist(config_path: Optional[Path] = None) -> AppWhitelist:
    global _whitelist_instance
    if _whitelist_instance is None:
        _whitelist_instance = AppWhitelist(config_path)
        _whitelist_instance.initialize()
    return _whitelist_instance
