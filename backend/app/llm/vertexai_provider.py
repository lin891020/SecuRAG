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
        # `generate_content(...).text` raises if the candidate was blocked or
        # returned no parts, and that exception propagates from `to_thread`.
        # Unlike the streaming path below, nothing here has to carry it across
        # a thread boundary by hand.
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
        queue: asyncio.Queue[str | BaseException | None] = asyncio.Queue()

        def _produce() -> None:
            """Pump chunks onto the queue; put the failure on it too.

            The `finally` here closes the stream, and on its own that is all it
            did: an exception raised inside the loop -- an expired credential, a
            quota refusal, a dropped connection -- died in the executor thread,
            the sentinel went out, and the caller saw a stream that ended. Which
            is to say a truncated answer, or an empty one, with a 200 and
            nothing in the log. The exception travels with the sentinel now, so
            it is raised where somebody can see it.
            """
            try:
                for chunk in model.generate_content(prompt, stream=True):
                    if chunk.text:
                        loop.call_soon_threadsafe(queue.put_nowait, chunk.text)
            except BaseException as exc:  # noqa: BLE001 -- re-raised below
                loop.call_soon_threadsafe(queue.put_nowait, exc)
            else:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        loop.run_in_executor(None, _produce)

        while True:
            token = await queue.get()
            if token is None:
                break
            if isinstance(token, BaseException):
                raise token
            yield token
