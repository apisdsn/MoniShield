"""Data sources (owner request 2026-10-23, third source docs/12-collector.md): S3, Kafka and collector are independent sources.
Each has its own database and its own folders, so a day is never a mix of them, and the dashboard shows one source at a time
(`?source=` of the API, the source switch in the page header). The services of the application layer (ingest, retention,
folder management, Kafka feed, collector feed) take a `ctx`; one ctx per source gives each source its own copy of them."""

S3, KAFKA, COLLECTOR = 's3', 'kafka', 'collector'
SOURCES = (S3, KAFKA, COLLECTOR)
LABEL = {S3: 'S3', KAFKA: 'Kafka', COLLECTOR: 'Collector'}
FILLING = (KAFKA, COLLECTOR)   # sources that write the day in progress: the folder dated tomorrow is still filling up


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
