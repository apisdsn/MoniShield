# 04c — Attack detection: OWASP CRS + CAPEC (Stage 21)

Comparison report of the old detection rules (the old system's patterns, `attack_cat`) with the OWASP Core Rule Set
(CRS) rules that v2 has used since Stage 21. Technical details: TRD §4.6; plan: `04-plan.md` Stage 21.
The figures below were computed from the real database (11 folders, 308,158 ingress nginx log lines) at paranoia
level 1 and an anomaly score threshold of 5.

## Summary

- **Rule source**: OWASP CRS **v4.30.0**, commit `e03a4f6dabc7a30ebd8c52c97d28a154f590a48f`, Apache 2.0 license
  (`monishield/CRS-LICENSE.txt`). Processed once by `tools/ambil_crs.py` into `monishield/crs_rules.json`, which
  is part of the repo: the dashboard downloads nothing at runtime. `py tools/ambil_crs.py --check` proves that the file
  in the repo equals the result of re-processing the pinned release.
- **Rules**: of the 203 rules in the relevant files REQUEST-913, 930–934, 941, 942, 944, **176 are taken**
  (paranoia level 1: 91, 2: 61, 3: 22, 4: 2) and **27 are skipped** together with their reasons (list below).
- **What is inspected**: only the parts of the request recorded in the nginx log: URI, query arguments (names and values),
  file name, request line, and User-Agent. POST body, cookies and other headers are not recorded. **This is not a
  WAF replacement**; the same sentence is in the footnote of the Security page.
- **How matching works** (as in ModSecurity): values are matched as bytes, `t:` transformations are applied
  in order, anomaly score = sum of the scores of the matched rules (CRITICAL 5, ERROR 4, WARNING 3, NOTICE 2); a request
  is considered an attack when its score is ≥ 5 (the CRS default threshold).
- **Category** = CAPEC from the rule tags, plus the CRS attack family when the CAPEC is generic (e.g. CAPEC-242
  Code Injection · XSS). The CAPEC is chosen from the rules with the highest total score. Bilingual CAPEC names are in
  `monishield/capec.json`.
- **The old rules remain**: the `attack_cat` column and the `agg_attack_*` aggregates are unchanged, so the
  E1–E4 parity tests keep running with `S4_ATTACK_RULES=lama`. The default view uses CRS
  (`S4_ATTACK_RULES=crs`, decision S1b).

## Old vs CRS per folder

Only 5 of the 11 folders have an ingress nginx log; the other folders have no data for per-URL detection.
"Matched by both" = requests flagged by the old rules **and** by CRS.

| Folder | Old requests | Old IPs | CRS requests | CRS IPs | Matched by both | Old only | CRS only |
|---|--:|--:|--:|--:|--:|--:|--:|
| 2026-09-29 | 155 | 12 | 27 | 5 | 25 | 130 | 2 |
| 2026-09-30 | 32 | 9 | 28 | 7 | 27 | 5 | 1 |
| 2026-10-03 | 10 | 4 | 2 | 1 | 2 | 8 | 0 |
| 2026-10-05 | 30 | 3 | 3 | 1 | 3 | 27 | 0 |
| 2026-10-06 | 88 | 14 | 50 | 4 | 29 | 59 | 21 |
| **Total** | **315** | | **110** | | **86** | **229** | **24** |

**Why CRS flags fewer.** Most of the "old only" requests are common tool User-Agents (`Go-http-client` 49,
`curl` 33, `python-requests` 1) and CMS/WordPress probes in the form of plain paths (`/wp-login.php`, `/phpmyadmin/`, `/pma/`) that
CRS does not consider attacks without a malicious payload. **Why there are "CRS only" requests.** 24 requests are probes for
sensitive files whose names are **percent-encoded** to evade patterns (e.g. `/%61%77%73-%63%6f%6e%66%69%67.%6a%73%6f%6e`
= `/aws-config.json`, `/%70%68%70%69%6e%66%6f` = `/phpinfo`); CRS applies `urlDecode` before matching,
the old patterns do not.

## Per CRS category (all folders)

| Category | Name (EN) | Requests | IPs | Folders |
|---|---|--:|--:|--:|
| CAPEC-126 / lfi | Path Traversal | 59 | 9 | 5 |
| CAPEC-88 / rce | OS Command Injection · RCE | 25 | 8 | 3 |
| CAPEC-310 / reputation-scanner | Scanning for Vulnerable Software | 13 | 1 | 1 |
| CAPEC-6 / rce | Argument Injection · RCE (obfuscated Log4Shell in the User-Agent, rule 944150) | 11 | 5 | 3 |
| CAPEC-242 / xss | Code Injection · XSS | 1 | 1 | 1 |
| CAPEC-66 / sqli | SQL Injection | 1 | 1 | 1 |

## Old category → also matched by CRS?

| Old rule | Requests | Also matched by CRS | CRS category used |
|---|--:|--:|---|
| UA tool/scanner otomatis (automated tool/scanner UA) | 85 | 0 | – (common tool UAs, see Limitations 3) |
| Scan CMS / WordPress | 82 | 1 | CAPEC-126/lfi |
| Probe file sensitif (sensitive file probe) | 64 | 36 | CAPEC-126/lfi, CAPEC-310 |
| Probe PHP / CGI | 47 | 13 | CAPEC-310, CAPEC-126/lfi |
| Log4Shell / RCE | 33 | **33** | CAPEC-6/rce, CAPEC-88/rce |
| SQL Injection | 2 | **2** | CAPEC-66/sqli, CAPEC-88/rce |
| Path Traversal / LFI | 1 | 0 | – (direct `/etc/passwd` URL; rule 930120 PL1 inspects arguments only) |
| XSS | 1 | **1** | CAPEC-242/xss |

All high-severity attacks according to the old rules (Log4Shell, SQLi, XSS) are also caught by CRS.

## Most frequently matched CRS rules

930130 (restricted file access) 60 · 944150 (Log4j) 25 · 932130 (Unix shell expression) 16 · 933135 (PHP
variables) 14 · 913100 (scanner UA) 13 · 932160 and 932235 (shell commands) 9 · the rest ≤ 2 (25 different rules).

## False positives on normal traffic

Of the **30,512** unique (method, path) pairs that are **clean** according to the old rules, CRS at paranoia level 1
flags **13 (0.043 %)**; the plan requirement of < 0.5 % is met. Causes: 930130 ×11 (application paths containing
names resembling system files) and 932130 ×2. Re-measured on every `pytest tests/test_detect.py` (test
`test_salah_tuduh_lalu_lintas_normal`, which runs when the real database is available).

## Performance

`derive --all` (11 folders, including CRS classification) 39 seconds; `ingest --folder 2026-09-29 --force` 24 seconds
(requirement ≤ 60). Classification per unique (method, path, UA) pair with a cache; `@pm` patterns are compiled into a
trie-shaped regex (≈ 1 ms per path).


## Skipped rules (27)

| Reason | Count | Rule IDs |
|---|--:|---|
| Rule chain (`chain`): the second rule inspects something not in the log, or its result depends on transaction variables | 15 | 931130, 932200, 932205, 932206, 932207, 932240, 933150, 941310, 942130, 942131, 942200, 942440, 942521, 944110, 944120 |
| Target not in the nginx log (uploaded files, `X-Filename` header, cookies) | 7 | 932180, 933110, 933111, 933220, 942420, 942421, 944140 |
| libinjection operators (`@detectSQLi`, `@detectXSS`): a C library with no equivalent in Python | 4 | 941100, 941101, 942100, 942101 |
| Negated operator `!@validateByteRange` (character-checking rule, without a paranoia level) | 1 | 941010 |

No pattern is rejected by the Python regex engine: all single-byte `\x{HH}` escapes are converted to `\xHH`, which
means the same for byte matching. The tool will log (rather than silently change) it when a future release
contains a pattern that cannot be used.

## Limitations

1. **Classic SQL tautology** (`' OR 1=1--`) is not caught at paranoia level 1, because in the original CRS it is
   libinjection (942100) that catches it. At paranoia level 2 it is caught by a regex rule (tested in
   `tests/test_detect.py::test_keterbatasan_tautologi_sql_tanpa_libinjection`). Other SQLi payloads (UNION
   SELECT, WAITFOR DELAY, comments) are still caught at level 1.
2. **Body, cookies, other headers** are not recorded in the nginx log, so attacks present only there are not
   visible. The "at the ingress" approach (ModSecurity/Coraza in detection mode) can see them; proposed to the cluster
   administrators (S1a), outside this stage.
3. **Scanners flagged only by a common User-Agent** (`curl`, `python-requests`, `Go-http-client`) are not
   considered attacks by CRS (rule 913100 only contains names of scanning tools such as sqlmap, Nikto, Nuclei).
   The old rules flag some of those UAs as "UA scanner", so the number of requests and attacker IPs goes down.
4. **2xx responses** on attack URLs are usually the SPA fallback (`index.html`), same as before: the response
   size column is still shown for verification.
5. Paranoia level and threshold can be configured (`S4_ATTACK_PARANOIA` 1–4). Changing it makes the next ingest
   re-derive the CRS aggregates of all folders (column `folder_state.crs_version`).
