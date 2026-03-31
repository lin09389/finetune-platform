import os
import platform
import subprocess
import winreg
from dataclasses import dataclass
from enum import Enum
from typing import Any


class EnvironmentAction(str, Enum):
    GET = "get"
    SET = "set"
    DELETE = "delete"
    LIST = "list"
    PATH_ADD = "path_add"
    PATH_REMOVE = "path_remove"
    PATH_LIST = "path_list"


class EnvironmentScope(str, Enum):
    USER = "user"
    SYSTEM = "system"
    PROCESS = "process"


@dataclass
class EnvironmentVariable:
    name: str
    value: str
    scope: EnvironmentScope

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "scope": self.scope.value,
        }


class EnvironmentOperations:
    def __init__(self):
        self._is_windows = platform.system() == "Windows"
        self._confirmation_required: dict[str, bool] = {}

    async def get_variable(self, name: str) -> dict[str, Any] | None:
        value = os.environ.get(name)

        if value is None:
            return None

        return {
            "name": name,
            "value": value,
            "scope": "process",
        }

    async def list_variables(
        self,
        filter_name: str | None = None,
    ) -> list[dict[str, Any]]:
        variables = []

        for name, value in os.environ.items():
            if filter_name and filter_name.lower() not in name.lower():
                continue

            variables.append({
                "name": name,
                "value": value,
                "scope": "process",
            })

        variables.sort(key=lambda x: x["name"])

        return variables

    async def set_variable(
        self,
        name: str,
        value: str,
        scope: EnvironmentScope = EnvironmentScope.USER,
        require_confirmation: bool = True,
    ) -> dict[str, Any]:
        if scope == EnvironmentScope.SYSTEM:
            if require_confirmation and not self._confirmation_required.get(f"set_system_{name}"):
                self._confirmation_required[f"set_system_{name}"] = True
                return {
                    "success": False,
                    "requires_confirmation": True,
                    "message": f"确认设置系统环境变量 {name}？这需要管理员权限。请再次执行以确认。",
                    "name": name,
                }
            self._confirmation_required.pop(f"set_system_{name}", None)

        if scope == EnvironmentScope.PROCESS:
            os.environ[name] = value
            return {
                "success": True,
                "message": f"进程环境变量 {name} 已设置",
                "name": name,
                "value": value,
                "scope": scope.value,
            }

        if self._is_windows:
            return await self._set_variable_windows(name, value, scope)
        else:
            return await self._set_variable_linux(name, value, scope)

    async def _set_variable_windows(
        self,
        name: str,
        value: str,
        scope: EnvironmentScope,
    ) -> dict[str, Any]:
        try:
            if scope == EnvironmentScope.USER:
                key = winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    "Environment",
                    0,
                    winreg.KEY_SET_VALUE,
                )
            else:
                key = winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment",
                    0,
                    winreg.KEY_SET_VALUE,
                )

            winreg.SetValueEx(key, name, 0, winreg.REG_EXPAND_SZ, value)
            winreg.CloseKey(key)

            os.environ[name] = value

            subprocess.run(
                ["powershell", "-Command",
                 "[Environment]::SetEnvironmentVariable('" + name + "', '" + value + "', 'Process')"],
                capture_output=True,
            )

            return {
                "success": True,
                "message": f"{'用户' if scope == EnvironmentScope.USER else '系统'}环境变量 {name} 已设置",
                "name": name,
                "value": value,
                "scope": scope.value,
            }

        except PermissionError:
            return {
                "success": False,
                "error": "没有权限设置环境变量，请以管理员身份运行",
                "name": name,
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "name": name,
            }

    async def _set_variable_linux(
        self,
        name: str,
        value: str,
        scope: EnvironmentScope,
    ) -> dict[str, Any]:
        try:
            if scope == EnvironmentScope.USER:
                home = os.path.expanduser("~")
                bashrc = os.path.join(home, ".bashrc")

                export_line = f'export {name}="{value}"\n'

                with open(bashrc, "a", encoding="utf-8") as f:
                    f.write(export_line)

                os.environ[name] = value

                return {
                    "success": True,
                    "message": f"用户环境变量 {name} 已添加到 .bashrc",
                    "name": name,
                    "value": value,
                    "scope": scope.value,
                }
            else:
                return {
                    "success": False,
                    "error": "设置系统环境变量需要 root 权限",
                    "name": name,
                }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "name": name,
            }

    async def delete_variable(
        self,
        name: str,
        scope: EnvironmentScope = EnvironmentScope.USER,
        require_confirmation: bool = True,
    ) -> dict[str, Any]:
        if scope == EnvironmentScope.SYSTEM:
            if require_confirmation and not self._confirmation_required.get(f"delete_system_{name}"):
                self._confirmation_required[f"delete_system_{name}"] = True
                return {
                    "success": False,
                    "requires_confirmation": True,
                    "message": f"确认删除系统环境变量 {name}？这需要管理员权限。请再次执行以确认。",
                    "name": name,
                }
            self._confirmation_required.pop(f"delete_system_{name}", None)

        if scope == EnvironmentScope.PROCESS:
            if name in os.environ:
                del os.environ[name]
                return {
                    "success": True,
                    "message": f"进程环境变量 {name} 已删除",
                    "name": name,
                }
            return {
                "success": False,
                "error": f"环境变量 {name} 不存在",
                "name": name,
            }

        if self._is_windows:
            return await self._delete_variable_windows(name, scope)
        else:
            return await self._delete_variable_linux(name, scope)

    async def _delete_variable_windows(
        self,
        name: str,
        scope: EnvironmentScope,
    ) -> dict[str, Any]:
        try:
            if scope == EnvironmentScope.USER:
                key = winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    "Environment",
                    0,
                    winreg.KEY_SET_VALUE,
                )
            else:
                key = winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment",
                    0,
                    winreg.KEY_SET_VALUE,
                )

            winreg.DeleteValue(key, name)
            winreg.CloseKey(key)

            if name in os.environ:
                del os.environ[name]

            return {
                "success": True,
                "message": f"{'用户' if scope == EnvironmentScope.USER else '系统'}环境变量 {name} 已删除",
                "name": name,
            }

        except FileNotFoundError:
            return {
                "success": False,
                "error": f"环境变量 {name} 不存在",
                "name": name,
            }
        except PermissionError:
            return {
                "success": False,
                "error": "没有权限删除环境变量，请以管理员身份运行",
                "name": name,
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "name": name,
            }

    async def _delete_variable_linux(
        self,
        name: str,
        scope: EnvironmentScope,
    ) -> dict[str, Any]:
        try:
            if scope == EnvironmentScope.USER:
                home = os.path.expanduser("~")
                bashrc = os.path.join(home, ".bashrc")

                if os.path.exists(bashrc):
                    with open(bashrc, encoding="utf-8") as f:
                        lines = f.readlines()

                    new_lines = [
                        line for line in lines
                        if not line.strip().startswith(f"export {name}=")
                    ]

                    with open(bashrc, "w", encoding="utf-8") as f:
                        f.writelines(new_lines)

                if name in os.environ:
                    del os.environ[name]

                return {
                    "success": True,
                    "message": f"用户环境变量 {name} 已从 .bashrc 中删除",
                    "name": name,
                }
            else:
                return {
                    "success": False,
                    "error": "删除系统环境变量需要 root 权限",
                    "name": name,
                }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "name": name,
            }

    async def get_path_list(self) -> list[str]:
        path_value = os.environ.get("PATH", "")

        if self._is_windows:
            return [p for p in path_value.split(";") if p]
        else:
            return [p for p in path_value.split(":") if p]

    async def add_to_path(
        self,
        path: str,
        scope: EnvironmentScope = EnvironmentScope.USER,
        require_confirmation: bool = True,
    ) -> dict[str, Any]:
        path = os.path.abspath(path)

        current_paths = await self.get_path_list()

        if path in current_paths:
            return {
                "success": False,
                "error": f"路径 {path} 已存在于 PATH 中",
                "path": path,
            }

        if scope == EnvironmentScope.SYSTEM:
            if require_confirmation and not self._confirmation_required.get(f"path_add_system_{path}"):
                self._confirmation_required[f"path_add_system_{path}"] = True
                return {
                    "success": False,
                    "requires_confirmation": True,
                    "message": f"确认将 {path} 添加到系统 PATH？这需要管理员权限。请再次执行以确认。",
                    "path": path,
                }
            self._confirmation_required.pop(f"path_add_system_{path}", None)

        separator = ";" if self._is_windows else ":"
        new_path_value = path + separator + os.environ.get("PATH", "")

        return await self.set_variable("PATH", new_path_value, scope, require_confirmation=False)

    async def remove_from_path(
        self,
        path: str,
        scope: EnvironmentScope = EnvironmentScope.USER,
        require_confirmation: bool = True,
    ) -> dict[str, Any]:
        path = os.path.abspath(path)

        current_paths = await self.get_path_list()

        if path not in current_paths:
            return {
                "success": False,
                "error": f"路径 {path} 不存在于 PATH 中",
                "path": path,
            }

        if scope == EnvironmentScope.SYSTEM:
            if require_confirmation and not self._confirmation_required.get(f"path_remove_system_{path}"):
                self._confirmation_required[f"path_remove_system_{path}"] = True
                return {
                    "success": False,
                    "requires_confirmation": True,
                    "message": f"确认从系统 PATH 中移除 {path}？这需要管理员权限。请再次执行以确认。",
                    "path": path,
                }
            self._confirmation_required.pop(f"path_remove_system_{path}", None)

        new_paths = [p for p in current_paths if p != path]
        separator = ";" if self._is_windows else ":"
        new_path_value = separator.join(new_paths)

        return await self.set_variable("PATH", new_path_value, scope, require_confirmation=False)

    async def expand_environment_variables(self, value: str) -> str:
        return os.path.expandvars(value)
