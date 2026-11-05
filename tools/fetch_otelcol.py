"""Download the OpenTelemetry Collector (otelcol-contrib) for the configuration tests (docs/12-collector.md, step 5).

    py tools/fetch_otelcol.py              # the version of S4_COLLECTOR_OTEL_VERSION's default, into tools/otelcol/<version>/
    py tools/fetch_otelcol.py --version 0.163.2

The release's own `<asset>.sha256` file is compared with the download; a mismatch deletes the file and stops. Only linux amd64
and arm64 are fetched (the tests run on Linux). The folder is ignored by git. tests/test_collector_config.py uses the binary
when it is there and skips the real `otelcol-contrib validate` check when it is not.
"""
import argparse, hashlib, io, os, platform, re, sys, tarfile, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from monishield.domain.config_model import Config   # noqa: E402

RELEASE = 'https://github.com/open-telemetry/opentelemetry-collector-releases/releases/download/v{v}/{asset}'


def binary_path(version):
    return os.path.join(ROOT, 'tools', 'otelcol', version, 'otelcol-contrib')


def fetch(version):
    arch = {'x86_64': 'amd64', 'amd64': 'amd64', 'aarch64': 'arm64', 'arm64': 'arm64'}.get(platform.machine().lower())
    if sys.platform != 'linux' or not arch: raise SystemExit('only Linux amd64 and arm64 are supported here')
    asset = f'otelcol-contrib_{version}_linux_{arch}.tar.gz'
    get = lambda name: urllib.request.urlopen(RELEASE.format(v=version, asset=name), timeout=120).read()   # noqa: E731
    want = get(asset + '.sha256').decode('ascii').split()[0].lower()
    if not re.fullmatch(r'[0-9a-f]{64}', want): raise SystemExit('the checksum file does not hold a SHA-256')
    data = get(asset)
    if hashlib.sha256(data).hexdigest() != want: raise SystemExit(f'checksum mismatch for {asset}: nothing was kept')
    dest = os.path.dirname(binary_path(version))
    os.makedirs(dest, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        member = tar.getmember('otelcol-contrib')
        with tar.extractfile(member) as src, open(binary_path(version), 'wb') as out: out.write(src.read())
    os.chmod(binary_path(version), 0o755)
    return binary_path(version)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--version', default=Config().collector_otel_version)
    print(fetch(ap.parse_args().version))
