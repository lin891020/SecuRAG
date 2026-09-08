import logging
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)


#: What a caller is told when the input rail was asked for and could not be
#: supplied. Deliberately the same text whether NeMo failed to load or failed
#: mid-check: from outside, both are "the check did not happen".
UNAVAILABLE = "Safety check unavailable. Please try again."


class GuardService:
    """Wrapper around NeMo Guardrails for input/output checking."""

    def __init__(self):
        self._rails = None
        self._enabled = settings.guardrails_enabled
        self._broken = False
        """NeMo was asked for and could not be built.

        Kept apart from ``_enabled`` on purpose. Turning the rails off is a
        decision; failing to load them is an accident, and the two must not
        produce the same behaviour. An earlier version collapsed them -- an
        initialisation failure set ``_enabled = False``, after which every
        request took the "guardrails are off" path and was allowed straight
        through. The README called the input rail fail-closed and a test named
        `test_allows_when_rails_init_fails` held the opposite behaviour in
        place, so a deployment whose NeMo config had a typo ran with no input
        rail at all and said nothing about it.
        """

    async def _get_rails(self):
        if self._rails is None and self._enabled and not self._broken:
            try:
                from nemoguardrails import LLMRails, RailsConfig

                config_path = Path(settings.guardrails_config_path)
                config = RailsConfig.from_path(str(config_path))
                self._rails = LLMRails(config)
            except Exception as e:
                logger.error("Failed to initialize NeMo Guardrails: %s", e)
                self._broken = True
        return self._rails

    async def check_input(self, user_message: str) -> tuple[bool, str]:
        """Check if user input is allowed.

        Returns (is_allowed, response_if_blocked).

        Fail-closed: if the rail was configured on and cannot answer -- because
        NeMo would not load, or because the check itself raised -- the request
        is blocked. Only an explicitly disabled rail lets traffic past
        unchecked.
        """
        if not self._enabled:
            return True, ""

        try:
            rails = await self._get_rails()
            if rails is None:
                return False, UNAVAILABLE

            result = await rails.generate_async(
                messages=[{"role": "user", "content": user_message}]
            )
            content = result.get("content", "")

            # NeMo returns the bot's refusal message if blocked
            blocked = self._is_blocked(content)
            return (not blocked, content if blocked else "")
        except Exception as e:
            logger.error(f"Guardrails input check error: {e}")
            return False, UNAVAILABLE

    async def check_output(self, output: str) -> tuple[bool, str]:
        """Check if LLM output is allowed.

        Returns (is_allowed, output).

        Runs on the finished response, after every token has already been
        streamed to the client, so it detects rather than blocks -- see
        `app.services.rag_pipeline.query_rag`. It needs no NeMo, which is why
        ``_broken`` does not disable it.

        NeMo generate_async is a response-generation API, not an auditing API.
        Passing externally-generated content through it triggers NeMo's own input
        rails on the trigger phrase ("check this response"), causing false positives
        on every legitimate answer. Pattern matching is used instead to catch the
        narrow class of outputs that indicate the LLM was successfully jailbroken
        (system prompt disclosure, jailbreak confirmations).
        """
        if not self._enabled:
            return True, output

        block_patterns = [
            "ignore all previous instructions",
            "ignore your instructions",
            "my actual system prompt is",
            "here is my system prompt",
            "my system prompt says",
            "i have no restrictions",
            "i am now unrestricted",
        ]
        lower = output.lower()
        if any(p in lower for p in block_patterns):
            logger.warning("Output guardrail blocked response (pattern match): %s", output[:100])
            return False, output

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
