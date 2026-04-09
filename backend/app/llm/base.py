from typing import AsyncIterator, Protocol


class LLMProvider(Protocol):
    async def generate(self, prompt: str, system_prompt: str = "") -> str: ...

    async def generate_stream(
        self, prompt: str, system_prompt: str = ""
    ) -> AsyncIterator[str]: ...

    def model_name(self) -> str: ...
