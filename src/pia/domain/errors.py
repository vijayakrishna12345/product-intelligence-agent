"""Domain errors. Crawl errors must not leak into the chat agent."""


class PiaError(Exception):
    """Base error."""


class ProductNotFound(PiaError):
    def __init__(self, query: str, candidates: list[str] | None = None) -> None:
        self.query = query
        self.candidates = candidates or []
        super().__init__(f"Product not found: {query}")


class AmbiguousProduct(PiaError):
    def __init__(self, query: str, candidates: list) -> None:
        self.query = query
        self.candidates = candidates
        super().__init__(f"Ambiguous product: {query}")


class CatalogUnavailable(PiaError):
    pass


class ToolValidationError(PiaError):
    pass


class IngestionError(PiaError):
    pass


class DomainNotAllowed(IngestionError):
    pass


class PathNotAllowed(IngestionError):
    pass


class RobotsDisallowed(IngestionError):
    pass


class LLMError(PiaError):
    pass


class PersistenceError(PiaError):
    pass
