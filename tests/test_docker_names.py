"""The Docker name helper (assets/collector/docker-names.sh) against a fake `docker` on PATH and a temporary folder."""
import os, stat, subprocess

import pytest

SCRIPT = os.path.join(os.path.dirname(__file__), '..', 'monishield', 'infrastructure', 'assets', 'collector', 'docker-names.sh')


def cid(n): return f'{n:x}'.rjust(64, 'a')[:64] if n > 9 else str(n) * 64


@pytest.fixture
def env(tmp_path):
    bin_ = tmp_path / 'bin'; bin_.mkdir()
    fake = bin_ / 'docker'
    fake.write_text('#!/bin/sh\n[ -f "$FAKE_FAIL" ] && exit 1\ncat "$FAKE_PS"\n')
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    root, links = tmp_path / 'docker', tmp_path / 'links'
    root.mkdir()

    class E:
        ps = tmp_path / 'ps.txt'
        dir, root_ = links, root

        def containers(self, *rows, files=True):
            """rows (id, name), newest first like `docker ps -a`."""
            self.ps.write_text(''.join(f'{i} {n}\n' for i, n in rows))
            for i, _ in rows:
                if files:
                    (root / i).mkdir(exist_ok=True); (root / i / f'{i}-json.log').write_text('{"log":"x\\n"}\n')

        def run(self, *args, fail=False):
            e = dict(os.environ, PATH=f'{bin_}:{os.environ["PATH"]}', FAKE_PS=str(self.ps), FAKE_FAIL=str(tmp_path / 'fail') if fail else '/nonexistent')
            if fail: (tmp_path / 'fail').write_text('')
            return subprocess.run(['sh', SCRIPT, '--dir', str(links), '--root', str(root), *args], env=e, capture_output=True, text=True, timeout=30)

        def state(self):
            return {p.name: os.readlink(p) for p in sorted(links.iterdir())} if links.exists() else {}
    return E()


def target(env, i): return f'{env.root_}/{i}/{i}-json.log'


def test_creates_links_for_every_container_also_stopped_ones(env):
    a, b, c = cid(1), cid(2), cid(3)
    env.containers((c, 'caddy-t'), (b, 'db-test'), (a, 'web-test'))
    r = env.run()
    assert r.returncode == 0, r.stderr
    assert env.state() == {'web-test.log': target(env, a), 'db-test.log': target(env, b), 'caddy-t.log': target(env, c)}
    assert sorted(r.stdout.splitlines()) == sorted(f'create {n}.log -> {target(env, i)}' for n, i in (('web-test', a), ('db-test', b), ('caddy-t', c)))
    again = env.run()
    assert again.returncode == 0 and again.stdout == ''                    # nothing to do the second time


def test_target_change_and_removal(env):
    a, b, c = cid(1), cid(2), cid(3)
    env.containers((b, 'db-test'), (a, 'web-test'))
    env.run()
    env.containers((c, 'web-test'))                                        # web-test was created again, db-test is gone
    r = env.run()
    assert env.state() == {'web-test.log': target(env, c)}
    assert f'update web-test.log -> {target(env, c)}' in r.stdout and 'remove db-test.log' in r.stdout


def test_dry_run_changes_nothing(env):
    a, b = cid(1), cid(2)
    env.containers((a, 'web-test'))
    r = env.run('--dry-run')
    assert r.stdout == f'create web-test.log -> {target(env, a)}\n' and not env.dir.exists()
    env.run()
    env.containers((b, 'db-test'))
    r = env.run('--dry-run')
    assert sorted(r.stdout.splitlines()) == sorted([f'create db-test.log -> {target(env, b)}', 'remove web-test.log'])
    assert env.state() == {'web-test.log': target(env, a)}


@pytest.mark.parametrize('raw,link', [
    ('my app', 'my-app.log'), ('a/b', 'a-b.log'), ('über', 'ber.log'), ('_x', 'x.log'), ('Shop_DB.1', 'Shop_DB.1.log'),
    ('web,alias', 'web.log'), ('$(touch bad)', 'touch-bad-.log'), ('..', None), ('-', None),
])
def test_odd_names_are_cleaned(env, raw, link):
    a = cid(1)
    env.containers((a, raw))
    r = env.run()
    assert r.returncode == 0, r.stderr
    (name,) = env.state() or [None]
    if link is None: assert name == a[:12] + '.log'                       # nothing usable is left: the first 12 characters of the id
    else: assert name == link
    assert not (env.dir.parent / 'bad').exists()


def test_names_that_clash_after_cleaning(env):
    a, b, c = cid(1), cid(2), cid(3)
    env.containers((c, 'a b'), (b, 'a/b'), (a, 'a-b'))                    # oldest last in the listing: a is the oldest
    env.run()
    assert env.state() == {'a-b.log': target(env, a), f'a-b-{b[:8]}.log': target(env, b), f'a-b-{c[:8]}.log': target(env, c)}


def test_container_without_a_json_file_gets_no_link_and_its_old_link_goes(env):
    a = cid(1)
    env.containers((a, 'web'))
    env.run()
    os.remove(target(env, a))
    r = env.run()
    assert env.state() == {} and 'remove web.log' in r.stdout


def test_docker_not_answering_changes_nothing(env):
    a = cid(1)
    env.containers((a, 'web'))
    env.run()
    r = env.run(fail=True)
    assert r.returncode == 1 and 'links left as they are' in r.stderr and env.state() == {'web.log': target(env, a)}


def test_only_links_are_removed(env):
    env.containers()
    env.dir.mkdir()
    (env.dir / 'keep.log').write_text('a real file')
    env.run()
    assert (env.dir / 'keep.log').read_text() == 'a real file'


def test_bad_option_and_syntax():
    assert subprocess.run(['sh', '-n', SCRIPT]).returncode == 0
    assert subprocess.run(['sh', SCRIPT, '--nope'], capture_output=True).returncode == 2
