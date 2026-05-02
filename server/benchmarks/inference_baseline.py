"""本地推理基线采样脚本。"""
from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path
from statistics import mean

import httpx


async def _run_once(
    client: httpx.AsyncClient,
    *,
    endpoint: str,
    model: str,
    backend: str,
    prompt: str,
    max_tokens: int,
    stream: bool,
) -> dict:
    payload = {
        "model": model,
        "prompt": prompt,
        "messages": [{"role": "user", "content": prompt}],
        "options": {
            "backend": backend,
            "max_tokens": max_tokens,
        },
        "memory": {"enabled": False, "auto_retrieve": False},
        "knowledge": {"use_knowledge": False},
    }

    started_at = time.perf_counter()
    first_chunk_at = None
    response_text = ""

    if stream:
        async with client.stream("POST", endpoint, json=payload) as response:
            response.raise_for_status()
            async for chunk in response.aiter_text():
                if not chunk:
                    continue
                if first_chunk_at is None:
                    first_chunk_at = time.perf_counter()
                response_text += chunk
    else:
        response = await client.post(endpoint, json=payload)
        response.raise_for_status()
        response_text = response.text
        first_chunk_at = time.perf_counter()

    completed_at = time.perf_counter()
    duration_ms = (completed_at - started_at) * 1000
    ttft_ms = ((first_chunk_at or completed_at) - started_at) * 1000

    return {
        "duration_ms": round(duration_ms, 2),
        "ttft_ms": round(ttft_ms, 2),
        "response_size": len(response_text),
    }


async def main() -> None:
    parser = argparse.ArgumentParser(description="采样本地推理基线指标")
    parser.add_argument("--base-url", default="http://127.0.0.1:8010", help="服务地址")
    parser.add_argument("--backend", required=True, help="后端类型，如 huggingface/ollama/llama-cpp")
    parser.add_argument("--model", required=True, help="模型名称或路径")
    parser.add_argument("--prompt", default="请简要介绍你自己。", help="测试提示词")
    parser.add_argument("--max-tokens", type=int, default=128)
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--stream", action="store_true", help="使用流式接口")
    parser.add_argument("--output", required=True, help="输出 JSON 文件路径")
    args = parser.parse_args()

    endpoint = "/inference/chat/stream" if args.stream else "/inference/chat"
    runs: list[dict] = []

    async with httpx.AsyncClient(base_url=args.base_url, timeout=180.0) as client:
        for iteration in range(args.iterations):
            batch = await asyncio.gather(
                *[
                    _run_once(
                        client,
                        endpoint=endpoint,
                        model=args.model,
                        backend=args.backend,
                        prompt=args.prompt,
                        max_tokens=args.max_tokens,
                        stream=args.stream,
                    )
                    for _ in range(args.concurrency)
                ]
            )
            runs.extend(batch)
            print(f"[{iteration + 1}/{args.iterations}] 采样完成")

    result = {
        "base_url": args.base_url,
        "backend": args.backend,
        "model": args.model,
        "stream": args.stream,
        "iterations": args.iterations,
        "concurrency": args.concurrency,
        "summary": {
            "avg_duration_ms": round(mean(item["duration_ms"] for item in runs), 2) if runs else 0.0,
            "avg_ttft_ms": round(mean(item["ttft_ms"] for item in runs), 2) if runs else 0.0,
            "avg_response_size": round(mean(item["response_size"] for item in runs), 2) if runs else 0.0,
        },
        "runs": runs,
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已写入基线结果: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
