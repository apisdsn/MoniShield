"""Object storage providers (owner request 2026-10-08): provider rules, the S3 endpoint per provider, the Azure Blob
adapter (with a fake container client) and the credentials per provider."""
import dataclasses, types

import pytest

from monishield.domain import storage
from monishield.domain.s3_import import ImportFail
from monishield.infrastructure import config, importer

AK, SK = 'AKIAIOSFODNN7EXAMPLE', 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY'
R2_ID, R2_SECRET = '3f2a9c0e7b6d4a1f8e5c2b9a7d4e1f0a', 'c0ffee1234567890abcdef0123456789abcdef0123456789abcdef0123456789'
AZ_KEY = 'bm90LWEtcmVhbC1rZXktanVzdC1hLXRlc3Q=' * 2


@pytest.mark.parametrize('s, problem', [
    (dict(storage_provider='aws', aws_access_key_id=AK, aws_secret_access_key=SK, import_region='ap-southeast-3'), None),
    (dict(storage_provider='aws', aws_access_key_id=R2_ID, aws_secret_access_key=SK), 'AWS Access Key ID'),
    (dict(storage_provider='r2', storage_endpoint='https://acc.r2.cloudflarestorage.com', aws_access_key_id=R2_ID,
          aws_secret_access_key=R2_SECRET, import_region='auto'), None),
    (dict(storage_provider='r2', aws_access_key_id=R2_ID, aws_secret_access_key=R2_SECRET), 'needs the endpoint'),
    (dict(storage_provider='minio', storage_endpoint='http://10.0.0.5:9000', aws_access_key_id='minioadmin',
          aws_secret_access_key='minio-secret-1', import_region='us-east-1'), None),
    (dict(storage_provider='minio', storage_endpoint='minio.local:9000'), 'endpoint must be an address'),
    (dict(storage_provider='wasabi', import_region='ap-southeast-1', aws_access_key_id='ABCDEFGHIJKLMNOPQRST', aws_secret_access_key=SK), None),
    (dict(storage_provider='spaces', import_region='Singapore 1'), 'contains spaces'),
    (dict(storage_provider='spaces'), 'needs the region'),
    (dict(storage_provider='aws', import_region='eu-central-2-custom'), None),          # region is free text
    (dict(storage_provider='gcs', aws_access_key_id='GOOG1EABCDEF', aws_secret_access_key=''), 'together'),
    (dict(storage_provider='azure', azure_storage_account='monishieldlogs', azure_storage_key=AZ_KEY), None),
    (dict(storage_provider='azure', azure_storage_account='Monishield_Logs', azure_storage_key=AZ_KEY), 'account name'),
    (dict(storage_provider='azure', azure_storage_account='monishieldlogs'), 'together'),
    (dict(storage_provider='dropbox'), 'Unknown object storage provider'),
])
def test_provider_rules(s, problem):
    msg = storage.check(s)
    assert (msg is None) if problem is None else (problem in msg), msg


def test_endpoint_per_provider():
    assert storage.endpoint_url('aws') is None                                     # boto3 picks the regional AWS endpoint
    assert storage.endpoint_url('wasabi', '', 'eu-central-1') == 'https://s3.eu-central-1.wasabisys.com'
    assert storage.endpoint_url('spaces', '', 'sgp1') == 'https://sgp1.digitaloceanspaces.com' and storage.endpoint_url('spaces') is None
    assert storage.endpoint_url('gcs') == 'https://storage.googleapis.com'
    assert storage.endpoint_url('r2', 'https://acc.r2.cloudflarestorage.com/') == 'https://acc.r2.cloudflarestorage.com'


def cfg(**over):
    return dataclasses.replace(config.Config(), **over)


def test_s3_client_uses_the_provider_endpoint():
    pytest.importorskip('boto3')
    c = importer._client(cfg(storage_provider='minio', storage_endpoint='http://10.0.0.5:9000', import_region='us-east-1'),
                         dict(aws_access_key_id='minioadmin', aws_secret_access_key='minio-secret-1'))
    assert c.meta.endpoint_url == 'http://10.0.0.5:9000' and c.meta.config.s3['addressing_style'] == 'path'
    c = importer._client(cfg(storage_provider='wasabi', import_region='ap-southeast-1'), dict(aws_access_key_id=AK, aws_secret_access_key=SK))
    assert c.meta.endpoint_url == 'https://s3.ap-southeast-1.wasabisys.com'
    c = importer._client(cfg(storage_provider='aws', import_region='ap-southeast-3'), dict(aws_access_key_id=AK, aws_secret_access_key=SK))
    assert c.meta.endpoint_url == 'https://s3.ap-southeast-3.amazonaws.com'


# ------------------------------------------------------------------ Azure adapter
class Blob(types.SimpleNamespace):
    pass


class Prefix(types.SimpleNamespace):
    pass


class Download:
    def __init__(self, data): self.data = data

    def chunks(self): yield self.data[:5]; yield self.data[5:]


class Pager(list):
    def by_page(self): return iter([self[:2], self[2:]])


class FakeContainer:
    def __init__(self, blobs): self.blobs = blobs

    def list_blobs(self, name_starts_with='', results_per_page=None):
        return Pager(Blob(name=k, size=len(v), etag='"0x8D"') for k, v in sorted(self.blobs.items()) if k.startswith(name_starts_with))

    def walk_blobs(self, name_starts_with='', delimiter='/'):
        seen, out = set(), []
        for k in sorted(self.blobs):
            if not k.startswith(name_starts_with): continue
            rest = k[len(name_starts_with):]
            if delimiter in rest:
                p = name_starts_with + rest.split(delimiter)[0] + delimiter
                if p not in seen: seen.add(p); out.append(Prefix(prefix=p, name=p))
            else: out.append(Blob(name=k, size=len(self.blobs[k]), etag='"0x8D"'))
        return out

    def download_blob(self, key): return Download(self.blobs[key])


def azure(blobs):
    a = importer.AzureBlob.__new__(importer.AzureBlob)
    a.svc = types.SimpleNamespace(get_container_client=lambda name: FakeContainer(blobs))
    return a


def test_azure_adapter_speaks_the_s3_calls_used():
    blobs = {'k8s-logs/2026-10-05/ns/svc/a.log': b'hello world', 'k8s-logs/2026-10-06/ns/svc/b.log': b'x' * 12,
             'k8s-logs/2026-10-06/ns/svc/c.log.gz': b'gz', 'k8s-logs/notes.txt': b'n', 'k8s-logs/latest/x': b'y'}
    a = azure(blobs)
    objs = importer.list_objects(a, 'logs', 'k8s-logs/2026-10-06/', cap=100)
    assert [o['key'] for o in objs] == ['k8s-logs/2026-10-06/ns/svc/b.log', 'k8s-logs/2026-10-06/ns/svc/c.log.gz']
    assert objs[0]['size'] == 12 and objs[0]['etag'] == '0x8D'
    assert importer.list_folders(a, 'logs', 'k8s-logs/') == ['2026-10-05', '2026-10-06']   # "latest" is not a date folder
    assert b''.join(a.get_object(Bucket='logs', Key='k8s-logs/2026-10-05/ns/svc/a.log')['Body'].iter_chunks(4)) == b'hello world'
    assert len(a.list_objects_v2(Bucket='logs', Prefix='k8s-logs/', MaxKeys=1)['Contents']) == 1


def test_azure_errors_are_readable():
    az = pytest.importorskip('azure.core.exceptions')
    assert importer._s3_error(az.ClientAuthenticationError('no')).code == 's3_denied'
    assert importer._s3_error(az.ResourceNotFoundError('no')).code == 's3_not_found'
    assert importer._s3_error(az.ServiceRequestError('no')).code == 's3_unreachable'


def test_credentials_follow_the_provider():
    c = cfg(storage_provider='azure', azure_storage_account='monishieldlogs', azure_storage_key=AZ_KEY, aws_access_key_id=AK, aws_secret_access_key=SK)
    creds = importer.Credentials(c)
    assert creds.get() == (dict(account='monishieldlogs', key=AZ_KEY), 'environment') and creds.status()['available']
    with pytest.raises(ImportFail): creds.set(AK, SK)
    assert 'monishieldlogs' not in repr(creds) and AZ_KEY not in repr(creds)
    r2 = importer.Credentials(cfg(storage_provider='r2', storage_endpoint='https://acc.r2.cloudflarestorage.com'))
    r2.set(R2_ID, R2_SECRET)                                    # lower-case R2 key IDs are accepted for non-AWS providers
    assert r2.get()[1] == 'pasted'
    aws = importer.Credentials(cfg(storage_provider='aws'))
    with pytest.raises(ImportFail): aws.set(R2_ID, R2_SECRET)   # AWS keeps its own key format
