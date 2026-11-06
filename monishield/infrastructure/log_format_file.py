"""log-formats.toml on disk (LogFormatStore port adapter): written to a temporary file in the same directory, then renamed over
the old one, so a reader (the next start, a copy of the file) never sees half a file."""
import os, tempfile


class LogFormatFile:
    def __init__(self, path): self.path = path

    def exists(self): return os.path.exists(self.path)

    def write(self, text):
        directory = os.path.dirname(self.path) or '.'
        os.makedirs(directory, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix='.log-formats-', suffix='.tmp', dir=directory)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as fh:
                fh.write(text); fh.flush(); os.fsync(fh.fileno())
            if os.path.exists(self.path): os.chmod(tmp, os.stat(self.path).st_mode & 0o777)
            else: os.chmod(tmp, 0o640)
            os.replace(tmp, self.path)
        except BaseException:
            try: os.unlink(tmp)
            except OSError: pass
            raise
