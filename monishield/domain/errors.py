"""Galat domain: penolakan yang boleh ditampilkan ke pengguna (kode + pesan + status HTTP saran), tanpa rahasia.
Lapisan antarmuka (API/CLI) menerjemahkannya; lapisan dalam tidak mengenal HTTP."""


class Fail(Exception):
    def __init__(self, code, message, status=400):
        super().__init__(message); self.code, self.message, self.status = code, message, status


class Busy(Fail):
    """Pekerjaan lain (ingest/impor) sedang berjalan."""

    def __init__(self, message='Ingest sedang berjalan.', code='ingest_running'): super().__init__(code, message, 409)
