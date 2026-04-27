"""Domain-level errors (independent of HTTP or infrastructure)."""


class AiServiceException(Exception):
    """Base exception for AI service domain."""
    def __init__(self, message: str, code: str = None):
        self.message = message
        self.code = code or self.__class__.__name__
        super().__init__(self.message)


class LlmNotConfiguredError(AiServiceException):
    """Raised when the LLM client was not initialized."""
    pass


class LlmAnalysisError(AiServiceException):
    """Raised when the LLM call fails or returns unusable data."""
    pass


class ValidationError(AiServiceException):
    """Raised when input validation fails."""
    pass


class OcrExtractionError(AiServiceException):
    """Raised when OCR extraction fails."""
    pass
