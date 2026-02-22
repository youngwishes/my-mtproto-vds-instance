class BaseServiceError(Exception):
    def __init__(self, *, message: str | None = None, **context) -> None:
        self.message = message or self.__doc__
        self.context = context


class PathDoesNotExist(BaseServiceError):
    """Path does not exist."""
