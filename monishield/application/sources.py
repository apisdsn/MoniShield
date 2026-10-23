"""Data sources (owner request 2026-10-23): S3 and Kafka are two independent sources. Each has its own database and its own
folders, so a day is never a mix of both, and the dashboard shows one source at a time (`?source=` of the API, the source
switch in the page header). The services of the application layer (ingest, retention, folder management, Kafka feed) take a
`ctx`; one ctx per source gives each source its own copy of them."""

S3, KAFKA = 's3', 'kafka'
SOURCES = (S3, KAFKA)
LABEL = {S3: 'S3', KAFKA: 'Kafka'}


def valid(name): return name in SOURCES


class SourceCtx:
    """ctx of one source: its own attributes (cfg, con, warehouse, logfolders, ingest, retention, …) and, for everything else
    (accounts, S3 gateway, notifier, mailer, …), the main ctx. The main ctx itself is the S3 source."""

    def __init__(self, parent, source, **own):
        self._parent = parent
        self.source = source
        self.con = None   # opened when the server starts; never the parent's (that is the S3 database)
        for k, v in own.items(): setattr(self, k, v)

    def __getattr__(self, name):   # only called when the attribute is not the source's own
        if name == '_parent': raise AttributeError(name)
        return getattr(self._parent, name)
