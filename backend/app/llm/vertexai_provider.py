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
        # Lazy import to avoid requiring google-cloud-aiplatform when using Ollama
        import vertexai
        from vertexai.generative_models import GenerativeModel

        vertexai.init(project=self._project, location=self._region)
        model = GenerativeModel(
            self._model,
            system_instruction=system_prompt if system_prompt else None,
        )
        response = model.generate_content(prompt)
        return response.text

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
        response = model.generate_content(prompt, stream=True)
        for chunk in response:
            if chunk.text:
                yield chunk.text
