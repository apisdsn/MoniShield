"""The install scripts for collectors (docs/12-collector.md, step 5): templates in assets/collector/ with the pinned
otelcol-contrib version and this server's receiver address filled in. The scripts hold no secret."""
import os

from monishield.domain import collector_config

DIR = os.path.join(os.path.dirname(__file__), 'assets', 'collector')
SCRIPTS = {'install.sh': 'text/x-shellscript', 'install.ps1': 'text/plain'}


def render(name, version, url):
    """-> the script text. `version` and `url` are checked here, because they end up inside commands."""
    if name not in SCRIPTS: raise KeyError(name)
    if not all(c.isdigit() or c == '.' for c in version) or not version: raise ValueError('invalid version')
    with open(os.path.join(DIR, name), encoding='utf-8') as fh: text = fh.read()
    if name == 'install.sh':          # the Docker name helper is part of the script: one downloaded file is all there is to read
        with open(os.path.join(DIR, 'docker-names.sh'), encoding='utf-8') as fh: text = text.replace('@@DOCKER_NAMES_SH@@', fh.read().rstrip('\n'))
    return text.replace('@@VERSION@@', version).replace('@@URL@@', collector_config.base_url(url))
