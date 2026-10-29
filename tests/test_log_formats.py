"""Log format rules (domain/log_formats.py, step 1a of docs/11-log-formats.md): file, validation, matching, defaults."""
import dataclasses, os, tomllib

import pytest

from monishield.domain import log_formats as lf, services
from monishield.infrastructure import config

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLE = os.path.join(ROOT, 'log-formats.example.toml')


def example(): return lf.rules_from(tomllib.load(open(EXAMPLE, 'rb')))


def test_example_file_is_valid_and_first_match_wins():
    rules = example()
    assert len(rules) == 8 and lf.unreachable(rules) == []
    pick = lambda svc, ns='shop': lf.match(rules, ns, svc).format
    assert pick('ingress-nginx-controller') == 'ingress-nginx'
    assert pick('web-shop') == pick('web-admin') == 'nginx-combined'
    assert pick('orders-api') == 'json' and pick('payments') == 'logfmt' and pick('legacy-erp') == 'regex'
    assert pick('worker-mail') == 'auto' and pick('something-else') == 'plain'
    orders = lf.match(rules, 'shop', 'orders-api')
    assert dict(orders.fields)['path'] == 'req.url' and orders.features == ('tracing',) and orders.kind == 'app'
    assert lf.match(rules, 'shop', 'auth-service').features == ('logins',)
    assert dict(lf.match(rules, 'x', 'legacy-erp').levels) == {'SEVERE': 'ERROR', 'WARNING': 'WARN', 'FINE': 'DEBUG'}


def test_namespace_globs_and_defaults_per_preset():
    rules = lf.rules_from({'service': [{'match': 'payments/*', 'format': 'json'}, {'match': '*', 'format': 'plain'}]})
    assert lf.match(rules, 'payments', 'api').format == 'json' and lf.match(rules, 'shop', 'api').format == 'plain'
    assert rules[0].kind == 'app' and lf.rules_from({'service': [{'match': 'gw', 'format': 'nginx-combined'}]})[0].kind == 'http'
    assert lf.unreachable(lf.rules_from({'service': [{'match': '*', 'format': 'plain'}, {'match': 'x', 'format': 'json'}]})) == [2]


def test_rule_key_changes_with_the_rule_only():
    a = lf.Rule('orders-api', 'json', 'app', fields=(('time', 'ts'),))
    assert a.key == lf.Rule('orders-api', 'json', 'app', fields=(('time', 'ts'),)).key
    assert a.key != dataclasses.replace(a, fields=(('time', 'timestamp'),)).key and len(a.key) == 12


@pytest.mark.parametrize('rule, word', [
    ({'match': 'a', 'format': 'yaml'}, 'format must be one of'),
    ({'match': 'a b', 'format': 'json'}, 'match must be'),
    ({'match': 'a', 'format': 'json', 'colour': 'red'}, 'unknown key colour'),
    ({'match': 'a', 'format': 'json', 'kind': 'db'}, 'kind must be'),
    ({'match': 'a', 'format': 'json', 'fields': {'when': 'ts'}}, "unknown column 'when'"),
    ({'match': 'a', 'format': 'json', 'fields': {'time': 'a b'}}, 'must be a key name'),
    ({'match': 'a', 'format': 'nginx-combined', 'fields': {'time': 'ts'}}, 'fields only apply'),
    ({'match': 'a', 'format': 'regex'}, 'needs a pattern'),
    ({'match': 'a', 'format': 'regex', 'pattern': '(?P<message>.*)'}, 'named group(s) time'),
    ({'match': 'a', 'format': 'regex', 'pattern': '(?P<time>\\S+) (?P<when>.*) (?P<message>.*)'}, 'unknown group when'),
    ({'match': 'a', 'format': 'regex', 'pattern': '(?P<time>(a+)+) (?P<message>.*)'}, 'nested repeat'),
    ({'match': 'a', 'format': 'regex', 'pattern': '(?P<time>[) (?P<message>.*)'}, 'not a valid regular expression'),
    ({'match': 'a', 'format': 'regex', 'pattern': 'x' * 2001}, 'longer than'),
    ({'match': 'a', 'format': 'json', 'pattern': '.*'}, 'pattern only applies'),
    ({'match': 'a', 'format': 'json', 'time_format': 'yesterday'}, 'time_format must be'),
    ({'match': 'a', 'format': 'json', 'levels': {'SEVERE': 'FATAL'}}, 'levels maps'),
    ({'match': 'a', 'format': 'json', 'tag': 'APP'}, 'tag only applies'),
    ({'match': 'a', 'format': 'json', 'features': ['billing']}, 'features are'),
    ({'match': 'a', 'format': 'json', 'ip_header': 'xff'}, 'ip_header only applies'),
])
def test_bad_rules_are_refused_with_their_position(rule, word):
    with pytest.raises(lf.FormatError, match='rule 2') as e:
        lf.rules_from({'service': [{'match': 'ok', 'format': 'plain'}, rule]})
    assert word in str(e.value)


def test_file_shape():
    for doc in ({}, {'service': []}, {'service': {}}, {'other': 1}):
        with pytest.raises(lf.FormatError): lf.rules_from(doc)


def test_without_a_file_the_rules_of_today():
    """No log-formats.toml: every service gets the same parser as before (domain/parse.py), by role."""
    rules = lf.default_rules(services.Profile())
    pick = lambda svc: lf.match(rules, 'tenant', svc)
    assert pick('nginx-ingress-controller').format == 'ingress-nginx' and pick('coredns').format == 'coredns'
    assert pick('web-frontend').format == 'nginx-frontend' and pick('event-api').format == 'events-json'
    assert pick('event-api').tag == 'APP' and pick('auth-service').features == ('logins',) and pick('report-service').features == ('pdf',)
    assert pick('anything-else').format == 'spring-boot'


def test_config_reads_the_file_and_stops_on_a_bad_one(tmp_path):
    c = config.load(env={'S4_STATE_DIR': str(tmp_path)}, dotenv=False)
    assert c.log_formats_file == str(tmp_path / 'log-formats.toml')
    assert config.log_format_rules(c) == lf.default_rules(services.from_config(c))          # no file yet
    f = tmp_path / 'log-formats.toml'
    f.write_text(open(EXAMPLE).read())
    assert config.log_format_rules(config.load(env={'S4_STATE_DIR': str(tmp_path)}, dotenv=False)) == example()
    f.write_text('[[service]]\nmatch = "a"\nformat = "yaml"\n')
    with pytest.raises(SystemExit, match='rule 1'): config.load(env={'S4_STATE_DIR': str(tmp_path)}, dotenv=False)
    f.write_text('[[service]\n')
    with pytest.raises(SystemExit, match='not valid TOML'): config.load(env={'S4_STATE_DIR': str(tmp_path)}, dotenv=False)
