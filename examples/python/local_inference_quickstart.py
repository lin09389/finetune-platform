import asyncio
import json

import httpx


async def main():
    async with httpx.AsyncClient(base_url="http://127.0.0.1:8010", timeout=120.0) as client:
        payload = {
            "model": "your-local-model",
            "messages": [{"role": "user", "content": "请用一句话介绍这个平台。"}],
            "options": {
                "backend": "llama-cpp",
                "temperature": 0.2,
                "max_tokens": 128,
            },
            "memory": {"enabled": False, "auto_extract": False, "auto_retrieve": False},
            "knowledge": {"use_knowledge": False, "auto_retrieve": False, "include_sources": False},
            "context": {"use_context": False},
        }
        response = await client.post("/inference/chat", json=payload)
        response.raise_for_status()
        print(json.dumps(response.json(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
