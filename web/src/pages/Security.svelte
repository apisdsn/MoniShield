<!-- Keamanan (DRD §3.4, inv. §2.4): 8 KPI (4 + 4, U5), "Temuan utama" (9 aturan, komponen + kamus), 6 chart, 5 tabel,
     catatan kaki. Satu permintaan: GET /api/folders/{folder}/security (tabel halaman pertama ikut di respons).
     Tahap 21: data.scheme = 'crs' (bawaan) -> kategori = "CAPEC/keluarga CRS" (mis. '242/xss'), keparahan dari aturan
     CRS, kolom "Aturan" berisi ID CRS, catatan kaki menyebut CRS + versi + bagian request yang diperiksa;
     'lama' -> tampilan aturan sistem lama (uji kesetaraan). Semua teks data dirender sebagai teks. -->
<script>
  import { lang, t } from '../i18n.js';
  import { api } from '../api.js';
  import { num } from '../format.js';
  import Kpi from '../lib/Kpi.svelte';
  import ChartCard from '../lib/ChartCard.svelte';
  import HBar from '../lib/HBar.svelte';
  import DataTable from '../lib/DataTable.svelte';
  import Note from '../lib/Note.svelte';
  import Findings from '../lib/Findings.svelte';
  import AttackUrl from '../lib/AttackUrl.svelte';
  import IpCell from '../lib/IpCell.svelte';
  import SeverityTag from '../lib/SeverityTag.svelte';
  import StatusCode from '../lib/StatusCode.svelte';
  import Skeleton from '../lib/Skeleton.svelte';
  import ErrorState from '../lib/ErrorState.svelte';

  let { folder, hosts = {}, reloadKey = 0, onready = null } = $props();
  let data = $state.raw(null), busy = $state(false), error = $state(null);
  let seq = 0;

  async function load() {
    const my = ++seq;
    busy = true; error = null; onready?.(false);
    try {
      const j = await api.get(`/api/folders/${encodeURIComponent(folder)}/security`);
      if (my === seq) data = j;
    } catch (e) {
      if (my === seq) error = e;
    } finally {
      if (my === seq) { busy = false; onready?.(true); }
    }
  }
  $effect(() => { void [folder, reloadKey]; if (folder) load(); });

  // label (diterjemahkan, DRD §6.3): kategori serangan, tanda akun
  const slug = (s) => s.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '');
  const crs = $derived(data?.scheme === 'crs');
  // CRS: "<nama CAPEC> · <keluarga>" — keluarga ditulis bila menambah informasi (mis. CAPEC-242 Injeksi kode · XSS)
  const SAMA = new Set(['66/sqli', '63/xss', '126/lfi', '253/rfi', '664/ssrf', '310/reputation-scanner']);
  const cat = (c) => {
    if (!crs) return $t(`cat.${slug(c)}`);
    const [id, fam] = c.split('/');
    return SAMA.has(c) || !fam ? $t(`capec.${id}`) : `${$t(`capec.${id}`)} · ${$t(`fam.${slug(fam)}`)}`;
  };
  const capecId = (c) => `CAPEC-${c.split('/')[0]}`;
  const SEV = { 'Log4Shell / RCE': 3, 'SQL Injection': 3, 'Path Traversal / LFI': 3, XSS: 3, 'Probe file sensitif': 2, 'Scan CMS / WordPress': 2, 'Probe PHP / CGI': 2 };
  const sevCrs = $derived(Object.fromEntries((data?.by_category || []).map(([c, , v]) => [c, v])));
  const sev = (c) => (crs ? sevCrs[c] || 1 : SEV[c] || 1);
  const sevTok = (s) => (s === 3 ? '--err' : s === 2 ? '--warn' : '--neutral');
  const statusText = (sc) => Object.entries(sc).sort(([a], [b]) => a.localeCompare(b)).map(([c, n]) => `${c}×${n}`).join(' ');   // bentuk lama "200×3 401×1"
  const has2xx = (sc) => Object.keys(sc).some((c) => c.startsWith('2'));
  const org = (o) => (o === 'Tidak diketahui' ? $t('sec.unknown_owner') : o);
  const uniq = (a) => [...new Set(a)];

  // ---------------------------------------------------------------- temuan utama (urutan dan isi seperti lama)
  const findings = $derived.by(() => {
    if (!data) return [];
    const f = data.findings, k = data.kpi, T = data.tables;
    const urls = T['attack-urls'], full = !crs && urls.rows.length >= urls.total;     // aturan lama + daftar lengkap -> urutan persis seperti lama
    const rowsOf = (c) => urls.rows.filter((r) => r.category === c);
    const out = [];
    if (f.log4shell) {
      const rs = rowsOf('Log4Shell / RCE');
      out.push({ key: 'log4shell', b: {}, t: { n: num(f.log4shell.hits, $lang),
        ips: (full ? uniq(rs.map((r) => r.top_ip.ip)) : f.log4shell.ips).join(', '),
        ups: (full ? uniq(rs.flatMap((r) => r.upstreams)) : f.log4shell.upstreams).join(', ') } });
    }
    for (const c of f.by_critical_category) {
      const rs = rowsOf(c.category);
      out.push({ key: 'critical', b: { cat: cat(c.category) }, t: { n: num(c.hits, $lang),
        ips: (full ? uniq(rs.map((r) => r.top_ip.ip)) : c.ips).join(', '),
        statuses: (full ? uniq(rs.map((r) => statusText(r.status_counts))) : c.statuses).join(', ') } });
    }
    if (f.rancher_probe_hits) out.push({ key: 'rancher', b: {}, t: { n: num(f.rancher_probe_hits, $lang) } });
    if (k.attack_urls_2xx) out.push({ key: 'ok2xx', b: { n: num(k.attack_urls_2xx, $lang) }, t: {} });
    if (f.cloud_owners.length) {
      const ips = T['attack-ips'], fullIp = ips.rows.length >= ips.total;
      const CLOUD = /CLOUD|OCEAN|AMAZON|AWS|AZURE|MICROSOFT|HETZNER|OVH|LINODE|VULTR|ALIBABA|TENCENT|HOSTING|DATACENTER/i;
      const owners = fullIp && !crs ? uniq(ips.rows.filter((r) => Object.keys(r.cats).some((c) => sev(c) >= 2)).map((r) => r.ip.org || 'Tidak diketahui').filter((o) => CLOUD.test(o)))
                            : f.cloud_owners;
      out.push({ key: 'cloud', b: {}, t: { owners: owners.map(org).join(', ') } });
    }
    if (f.ombudsman_login_ips.length) out.push({ key: 'ombudsman', b: { n: num(f.ombudsman_login_ips.length, $lang) }, t: { ips: f.ombudsman_login_ips.join(', ') } });
    if (f.multi_account_ips.length) out.push({ key: 'stuffing', b: { n: num(f.multi_account_ips.length, $lang) }, t: { ips: f.multi_account_ips.join(', ') } });
    if (f.accounts_other_ip.length) {
      const ac = T.accounts, fullAc = ac.rows.length >= ac.total;
      const list = fullAc ? ac.rows.filter((r) => r.flags.includes('Sukses Dari IP Berbeda')).map((r) => r.account) : f.accounts_other_ip;
      out.push({ key: 'other_ip', b: { n: num(list.length, $lang) }, t: { accounts: list.join(', ') } });
    }
    if (k.resets) out.push({ key: 'resets', b: { n: num(k.resets, $lang) }, t: {} });
    return out;
  });

  // tanda "Sukses Dari IP Berbeda" -> "(ISP Sama)" bila semua IP sukses ber-ASN sama dengan salah satu IP gagal (lama)
  const flagsOf = (r) => {
    const same = r.ok_ips.length && r.ok_ips.every((ip) => r.fail_ips.some((f) => f.asn && f.asn === ip.asn));
    return r.flags.map((f) => (f === 'Sukses Dari IP Berbeda' && same ? 'sukses_dari_ip_berbeda_isp_sama' : slug(f)));
  };
  // catatan kejadian "<waktu> sukses dari <ip>" (data lama, kalimat Indonesia) -> dua bahasa
  const noteText = (n) => { const m = /^(.+) sukses dari (.+)$/.exec(n); return m ? $t('sec.note_ok_from', { time: m[1], ip: m[2] }) : n; };   // waktu apa adanya (WIB, seperti lama)
  const accountsOf = (r) => new Set(r.accounts.map((u) => u.split('@')[0])).size;
</script>

{#if error && !data}
  <ErrorState {error} onretry={load} />
{:else if !data}
  <Skeleton kpis={8} charts={6} />
{:else}
  {@const k = data.kpi}
  {@const T = data.tables}
  <div class="content" class:dim={busy}>
    <div class="kpis four">
      <Kpi icon="shield" label={$t('sec.kpi.attack_requests')} value={k.attack_requests} tone="err" />
      <Kpi icon="globe" label={$t('sec.kpi.attack_ips')} value={k.attack_ips} tone="warn" />
      <Kpi icon="alert" label={$t(crs ? 'sec.kpi.critical_crs' : 'sec.kpi.critical')} value={k.critical_hits} tone="err" />
      <Kpi icon="pulse" label={$t('sec.kpi.urls_2xx')} value={k.attack_urls_2xx} tone="warn" />
      <Kpi icon="key" label={$t('sec.kpi.login_fail_ips')} value={k.login_fail_ips} tone="warn" />
      <Kpi icon="user" label={$t('sec.kpi.ok_after_fail')} value={k.accounts_ok_after_fail} tone="warn" />
      <Kpi icon="users" label={$t('sec.kpi.ok_other_ip')} value={k.accounts_ok_other_ip} tone="err" />
      <Kpi icon="refresh" label={$t('sec.kpi.resets')} value={k.resets} tone="err" />
    </div>

    <Findings items={findings} />

    <div class="grid">
      {#if data.by_category.length}
        <ChartCard title={$t('sec.by_category')} type="bar" labels={data.by_category.map((c) => cat(c[0]))}
          datasets={[{ label: $t('col.hits'), data: data.by_category.map((c) => c[1]), colors: data.by_category.map((c) => sevTok(c[2])) }]}
          options={{ indexAxis: 'y', plugins: { legend: { display: false } } }} />
        <ChartCard title={$t('sec.by_hour')} type="line" timeAxis labels={data.by_hour.map((h) => h[0])}
          datasets={[{ label: $t('col.hits'), data: data.by_hour.map((h) => h[1]), color: '--err' }]} />
      {/if}
      {#if data.top_ips.length}
        <ChartCard title={$t('sec.top_ips')} type="bar" labels={data.top_ips.map((r) => r.ip.ip)}
          datasets={[{ label: $t('col.hits'), data: data.top_ips.map((r) => r.hits), colors: data.top_ips.map((r) => (r.max_severity === 3 ? '--err' : r.max_severity === 2 ? '--warn' : '--muted')) }]}
          tooltipTitle={(i) => (data.top_ips[i].ip.org ? [data.top_ips[i].ip.ip, data.top_ips[i].ip.org] : data.top_ips[i].ip.ip)}
          options={{ indexAxis: 'y', plugins: { legend: { display: false } } }} />
        <HBar title={$t('sec.by_owner')} rows={data.by_owner.map(([o, n]) => ({ label: org(o), value: n }))} color="--violet" valueLabel={$t('col.hits')} />
      {/if}
      {#if k.login_fail_ips}
        <ChartCard title={$t('sec.login_by_hour')} type="line" timeAxis labels={data.login_by_hour.map((h) => h[0])}
          datasets={[{ label: $t('sec.wrong_pw'), data: data.login_by_hour.map((h) => h[1]), color: '--warn' }]} />
        <HBar title={$t('sec.login_top_ips')} rows={data.login_top_ips.map((r) => ({ label: r.ip, value: r.fail, org: r.org }))} color="--warn" valueLabel={$t('sec.wrong_pw')} />
      {/if}
      {#if !data.nginx}
        <Note>{$t('sec.no_nginx')}</Note>
      {/if}

      <DataTable title={$t('sec.t.urls')} {folder} table="attack-urls" initial={T['attack-urls']} maxHeight={560} columns={[
        { key: 'category', label: $t('col.category'), custom: true, sort: true, minw: 150 },
        { key: 'method_path', label: $t('col.url'), custom: true, minw: 340 },
        ...(crs ? [{ key: 'rules', label: $t('sec.col.rules'), custom: true, minw: 90 }] : []),
        { key: 'hits', label: $t('col.hits'), type: 'num', sort: true },
        { key: 'top_ip', label: 'IP', type: 'ip', more: (r) => r.ip_count - 1 },
        { key: 'status_counts', label: $t('col.status'), custom: true },
        { key: 'sizes', label: $t('sec.col.sizes'), type: 'num', fmt: (r) => r.sizes.join(', ') },
        { key: 'upstreams', label: $t('sec.col.upstream'), custom: true, minw: 170 },
        { key: 'first', label: $t('col.time'), type: 'range', to: 'last', cls: () => 'nowrap', sort: true },
      ]}>
        {#snippet cell(r, c)}
          {#if c.key === 'category'}<span title={crs ? capecId(r.category) : undefined}><SeverityTag level={r.severity} text={cat(r.category)} /></span>{#if crs}<div class="muted small">{capecId(r.category)}</div>{/if}
          {:else if c.key === 'rules'}<div class="small mono">{#each r.rules as id}<div>{id}</div>{/each}</div>
          {:else if c.key === 'method_path'}<AttackUrl methodPath={r.method_path} upstreams={r.upstreams} ua={r.ua} {hosts} />
          {:else if c.key === 'status_counts'}<StatusCode counts={r.status_counts} />{#if r.severity >= 2 && has2xx(r.status_counts)}<div class="WARN small">{$t('sec.verify_2xx')}</div>{/if}
          {:else if c.key === 'upstreams'}<div class="small">{#each r.upstreams as u}<div class="nowrap">{u}</div>{/each}</div>{/if}
        {/snippet}
      </DataTable>

      <DataTable title={$t('sec.t.ips')} {folder} table="attack-ips" initial={T['attack-ips']} maxHeight={560} columns={[
        { key: 'ip', label: 'IP', type: 'ip', sort: true },
        { key: 'hits', label: $t('col.hits'), type: 'num', sort: true },
        { key: 'cats', label: $t('col.category'), custom: true, minw: 190 },
        { key: 'status_counts', label: $t('col.status'), type: 'statuses' },
        { key: 'ua', label: 'User-Agent', clip: true, minw: 220 },
        { key: 'first', label: $t('col.time'), type: 'range', to: 'last', cls: () => 'nowrap', sort: true },
      ]}>
        {#snippet cell(r)}
          {#each Object.entries(r.cats).sort((a, b) => sev(b[0]) - sev(a[0])) as [c, n]}<div class="tagrow"><SeverityTag level={sev(c)} text={cat(c)} /> <span class="muted">{num(n, $lang)}</span></div>{/each}
        {/snippet}
      </DataTable>

      {#if T.accounts.total}
        <DataTable title={$t('sec.t.accounts')} {folder} table="accounts" initial={T.accounts} maxHeight={560} columns={[
          { key: 'account', label: $t('sec.col.account'), cls: () => 'strong', sort: true, minw: 170 },
          { key: 'fail', label: $t('sec.col.fail'), type: 'num', cls: () => 'WARN', sort: true },
          { key: 'lock', label: $t('sec.col.reset'), type: 'num', cls: (r) => (r.lock ? 'ERROR' : ''), sort: true },
          { key: 'ok', label: $t('sec.col.ok'), type: 'num', sort: true },
          { key: 'fail_ips', label: $t('sec.col.fail_ips'), type: 'ips' },
          { key: 'ok_ips', label: $t('sec.col.ok_ips'), custom: true },
          { key: 'flags', label: $t('sec.col.flags'), custom: true, minw: 220 },
          { key: 'first', label: $t('col.time'), type: 'range', to: 'last', cls: () => 'nowrap', sort: true },
        ]}>
          {#snippet cell(r, c)}
            {#if c.key === 'ok_ips'}{#each r.ok_ips as ip}<IpCell {ip} />{:else}<span class="muted">–</span>{/each}
            {:else}
              {#each flagsOf(r) as f}<div class="tagrow"><SeverityTag level={1} text={$t(`flag.${f}`)} /></div>{/each}
              {#if r.notes.length}<div class="muted small">{#each r.notes as n}<div>{noteText(n)}</div>{/each}</div>{/if}
            {/if}
          {/snippet}
        </DataTable>
      {/if}

      <DataTable title={$t('sec.t.logins')} {folder} table="login-ips" initial={T['login-ips']} maxHeight={560} columns={[
        { key: 'ip', label: 'IP', custom: true, sort: true },
        { key: 'fail', label: $t('sec.wrong_pw'), type: 'num', cls: () => 'WARN', sort: true },
        { key: 'lock', label: $t('sec.col.reset_3x'), type: 'num', cls: (r) => (r.lock ? 'ERROR' : ''), sort: true },
        { key: 'ok', label: $t('sec.col.login_ok'), type: 'num', sort: true },
        { key: 'accounts', label: $t('sec.col.accounts_tried'), custom: true, minw: 180 },
        { key: 'first', label: $t('col.time'), type: 'range', to: 'last', cls: () => 'nowrap', sort: true },
      ]}>
        {#snippet cell(r, c)}
          {#if c.key === 'ip'}
            {#if accountsOf(r) >= 3}<div class="tagrow"><SeverityTag level={1} text={$t('sec.multi_account')} /></div>{/if}<IpCell ip={r.ip} />
          {:else}<div class="small">{#each r.accounts as a}<div>{a}</div>{/each}</div>{/if}
        {/snippet}
      </DataTable>

      <DataTable title={$t('sec.t.ip4xx')} {folder} table="ip-4xx" initial={T['ip-4xx']} columns={[
        { key: 'ip', label: 'IP', type: 'ip', sort: true },
        { key: 'n', label: $t('sec.col.n4xx'), type: 'num', sort: true },
        { key: 'ua', label: 'User-Agent', clip: true },
      ]} />
    </div>
    <p class="muted foot">{crs ? $t('sec.footnote_crs', { version: data.crs.version, pl: data.crs.paranoia, n: data.crs.rules, th: data.crs.threshold }) : $t('sec.footnote')}</p>
  </div>
{/if}

<style>
  .content { transition: opacity 0.15s; }
  .content.dim { opacity: 0.6; }
  .foot { font-size: 0.75rem; margin-top: 18px; }
  :global(.small) { font-size: 0.75rem; }
  :global(td.strong) { font-weight: 600; }
  .tagrow { margin: 2px 0; white-space: nowrap; }
</style>
