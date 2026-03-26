"""Domain-level errors (independent of HTTP or infrastructure)."""


class LlmNotConfiguredError(Exception):
    """Raised when the LLM client was not initialized (e.g. missing API key)."""


class LlmAnalysisError(Exception):
    """Raised when the LLM call fails or returns unusable data."""
