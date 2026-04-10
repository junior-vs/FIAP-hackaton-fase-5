"""Domain exceptions for the AI Module.

These exceptions map directly to HTTP error responses via handlers
registered in main.py. Never expose internal details in the message
— the handlers serialize only the message field into the response body.
"""

from __future__ import annotations


class UnsupportedFormatError(Exception):
    """Lançada quando o tipo de arquivo enviado não é suportado. → HTTP 422"""

    def __init__(self, message: str = "File format not supported") -> None:
        self.message = message
        super().__init__(self.message)


class InvalidInputError(Exception):
    """Lançada quando o arquivo é inválido (muito grande, corrompido, etc.). → HTTP 422"""

    def __init__(self, message: str = "Invalid input file") -> None:
        self.message = message
        super().__init__(self.message)


class AIFailureError(Exception):
    """Lançada quando o pipeline de IA falha após todas as tentativas. → HTTP 500"""

    def __init__(self, message: str = "AI analysis failed") -> None:
        self.message = message
        super().__init__(self.message)


class LLMTimeoutError(Exception):
    """Lançada pelos adaptadores quando a chamada ao LLM excede o timeout configurado."""

    def __init__(self, message: str = "LLM call timed out") -> None:
        self.message = message
        super().__init__(self.message)


class LLMCallError(Exception):
    """Lançada pelos adaptadores quando o SDK do LLM retorna um erro."""

    def __init__(self, message: str = "LLM call failed") -> None:
        self.message = message
        super().__init__(self.message)