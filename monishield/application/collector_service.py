"""Collector registry use cases (docs/12-collector.md, step 2): an admin registers a collector and gets a one-time
enrollment token; the collector exchanges it once for its own key; the receiver (step 3) authenticates with that key.
Thin: validation is in monishield/domain/collectors.py, storage and audit in the CollectorStore (ports.py)."""
from monishield.domain import collector_config, collectors


class CollectorService:
    def __init__(self, ctx): self.ctx = ctx

    @property
    def store(self): return self.ctx.auth

    @staticmethod
    def _open(info):
        """The collector with the options it really uses (a collector from before the options existed gets the defaults, but sends no
        metrics until an admin turns them on)."""
        return dict(info, options=collector_config.stored(info['platform'], info.get('options')))

    def list(self): return [self._open(c) for c in self.store.collector_list()]

    def get(self, cid): return self._open(self.store.collector_get(cid))

    def add(self, name, platform, admin, ip=None, options=None):
        """-> (collector, enrollment token, token expiry). The token is shown once."""
        platform = collectors.check_platform(platform)
        info, token = self.store.collector_create(collectors.check_name(name), platform, admin, ip, collector_config.normalize(platform, options))
        return self._open(info), token, info['enroll_expires']

    def set_options(self, cid, options, admin, ip=None):
        platform = self.store.collector_get(cid)['platform']
        return self._open(self.store.collector_set_options(cid, collector_config.normalize(platform, options), admin, ip))

    def config(self, info, base_url):
        """The collector's configuration text for its platform (Helm values for Kubernetes)."""
        return collector_config.build(info['platform'], base_url, collector_config.stored(info['platform'], info.get('options')), self.ctx.cfg.collector_otel_version)

    def new_token(self, cid, admin, ip=None):
        token = self.store.collector_new_token(cid, admin, ip)
        return token, self.store.collector_get(cid)['enroll_expires']

    def rotate(self, cid, admin, ip=None):
        """-> (new key, time until which the previous key still works)."""
        key = self.store.collector_rotate(cid, admin, ip)
        return key, self.store.collector_get(cid)['previous_valid_until']

    def revoke(self, cid, admin, ip=None): return self._open(self.store.collector_revoke(cid, admin, ip))

    def delete(self, cid, admin, ip=None):
        self.store.collector_delete(cid, admin, ip)
        self.ctx.metrics.forget(cid)   # its metrics go with it: the id may be given to a new collector

    def enroll(self, token, ip=None, version=None):
        """-> (collector, key). Any bad token gives the same error and counts toward the caller's IP limit."""
        info, key = self.store.collector_enroll(token, ip, (version or '')[:80] or None)
        return self._open(info), key

    def authenticate(self, key_text, ip=None, version=None):
        """For the receiver: the collector of this key, or None. Records the contact (at most once a minute)."""
        info = self.store.collector_check(key_text)
        if info: self.store.collector_seen(info['id'], ip, (version or '')[:80] or None)
        return info
