"""Object storage providers (owner request 2026-10-08: "object storage with many choices"). Pure rules: which
providers exist, which endpoint each uses, and what their keys look like. The S3 API is spoken by most of them
(AWS S3, Cloudflare R2, MinIO, Wasabi, Google Cloud Storage with HMAC keys, DigitalOcean Spaces, any other
S3-compatible service); Azure Blob Storage has its own API. The connection itself is monishield/infrastructure/importer.py.

Settings: S4_STORAGE_PROVIDER, S4_STORAGE_ENDPOINT, S4_IMPORT_REGION; keys AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY
(the access key pair of every S3-compatible provider) or AZURE_STORAGE_ACCOUNT / AZURE_STORAGE_KEY.
"""
import re

# key -> label, api ('s3' | 'azure'), endpoint template ({region}; '' = the provider's own default; None = must be
# entered), region (always empty: the region is free text typed by the user, owner request 2026-10-08), path-style addressing
PROVIDERS = {
    'aws':    dict(label='Amazon S3', api='s3', endpoint='', region='', path=False),
    'r2':     dict(label='Cloudflare R2', api='s3', endpoint=None, region='', path=False),
    'minio':  dict(label='MinIO', api='s3', endpoint=None, region='', path=True),
    'wasabi': dict(label='Wasabi', api='s3', endpoint='https://s3.{region}.wasabisys.com', region='', path=False),
    'gcs':    dict(label='Google Cloud Storage (HMAC)', api='s3', endpoint='https://storage.googleapis.com', region='', path=False),
    'spaces': dict(label='DigitalOcean Spaces', api='s3', endpoint='https://{region}.digitaloceanspaces.com', region='', path=False),
    'azure':  dict(label='Azure Blob Storage', api='azure', endpoint='', region='', path=False),
    's3':     dict(label='S3-compatible (other)', api='s3', endpoint=None, region='', path=True),
}
ENDPOINT = re.compile(r'https?://[A-Za-z0-9.-]{1,253}(:\d{1,5})?/?')
AWS_KEY_ID = re.compile(r'[A-Z0-9]{16,128}')
KEY_ID = re.compile(r'[A-Za-z0-9._+/=-]{3,128}')                    # access key IDs of the other S3-compatible services
SECRET = re.compile(r'[A-Za-z0-9/+=._-]{8,256}')
REGION = re.compile(r'[^\s\x00-\x1f]{1,64}')   # free text: any region name the provider uses, no spaces
AZURE_ACCOUNT = re.compile(r'[a-z0-9]{3,24}')
AZURE_KEY = re.compile(r'[A-Za-z0-9+/=]{20,200}')


def provider(name): return PROVIDERS.get(name or 'aws', PROVIDERS['aws'])


def is_azure(name): return provider(name)['api'] == 'azure'


def endpoint_url(name, endpoint='', region=''):
    """S3 endpoint to connect to: the one entered, else the provider's template; None = the AWS default for the region."""
    if endpoint: return endpoint.rstrip('/')
    p = provider(name)
    if p['endpoint'] and ('{region}' not in p['endpoint'] or region): return p['endpoint'].format(region=region)
    return None


def check(s):
    """Settings dict -> first problem (message) or None. Reads storage_provider, storage_endpoint, import_region and the keys."""
    name = s.get('storage_provider') or 'aws'
    if name not in PROVIDERS: return f'Unknown object storage provider "{str(name)[:30]}". Choose one of: {", ".join(PROVIDERS)}.'
    p, ep, region = PROVIDERS[name], s.get('storage_endpoint') or '', s.get('import_region') or ''
    if ep and not ENDPOINT.fullmatch(ep): return 'The storage endpoint must be an address such as https://minio.example.com:9000.'
    if p['api'] == 's3' and p['endpoint'] is None and not ep: return f'{p["label"]} needs the endpoint address of the storage server.'
    if region and not REGION.fullmatch(region): return 'The region is too long or contains spaces.'   # free text (owner, 2026-10-08)
    if p['api'] == 's3' and '{region}' in (p['endpoint'] or '') and not (ep or region): return f'{p["label"]} needs the region (or the endpoint address).'
    if p['api'] == 'azure':
        a, k = s.get('azure_storage_account') or '', s.get('azure_storage_key') or ''
        if a and not AZURE_ACCOUNT.fullmatch(a): return 'The Azure storage account name is 3–24 lowercase letters and digits.'
        if k and not AZURE_KEY.fullmatch(k): return 'The Azure storage account key does not look like a key (base64).'
        if bool(a) != bool(k): return 'Set the Azure storage account name and key together.'
        return None
    ak, sk = s.get('aws_access_key_id') or '', s.get('aws_secret_access_key') or ''
    if ak and not (AWS_KEY_ID if name == 'aws' else KEY_ID).fullmatch(ak):
        return ('AWS Access Key ID is 16–128 uppercase letters/digits (e.g. AKIA…).' if name == 'aws'
                else 'The access key ID may only contain letters, digits and . _ + / = - (3–128 characters).')
    if sk and not (16 <= len(sk) <= 128 and re.fullmatch(r'[A-Za-z0-9/+=]+', sk) if name == 'aws' else SECRET.fullmatch(sk)):
        return 'AWS Secret Access Key does not look like a secret key (16–128 characters).' if name == 'aws' else 'The secret access key does not look like a secret key.'
    if bool(ak) != bool(sk): return 'Set Access Key ID and Secret Access Key together.'
    return None


def has_keys(cfg):
    """Are the keys of the chosen provider set?"""
    if is_azure(cfg.storage_provider): return bool(cfg.azure_storage_account and cfg.azure_storage_key)
    return bool(cfg.aws_access_key_id and cfg.aws_secret_access_key)
