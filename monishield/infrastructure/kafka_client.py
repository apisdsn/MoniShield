"""Klien Kafka (adapter port KafkaClient, pustaka kafka-python): sambungan dengan SASL/SSL dari .env, konsumen grup untuk
monishield/application/kafka_service.py, dan "Cek pesan" (n pesan terakhir topic tanpa grup konsumen). Galat pustaka
diterjemahkan menjadi KafkaFail tanpa sandi."""
import datetime, time

from monishield.domain.kafka_message import KafkaFail, configured, folder_of, parse_message, relpath


def library_ok():
    import importlib.util
    return importlib.util.find_spec('kafka') is not None


NO_LIBRARY = ('Konsumen Kafka butuh paket kafka-python yang belum terpasang di server. Jalankan: .venv/bin/pip install -e ".[kafka]" '
              '(image Docker sudah memuatnya), lalu mulai ulang server.')


def _client_kwargs(cfg):
    kw = dict(bootstrap_servers=[x.strip() for x in cfg.kafka_brokers.split(',') if x.strip()], security_protocol=cfg.kafka_security.upper(),
              client_id='monishield', request_timeout_ms=30000, bootstrap_timeout_ms=10000)
    if cfg.kafka_security.upper().startswith('SASL'):
        kw.update(sasl_mechanism=cfg.kafka_sasl_mechanism.upper(), sasl_plain_username=cfg.kafka_username, sasl_plain_password=cfg.kafka_password)
    if cfg.kafka_ca_file: kw['ssl_cafile'] = cfg.kafka_ca_file
    return kw


def error(e):
    """Galat pustaka -> pesan yang bisa dibaca (tanpa sandi)."""
    n = type(e).__name__
    if n in ('NoBrokersAvailable', 'KafkaConnectionError') or (n == 'KafkaTimeoutError' and 'bootstrap' in str(e)): return KafkaFail('kafka_unreachable', f'Broker Kafka tidak terjangkau dari server ({n}). Periksa alamat broker dan firewall.', 502)
    if 'Authentication' in n or 'SaslAuthentication' in n: return KafkaFail('kafka_auth', 'Kafka menolak nama pengguna/sandi SASL.', 502)
    if n in ('TopicAuthorizationFailedError', 'GroupAuthorizationFailedError'): return KafkaFail('kafka_denied', f'Kafka menolak akses ({n}).', 502)
    return KafkaFail('kafka_error', f'Kafka: {n}: {str(e)[:200]}', 502)


def peek(cfg, n=10):
    """Ambil n pesan TERAKHIR topic (tanpa grup konsumen, tanpa commit) untuk "Cek pesan" di layar."""
    if not configured(cfg): raise KafkaFail('kafka_not_configured', 'Isi alamat broker dan topic Kafka dulu.')
    if not library_ok(): raise KafkaFail('no_kafka_library', NO_LIBRARY)
    from kafka import KafkaConsumer, TopicPartition
    try:
        c = KafkaConsumer(enable_auto_commit=False, group_id=None, consumer_timeout_ms=4000, **_client_kwargs(cfg))
    except Exception as e: raise error(e) from None   # noqa: BLE001
    try:
        parts = c.partitions_for_topic(cfg.kafka_topic)
        if not parts: raise KafkaFail('kafka_no_topic', f'Topic "{cfg.kafka_topic}" tidak ada (atau belum pernah menerima pesan).', 404)
        tps = [TopicPartition(cfg.kafka_topic, p) for p in sorted(parts)]
        c.assign(tps)
        end, beg = c.end_offsets(tps), c.beginning_offsets(tps)
        for tp in tps: c.seek(tp, max(beg[tp], end[tp] - n))
        got, t0 = [], time.time()
        while time.time() - t0 < 6 and sum(1 for _ in got) < n * len(tps):
            batch = c.poll(timeout_ms=800)
            if not batch and all(c.position(tp) >= end[tp] for tp in tps): break
            for recs in batch.values(): got.extend(recs)
        got.sort(key=lambda r: r.timestamp or 0)
        out = []
        for r in got[-n:]:
            rec, why = parse_message(r.value, r.timestamp)
            out.append(dict(partition=r.partition, offset=r.offset, at=datetime.datetime.fromtimestamp((r.timestamp or 0) / 1000, datetime.timezone.utc).isoformat(timespec='seconds'),
                            raw=(r.value or b'')[:2000].decode('utf-8', 'replace'), ok=rec is not None, reason=why,
                            target=relpath(rec, folder_of(rec['t'])) if rec else None))
        total = sum(end[tp] - beg[tp] for tp in tps)
        return dict(topic=cfg.kafka_topic, partitions=len(tps), messages_retained=total, messages=out)
    except KafkaFail: raise
    except Exception as e: raise error(e) from None   # noqa: BLE001
    finally: c.close()




class Consumer:
    """Konsumen grup; offset di-commit pemanggil SESUDAH baris ditulis ke disk (at-least-once)."""

    def __init__(self, cfg):
        from kafka import KafkaConsumer
        self._c = KafkaConsumer(cfg.kafka_topic, group_id=cfg.kafka_group, enable_auto_commit=False, auto_offset_reset=cfg.kafka_offset_reset,
                                max_poll_records=2000, **_client_kwargs(cfg))

    def poll(self, timeout_ms=1000):
        """-> [[(nilai, timestamp_ms, partisi, offset), …] per partisi]."""
        return [[(r.value, r.timestamp, r.partition, r.offset) for r in recs] for recs in self._c.poll(timeout_ms=timeout_ms).values()]

    def commit(self): self._c.commit()

    def close(self): self._c.close()


class KafkaClient:
    """Port KafkaClient untuk lapisan application."""
    no_library = NO_LIBRARY

    def library_ok(self): return library_ok()

    def consumer(self, cfg): return Consumer(cfg)

    def peek(self, cfg, n=10): return peek(cfg, n)

    def error(self, e): return e if isinstance(e, KafkaFail) else error(e)
