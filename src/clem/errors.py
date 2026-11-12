class ClemError(Exception):
    """Error reported to the user as JSON on stdout with a specific exit code."""

    EXIT_CODES = {
        "config": 2,
        "auth_failed": 3,
        "rate_limited": 3,
        "not_found": 4,
        "upstream": 5,
    }

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message

    @property
    def exit_code(self) -> int:
        return self.EXIT_CODES.get(self.code, 5)
