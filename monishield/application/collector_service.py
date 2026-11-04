"""Collector registry use cases (docs/12-collector.md, step 2): an admin registers a collector and gets a one-time
enrollment token; the collector exchanges it once for its own key; the receiver (step 3) authenticates with that key.
Thin: validation is in monishield/domain/collectors.py, storage and audit in the CollectorStore (ports.py)."""
from monishield.domain import collectors


class CollectorService:
    def __init__(self, ctx): self.ctx = ctx

    @property
    def store(self): return self.ctx.auth

    def list(self): return self.store.collector_list()

    def add(self, name, platform, admin, ip=None):
        """-> (collector, enrollment token, token expiry). The token is shown once."""
        info, token = self.store.collector_create(collectors.check_name(name), collectors.check_platform(platform), admin, ip)
        return info, token, info['enroll_expires']

    def new_token(self, cid, admin, ip=None):
        token = self.store.collector_new_token(cid, admin, ip)
        return token, self.store.collector_get(cid)['enroll_expires']

    def rotate(self, cid, admin, ip=None):
        """-> (new key, time until which the previous key still works)."""
        key = self.store.collector_rotate(cid, admin, ip)
        return key, self.store.collector_get(cid)['previous_valid_until']

    def revoke(self, cid, admin, ip=None): return self.store.collector_revoke(cid, admin, ip)

    def delete(self, cid, admin, ip=None): self.store.collector_delete(cid, admin, ip)

    def enroll(self, token, ip=None, version=None):
        """-> (collector, key). Any bad token gives the same error and counts toward the caller's IP limit."""
        return self.store.collector_enroll(token, ip, (version or '')[:80] or None)

    def authenticate(self, key_text, ip=None, version=None):
        """For the receiver: the collector of this key, or None. Records the contact (at most once a minute)."""
        info = self.store.collector_check(key_text)
        if info: self.store.collector_seen(info['id'], ip, (version or '')[:80] or None)
        return info
