import logging
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)


class GuardService:
    """Wrapper around NeMo Guardrails for input/output checking."""

    def __init__(self):
        self._rails = None
        self._enabled = settings.guardrails_enabled

    async def _get_rails(self):
        if self._rails is None and self._enabled:
            try:
                from nemoguardrails import LLMRails, RailsConfig

                config_path = Path(settings.guardrails_config_path)
                config = RailsConfig.from_path(str(config_path))
                self._rails = LLMRails(config)
            except Exception as e:
                logger.warning(f"Failed to initialize NeMo Guardrails: {e}")
                self._enabled = False
        return self._rails

    async def check_input(self, user_message: str) -> tuple[bool, str]:
        """Check if user input is allowed.

        Returns (is_allowed, response_if_blocked).
        """
        if not self._enabled:
            return True, ""

        try:
            rails = await self._get_rails()
            if rails is None:
                return True, ""

            result = await rails.generate_async(
                messages=[{"role": "user", "content": user_message}]
            )
            content = result.get("content", "")

            # NeMo returns the bot's refusal message if blocked
            blocked = self._is_blocked(content)
            return (not blocked, content if blocked else "")
        except Exception as e:
            logger.error(f"Guardrails input check error: {e}")
            # Fail open: allow the message if guardrails error
            return True, ""

    async def check_output(self, output: str) -> tuple[bool, str]:
        """Check if LLM output is allowed.

        Returns (is_allowed, sanitized_output_if_blocked).
        """
        if not self._enabled:
            return True, output

        try:
            rails = await self._get_rails()
            if rails is None:
                return True, output

            result = await rails.generate_async(
                messages=[
                    {"role": "user", "content": "check this response"},
                    {"role": "assistant", "content": output},
                ]
            )
            return True, output
        except Exception as e:
            logger.error(f"Guardrails output check error: {e}")
            return True, output

    @staticmethod
    def _is_blocked(content: str) -> bool:
        """Detect if NeMo returned a refusal/redirect response."""
        block_indicators = [
            "I'm sorry, but I cannot comply",
            "I cannot modify my instructions",
            "I'm SecuRAG, focused on cybersecurity",
        ]
        return any(indicator in content for indicator in block_indicators)


# Singleton
guard_service = GuardService()
