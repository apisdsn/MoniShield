"""domain/host_info.py: the operating-system text of a server split into name, kernel and architecture."""
import pytest

from monishield.domain.host_info import parse_os

SAMPLES = [
    ('Ubuntu 24.04.5 LTS (Noble Numbat) (Linux vm 6.18.44-fc-v236 #1 SMP PREEMPT_DYNAMIC @0 x86_64)', ('Ubuntu 24.04.5 LTS', 'Linux 6.18.44-fc-v236', 'x86_64')),
    ('Ubuntu 22.04.4 LTS (Jammy Jellyfish) (Linux web-01 5.15.0-101-generic #111-Ubuntu SMP Tue Mar 5 20:16:58 UTC 2024 x86_64)',
     ('Ubuntu 22.04.4 LTS', 'Linux 5.15.0-101-generic', 'x86_64')),
    ('Debian GNU/Linux 12 (bookworm) (Linux db-02 6.1.0-18-arm64 #1 SMP Debian 6.1.76-1 aarch64)', ('Debian GNU/Linux 12', 'Linux 6.1.0-18-arm64', 'aarch64')),
    ('Alpine Linux v3.19 (Linux node-a 6.6.14-0-lts #1-Alpine SMP x86_64)', ('Alpine Linux v3.19', 'Linux 6.6.14-0-lts', 'x86_64')),
    ('Microsoft Windows Server 2022 Datacenter 10.0.20348 Build 20348', ('Microsoft Windows Server 2022 Datacenter', '10.0.20348 Build 20348', None)),
    ('Microsoft Windows 11 Pro 10.0.22631 Build 22631', ('Microsoft Windows 11 Pro', '10.0.22631 Build 22631', None)),
    ('macOS 14.5 (Darwin mac-1 23.5.0 Darwin Kernel Version 23.5.0 arm64)', ('macOS 14.5', 'Darwin 23.5.0', 'arm64')),
    ('Ubuntu 24.04 LTS', ('Ubuntu 24.04 LTS', None, None)),                                  # no kernel part
    ('Some Custom OS (build 7)', ('Some Custom OS (build 7)', None, None)),                    # unknown shape: the whole text
    ('linux', ('linux', None, None)),                                                          # only os.type
    ('Arch Linux (Linux box 6.8.1-arch1-1 #1 SMP PREEMPT_DYNAMIC)', ('Arch Linux', 'Linux 6.8.1-arch1-1', None)),
]


@pytest.mark.parametrize('text,want', SAMPLES)
def test_samples(text, want):
    got = parse_os(text)
    assert (got['name'], got['kernel'], got['arch']) == want


@pytest.mark.parametrize('text', [None, '', '   ', 5, b'x'])
def test_empty_or_not_text(text): assert parse_os(text) == dict(name=None, kernel=None, arch=None)


def test_a_long_text_is_cut():
    assert len(parse_os('x' * 1000)['name']) == 200
