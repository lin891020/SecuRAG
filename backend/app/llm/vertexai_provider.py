import asyncio
from typing import AsyncIterator


class VertexAIProvider:
    """Vertex AI LLM provider. Requires google-cloud-aiplatform SDK."""

    def __init__(self, project: str, region: str, model: str):
        self._project = project
        self._region = region
        self._model = model

    def model_name(self) -> str:
        return f"vertexai/{self._model}"

    async def generate(self, prompt: str, system_prompt: str = "") -> str:
        import vertexai
        from vertexai.generative_models import GenerativeModel

        vertexai.init(project=self._project, location=self._region)
        model = GenerativeModel(
            self._model,
            system_instruction=system_prompt if system_prompt else None,
        )

        def _sync() -> str:
            return model.generate_content(prompt).text

        return await asyncio.to_thread(_sync)

    async def generate_stream(
        self, prompt: str, system_prompt: str = ""
    ) -> AsyncIterator[str]:
        import vertexai
        from vertexai.generative_models import GenerativeModel

        vertexai.init(project=self._project, location=self._region)
        model = GenerativeModel(
            self._model,
            system_instruction=system_prompt if system_prompt else None,
        )

        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[str | None] = asyncio.Queue()

        def _produce() -> None:
            try:
                for chunk in model.generate_content(prompt, stream=True):
                    if chunk.text:
                        loop.call_soon_threadsafe(queue.put_nowait, chunk.text)
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        loop.run_in_executor(None, _produce)

        while True:
            token = await queue.get()
            if token is None:
                break
            yield token
