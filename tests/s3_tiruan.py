"""Local fake S3 for the import tests (TRD §9.6): just ListObjectsV2 (paginated) and GetObject, path-style addressing.

Does not verify signatures; only the key ID in the Authorization header (enough for "credentials rejected by S3").
Every request is recorded in `log` so tests can assert, e.g., that a rejected link never contacts S3.
"""
import hashlib, http.server, re, threading, urllib.parse
from xml.sax.saxutils import escape

KEY_OK = 'AKIATIRUANUJI0000001'


class S3Tiruan:
    def __init__(self, buckets=None, keys=(KEY_OK,), page=3):
        self.buckets = buckets or {}          # {bucket: {key: bytes}}
        self.keys, self.page, self.log = set(keys), page, []
        tiruan = self

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a): pass

            def _send(self, code, body=b'', headers=None):
                self.send_response(code)
                for k, v in (headers or {}).items(): self.send_header(k, v)
                self.send_header('Content-Length', str(len(body))); self.end_headers()
                if self.command != 'HEAD': self.wfile.write(body)

            def _err(self, code, s3code):
                self._send(code, f'<?xml version="1.0"?><Error><Code>{s3code}</Code><Message>{s3code}</Message></Error>'.encode(), {'Content-Type': 'application/xml'})

            def do_GET(self):
                u = urllib.parse.urlsplit(self.path)
                q = dict(urllib.parse.parse_qsl(u.query, keep_blank_values=True))
                tiruan.log.append((self.command, urllib.parse.unquote(u.path), q))
                m = re.search(r'Credential=([^/]+)/', self.headers.get('Authorization', ''))
                if not m or m.group(1) not in tiruan.keys: return self._err(403, 'InvalidAccessKeyId')
                parts = urllib.parse.unquote(u.path).lstrip('/').split('/', 1)
                bucket = tiruan.buckets.get(parts[0])
                if bucket is None: return self._err(404, 'NoSuchBucket')
                if len(parts) == 1 or parts[1] == '':
                    if q.get('list-type') != '2': return self._err(400, 'InvalidRequest')
                    keys = sorted(k for k in bucket if k.startswith(q.get('prefix', '')))
                    if q.get('delimiter'):   # common prefixes (folders) without their contents; a single page only
                        pre, d = q.get('prefix', ''), q['delimiter']
                        cps = sorted({pre + k[len(pre):].split(d, 1)[0] + d for k in keys if d in k[len(pre):]})
                        files = [k for k in keys if d not in k[len(pre):]]
                        xml = (f'<?xml version="1.0" encoding="UTF-8"?><ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
                               f'<Name>{parts[0]}</Name><Prefix>{escape(pre)}</Prefix><Delimiter>{escape(d)}</Delimiter><KeyCount>{len(cps) + len(files)}</KeyCount>'
                               f'<MaxKeys>1000</MaxKeys><IsTruncated>false</IsTruncated>'
                               + ''.join(f'<Contents><Key>{escape(k)}</Key><Size>{len(bucket[k])}</Size><ETag>"x"</ETag></Contents>' for k in files)
                               + ''.join(f'<CommonPrefixes><Prefix>{escape(c)}</Prefix></CommonPrefixes>' for c in cps) + '</ListBucketResult>')
                        return self._send(200, xml.encode(), {'Content-Type': 'application/xml'})
                    start = int(q.get('continuation-token') or 0)
                    chunk, more = keys[start:start + tiruan.page], start + tiruan.page < len(keys)
                    items = ''.join(f'<Contents><Key>{escape(k)}</Key><LastModified>2026-10-07T00:00:00.000Z</LastModified>'
                                    f'<ETag>"{hashlib.md5(bucket[k]).hexdigest()}"</ETag><Size>{len(bucket[k])}</Size>'
                                    f'<StorageClass>STANDARD</StorageClass></Contents>' for k in chunk)
                    xml = (f'<?xml version="1.0" encoding="UTF-8"?><ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
                           f'<Name>{parts[0]}</Name><Prefix>{escape(q.get("prefix", ""))}</Prefix><KeyCount>{len(chunk)}</KeyCount>'
                           f'<MaxKeys>1000</MaxKeys><IsTruncated>{"true" if more else "false"}</IsTruncated>{items}'
                           + (f'<NextContinuationToken>{start + tiruan.page}</NextContinuationToken>' if more else '') + '</ListBucketResult>')
                    return self._send(200, xml.encode(), {'Content-Type': 'application/xml'})
                data = bucket.get(parts[1])
                if data is None: return self._err(404, 'NoSuchKey')
                self._send(200, data, {'ETag': f'"{hashlib.md5(data).hexdigest()}"', 'Content-Type': 'application/octet-stream',
                                       'Last-Modified': 'Wed, 07 Oct 2026 00:00:00 GMT'})

            def do_PUT(self): tiruan.log.append((self.command, self.path, {})); self._err(403, 'AccessDenied')   # must never be called
            do_DELETE = do_POST = do_PUT

        self.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), H)
        self.url = f'http://127.0.0.1:{self.server.server_address[1]}'
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def gets(self): return [p for m, p, q in self.log if m == 'GET' and 'list-type' not in q]

    def close(self): self.server.shutdown(); self.server.server_close()
