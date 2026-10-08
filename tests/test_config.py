"""Configuration: environment > .env > config.toml > defaults; secrets are never printed."""
import dataclasses, os

import pytest

from monishield.infrastructure import config
from monishield.domain import rules


def env_file(tmp_path, text):
    p = tmp_path / '.env'; p.write_text(text, encoding='utf-8'); return str(p)


def test_bawaan_sama_dengan_sistem_lama():
    c = config.load(env={}, dotenv=False)
    assert (c.server_ip, c.hosts, c.server_fallback) == (rules.SERVER_IP, rules.HOSTS, rules.SERVER_FALLBACK)
    assert c.cache_dir.endswith('.cache') and c.state_dir == c.data_dir and c.inbox_dir.endswith('inbox')
    assert (c.cookie_secure, c.import_buckets, c.bind) == (True, {}, '127.0.0.1:8000')


def test_dotenv_semua_jenis_nilai(tmp_path):
    p = env_file(tmp_path, '''# komentar
S4_COOKIE_SECURE=false                    # komentar di ujung
S4_SESSION_IDLE_MINUTES=30
export S4_BIND="0.0.0.0:9000"  # berkutip
S4_ADMIN_PASSWORD=rahasia#bukan-komentar
S4_IMPORT_BUCKETS={"simpel4-backup": ["k8s-logs/"]}   # JSON
S4_SERVER_FALLBACK=["Bogor", "Jawa Barat", "ID", -6.6, 106.8]
MAXMIND_ACCOUNT_ID=123
MAXMIND_LICENSE_KEY='kunci rahasia'
AWS_ACCESS_KEY_ID=
S4_IMPORT_MAX_OBJECTS=
''')
    c = config.load(env={}, dotenv=p)
    assert (c.cookie_secure, c.session_idle_minutes, c.bind, c.admin_password) == (False, 30, '0.0.0.0:9000', 'rahasia#bukan-komentar')
    assert c.import_buckets == {'simpel4-backup': ['k8s-logs/']} and c.server_fallback == ['Bogor', 'Jawa Barat', 'ID', -6.6, 106.8]
    assert (c.maxmind_account_id, c.maxmind_license_key, c.aws_access_key_id, c.import_max_objects) == ('123', 'kunci rahasia', '', 500)


def test_lingkungan_mengalahkan_dotenv(tmp_path):
    p = env_file(tmp_path, 'S4_BIND=1.1.1.1:1\nS4_JOB_TOKEN=dari-file\n')
    c = config.load(env={'S4_BIND': '2.2.2.2:2'}, dotenv=p)
    assert (c.bind, c.job_token) == ('2.2.2.2:2', 'dari-file')


def test_rahasia_tidak_tercetak(tmp_path):
    p = env_file(tmp_path, 'S4_ADMIN_PASSWORD=sandi-panjang-sekali\nS4_JOB_TOKEN=zzTOKENzz\nMAXMIND_LICENSE_KEY=zzLISENSIzz\nAWS_SECRET_ACCESS_KEY=zzAWSzz\n')
    pub = config.load(env={}, dotenv=p).public()
    assert all(pub[k] in ('set', 'empty') for k in config.SECRETS)
    assert not any(s in str(pub) for s in ('sandi-panjang-sekali', 'zzTOKENzz', 'zzLISENSIzz', 'zzAWSzz'))


@pytest.mark.parametrize('text, pesan', [('S4_TIDAK_ADA=1\n', 'unknown keys'), ('S4_SESSION_IDLE_MINUTES=abc\n', 'S4_SESSION_IDLE_MINUTES'),
                                          ('S4_COOKIE_SECURE=mungkin\n', 'must be true or false'), ('S4_IMPORT_BUCKETS=[1]\n', 'must be JSON'), ('ini bukan pasangan\n', 'not KEY=VALUE')])
def test_salah_ketik_menggagalkan_dengan_pesan(tmp_path, text, pesan):
    with pytest.raises(SystemExit) as e: config.load(env={}, dotenv=env_file(tmp_path, text))
    assert pesan in str(e.value)


def test_galat_tidak_membocorkan_nilai(tmp_path):
    with pytest.raises(SystemExit) as e: config.load(env={}, dotenv=env_file(tmp_path, 'S4_IMPORT_MAX_OBJECTS=rahasia-salah-tempat\n'))
    assert 'S4_IMPORT_MAX_OBJECTS' in str(e.value)
    with pytest.raises(SystemExit) as e: config.load(env={}, dotenv=env_file(tmp_path, 'S4_HOSTS={rusak\n'))
    assert 'S4_HOSTS' in str(e.value)


def test_contoh_env_bisa_dimuat():
    import os
    c = config.load(env={}, dotenv=os.path.join(config.V2_DIR, '.env.example'))
    assert c.import_buckets == {'simpel4-backup': ['k8s-logs/']} and c.admin_user == 'admin' and c.cookie_secure is True and c.admin_password == ''


def test_env_example_memuat_semua_variabel():
    """.env.example is "COMPLETE": every config field (including download source URLs and notifications) has its line."""
    t = open(os.path.join(config.V2_DIR, '.env.example')).read()
    assert [config.env_name(f.name) for f in dataclasses.fields(config.Config) if config.env_name(f.name) + '=' not in t] == []
