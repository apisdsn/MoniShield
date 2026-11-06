"""What a server's operating-system description says (docs/13-metrics.md). The collector's resource detection sends one text,
`os.description`, for example

    Ubuntu 24.04.5 LTS (Noble Numbat) (Linux web-01 6.8.0-138-generic #1 SMP PREEMPT_DYNAMIC x86_64)
    Microsoft Windows Server 2022 Datacenter 10.0.20348 Build 20348

`parse_os` splits it into the short name, the kernel (or build) and the CPU architecture for the Servers page. A text of an unknown
shape is the name as it is, with no kernel. Pure: standard library only."""
import re

UNIX = r'(?:Linux|Darwin|FreeBSD|OpenBSD|NetBSD|DragonFly|SunOS|AIX)'
KERNEL = re.compile(rf'\s*\(({UNIX})\s+\S+\s+(\S+)([^()]*)\)\s*$')      # (Linux <host name> <release> <build text> <machine>)
CODENAME = re.compile(r'\s*\([^()]*\)\s*$')
WINDOWS = re.compile(r'^(?P<name>(?:Microsoft )?Windows\b.*?)\s+(?P<build>\d+\.\d+\.\d+.*)$', re.I)
ARCH = re.compile(r'\b(x86_64|amd64|aarch64|arm64|armv\d+l?|i[3-6]86|ppc64le|riscv64|s390x)\s*$', re.I)
MAX = 200


def parse_os(text):
    """-> dict(name, kernel, arch); every key can be None, `name` is None only for an empty text."""
    text = ' '.join(text.split())[:MAX] if isinstance(text, str) else ''
    if not text: return dict(name=None, kernel=None, arch=None)
    m = KERNEL.search(text)
    if m:
        name = CODENAME.sub('', text[:m.start()]).strip()
        arch = ARCH.search(m.group(3).strip())
        return dict(name=name or text, kernel=f'{m.group(1)} {m.group(2)}', arch=arch.group(1) if arch else None)
    m = WINDOWS.match(text)
    if m: return dict(name=m.group('name'), kernel=m.group('build'), arch=None)
    return dict(name=text, kernel=None, arch=None)
