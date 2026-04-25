"""Deployment package API for fine-tuned model handoff."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from core.config import get_settings
from core.training_context import get_training_context

router = APIRouter()


class DeploymentPackageRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    training_task_id: str
    base_model: str | None = None
    adapter_path: str | None = None
    merged_model_path: str | None = None
    service_base_url: str = "http://127.0.0.1:8000"
    model_alias: str | None = None


def _deployment_dir() -> Path:
    path = get_settings().outputs_dir_resolved / "deployment_packages"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _package_path(package_id: str) -> Path:
    return _deployment_dir() / f"{package_id}.json"


def _read_package_file(path: Path) -> dict[str, Any] | None:
    try:
        with open(path, encoding="utf-8") as f:
            payload = json.load(f)
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None


def _get_config_value(config: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = config.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def _find_training_record(training_task_id: str):
    try:
        for record in get_training_context().state.get_history():
            if record.id == training_task_id:
                return record
    except Exception:
        return None
    return None


def _resolve_package_inputs(request: DeploymentPackageRequest) -> dict[str, str | None]:
    record = _find_training_record(request.training_task_id)
    config = getattr(record, "config", {}) or {}

    base_model = (
        request.base_model
        or getattr(record, "base_model_id", None)
        or _get_config_value(config, "model_id", "modelId")
        or getattr(record, "model_name", None)
    )
    adapter_path = (
        request.adapter_path
        or getattr(record, "adapter_path", None)
        or getattr(record, "checkpoint_path", None)
    )
    merged_model_path = request.merged_model_path
    if not merged_model_path and getattr(record, "method", "") == "full":
        merged_model_path = getattr(record, "output_path", None)

    if not base_model:
        raise HTTPException(status_code=400, detail="缺少基础模型，请填写 base_model 或提供有效训练任务 ID")
    if not adapter_path and not merged_model_path:
        raise HTTPException(status_code=400, detail="缺少 Adapter 或合并模型路径，请填写 adapter_path 或 merged_model_path")

    return {
        "base_model": base_model,
        "adapter_path": adapter_path,
        "merged_model_path": merged_model_path,
    }


def _build_examples(model_name: str, service_base_url: str) -> dict[str, str]:
    return {
        "curl": (
            f"curl -X POST {service_base_url}/inference/chat "
            "-H \"Content-Type: application/json\" "
            f"-d '{{\"model_id\":\"{model_name}\",\"messages\":[{{\"role\":\"user\",\"content\":\"你好\"}}]}}'"
        ),
        "python": (
            "from openai import OpenAI\n\n"
            f"client = OpenAI(base_url=\"{service_base_url}/v1\", api_key=\"local\")\n"
            "response = client.chat.completions.create(\n"
            f"    model=\"{model_name}\",\n"
            "    messages=[{\"role\": \"user\", \"content\": \"你好\"}],\n"
            ")\n"
            "print(response.choices[0].message.content)\n"
        ),
        "typescript": (
            "import OpenAI from 'openai';\n\n"
            f"const client = new OpenAI({{ baseURL: '{service_base_url}/v1', apiKey: 'local' }});\n"
            "const response = await client.chat.completions.create({\n"
            f"  model: '{model_name}',\n"
            "  messages: [{ role: 'user', content: '你好' }],\n"
            "});\n"
            "console.log(response.choices[0].message.content);\n"
        ),
    }


def _build_modelfile(model_name: str, adapter_path: str, merged_model_path: str | None) -> str:
    source = merged_model_path or model_name
    lines = [
        f"FROM {source}",
        "PARAMETER temperature 0.2",
        "PARAMETER top_p 0.9",
        "SYSTEM \"你是一个经过业务数据适配的本地 AI 助手。\"",
    ]
    if adapter_path and not merged_model_path:
        lines.append(f"# LoRA adapter: {adapter_path}")
        lines.append("# Merge the adapter before importing if your Ollama version does not support adapters.")
    return "\n".join(lines) + "\n"


@router.post("/packages")
async def create_deployment_package(request: DeploymentPackageRequest):
    resolved = _resolve_package_inputs(request)
    base_model = resolved["base_model"] or ""
    adapter_path = resolved["adapter_path"] or ""
    merged_model_path = resolved["merged_model_path"]
    package_id = f"deploy_{uuid.uuid4().hex[:12]}"
    model_name = request.model_alias or merged_model_path or base_model
    examples = _build_examples(model_name=model_name, service_base_url=request.service_base_url.rstrip("/"))
    modelfile = _build_modelfile(
        model_name=base_model,
        adapter_path=adapter_path,
        merged_model_path=merged_model_path,
    )

    payload: dict[str, Any] = {
        "package_id": package_id,
        "training_task_id": request.training_task_id,
        "created_at": datetime.now().isoformat(),
        "base_model": base_model,
        "adapter_path": adapter_path,
        "merged_model_path": merged_model_path,
        "ollama_modelfile": modelfile,
        "openai_compatible_examples": examples,
        "env_template": {
            "OPENAI_BASE_URL": f"{request.service_base_url.rstrip('/')}/v1",
            "OPENAI_API_KEY": "local",
            "MODEL_NAME": model_name,
        },
    }

    with open(_package_path(package_id), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    return payload


@router.get("/packages")
async def list_deployment_packages(limit: int = 20):
    packages: list[dict[str, Any]] = []
    for path in _deployment_dir().glob("deploy_*.json"):
        payload = _read_package_file(path)
        if not payload:
            continue
        packages.append(
            {
                "package_id": payload.get("package_id"),
                "training_task_id": payload.get("training_task_id"),
                "created_at": payload.get("created_at"),
                "base_model": payload.get("base_model"),
                "adapter_path": payload.get("adapter_path"),
                "merged_model_path": payload.get("merged_model_path"),
                "model_name": (payload.get("env_template") or {}).get("MODEL_NAME"),
            }
        )

    packages.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    return packages[: max(1, min(limit, 100))]


@router.get("/packages/{package_id}")
async def get_deployment_package(package_id: str):
    path = _package_path(package_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="部署包不存在")
    payload = _read_package_file(path)
    if not payload:
        raise HTTPException(status_code=500, detail="部署包文件损坏")
    return payload


@router.delete("/packages/{package_id}")
async def delete_deployment_package(package_id: str):
    path = _package_path(package_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="部署包不存在")
    path.unlink()
    return {"deleted": True, "package_id": package_id}
