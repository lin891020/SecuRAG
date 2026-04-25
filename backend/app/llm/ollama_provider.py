import json
from typing import AsyncIterator

import httpx


class OllamaProvider:
    def __init__(self, base_url: str, model: str):
        self._base_url = base_url.rstrip("/")
        self._model = model

    def model_name(self) -> str:
        return f"ollama/{self._model}"

    async def generate(self, prompt: str, system_prompt: str = "") -> str:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{self._base_url}/api/generate",
                json={
                    "model": self._model,
                    "prompt": prompt,
                    "system": system_prompt,
                    "stream": False,
                    "num_predict": 2048,
                },
            )
            resp.raise_for_status()
            return resp.json()["response"]

    async def generate_stream(
        self, prompt: str, system_prompt: str = ""
    ) -> AsyncIterator[str]:
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                f"{self._base_url}/api/generate",
                json={
                    "model": self._model,
                    "prompt": prompt,
                    "system": system_prompt,
                    "stream": True,
                    "num_predict": 2048,
                },
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if line:
                        data = json.loads(line)
                        if token := data.get("response", ""):
                            yield token
                        if data.get("done", False):
                            break
