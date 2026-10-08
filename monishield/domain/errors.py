"""Domain errors: rejections that may be shown to the user (code + message + suggested HTTP status), without secrets.
The interface layer (API/CLI) translates them; inner layers know nothing about HTTP."""


class Fail(Exception):
    def __init__(self, code, message, status=400):
        super().__init__(message); self.code, self.message, self.status = code, message, status


class Busy(Fail):
    """Another job (ingest/import) is running."""

    def __init__(self, message='Ingest is running.', code='ingest_running'): super().__init__(code, message, 409)
