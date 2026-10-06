<!-- Command Center (Tahap 22, DRD §12, TRD §12): menyerap tab Peta IP (ASUMSI DRD §12) di alamat yang sama (#/peta, ?modul=).
     Satu permintaan: GET /api/folders/{folder}/command[?module=…] = KPI utama + "yang perlu perhatian" + data peta (respons
     Peta IP). Susunan: 6 KPI operasional · pemilih modul + angka peta · peta selebar dan setinggi layar (isi utama, permintaan
     pemilik) · kartu perhatian · tabel alur. Sumber = folder log (Kafka ditunda, Tahap 23); diperbarui saat ingest atau "Muat ulang".
     Ganti modul hanya menyaring peta; posisi dan zoom peta tetap. -->
<script>
  import { lang, t } from '../i18n.js';
  import { api } from '../api.js';
  import { num } from '../format.js';
  import { route, go, build } from '../state.js';
  import Kpi from '../lib/Kpi.svelte';
  import Alert from '../lib/Alert.svelte';
  import FlowMap from '../lib/FlowMap.svelte';
  import Note from '../lib/Note.svelte';
  import Skeleton from '../lib/Skeleton.svelte';
  import ErrorState from '../lib/ErrorState.svelte';

  let { folder, server = null, reloadKey = 0, onready = null } = $props();
  let data = $state.raw(null), busy = $state(false), error = $state(null);
  let seq = 0;
  const module = $derived($route.module || null);
  async function load() {
    const my = ++seq;
    busy = true; error = null; onready?.(false);
    try {
      const q = module ? `?module=${encodeURIComponent(module)}` : '';
      const j = await api.get(`/api/folders/${encodeURIComponent(folder)}/command${q}`);
      if (my === seq) data = j;
    } catch (e) {
      if (my === seq) {
        if (e.status === 404 && module) go({ module: null }, { replace: true });   // modul tidak ada di folder ini -> semua modul
        else error = e;
      }
    } finally {
      if (my === seq) { busy = false; onready?.(true); }
    }
  }
  $effect(() => { void [folder, module, reloadKey]; if (folder) load(); });

  // butir perhatian: kunci + angka dari server, kalimat dari kamus, tautan ke halaman asalnya
  const items = $derived((data?.attention || []).map((a) => {
    const p = { n: num(a.n, $lang), ips: num(a.ips ?? 0, $lang), resets: num(a.resets ?? 0, $lang), kind: a.kind ?? '', upstream: a.upstream ?? '', top: num(a.top ?? 0, $lang) };
    const text = a.key === 'n5xx' && !a.upstream ? $t('cc.a.n5xx.text_plain') : a.key === 'login' && !a.resets ? $t('cc.a.login.text_none') : $t(`cc.a.${a.key}.text`, p);
    return { title: $t(`cc.a.${a.key}.title`, p), text, tone: a.tone, link: $t('cc.open', { page: $t(`tab.${a.tab}`) }),
             href: build({ tab: a.tab, service: null, folder, module: null }) };
  }));
</script>

{#if error && !data}
  <ErrorState {error} onretry={load} />
{:else if !data}
  <Skeleton kpis={6} charts={1} />
{:else}
  {@const k = data.kpi}
  {@const m = data.map}
  <div class="content" class:dim={busy}>
    <div class="kpis cc">
      <Kpi icon="pulse" label={$t('cc.kpi.requests')} value={k.requests} missing={$t('cc.no_nginx')} />
      <Kpi icon="alert" label={$t('cc.kpi.n5xx')} value={k.n5xx} tone={k.n5xx ? 'err' : null} missing={$t('cc.no_nginx')} />
      <Kpi icon="alert" label={$t('cc.kpi.errors')} value={k.errors} tone={k.errors ? 'err' : null} />
      <Kpi icon="server" label={$t('cc.kpi.upstream')} value={k.upstream_errors} tone={k.upstream_errors ? 'err' : null} />
      <Kpi icon="shield" label={$t('cc.kpi.attack_ips')} value={k.attack_ips} tone={k.attack_ips ? 'warn' : null} />
      <Kpi icon="key" label={$t('cc.kpi.login_ips')} value={k.login_fail_ips} tone={k.login_fail_ips ? 'warn' : null} />
    </div>

    {#snippet attention()}
      {#if items.length}
        <Alert title={$t('cc.attention')} {items} />
      {:else}
        <section class="card calm" aria-label={$t('cc.attention')}><h2>{$t('cc.attention')}</h2><p class="muted">{$t('cc.none')}</p></section>
      {/if}
    {/snippet}

    {#if m.available}
      <div class="modsel">
        <label for="map-mod" class="sr-only">{$t('map.module')}</label>
        <select id="map-mod" value={module ?? ''} onchange={(e) => go({ module: e.currentTarget.value || null })}>
          <option value="">{$t('map.all_modules')}</option>
          {#each m.modules as x}<option value={x}>{x}</option>{/each}
        </select>
        <dl class="mapstats" aria-label={$t('cc.map_stats')}>
          {#each [['source_ips', 'ips'], ['locations', 'locations'], ['countries', 'countries'], ['modules', 'modules'], ['dest_pods', 'pods'], ['requests', 'requests']] as [key, lbl]}
            <div><dt>{$t(`map.kpi.${lbl}`)}</dt><dd>{num(m.kpi[key], $lang)}</dd></div>
          {/each}
        </dl>
      </div>
      <div class="grid">
        <FlowMap data={m} {folder} module={m.module} {server} aside={attention} tall />
      </div>
    {:else}
      <div class="grid">{@render attention()}</div>
      <Note>{$t('map.no_nginx')}</Note>
    {/if}
  </div>
{/if}

<style>
  .content { transition: opacity 0.15s; }
  .content.dim { opacity: 0.6; }
  .modsel { display: flex; flex-wrap: wrap; align-items: center; gap: 10px 22px; margin-bottom: 14px; }
  .modsel select { min-width: 220px; max-width: 100%; }
  .mapstats { display: flex; flex-wrap: wrap; gap: 6px 18px; margin: 0; font-size: 0.8125rem; }
  .mapstats div { display: flex; gap: 6px; align-items: baseline; }
  .mapstats dt { color: var(--muted); }
  .mapstats dd { margin: 0; color: var(--fg); font-weight: 600; font-variant-numeric: tabular-nums; }
  .calm h2 { font-size: 0.9375rem; font-weight: 600; color: var(--heading); margin: 0 0 8px; }
  .calm p { margin: 0; font-size: 0.8125rem; }
  @media (min-width: 1200px) { .kpis.cc { grid-template-columns: repeat(6, minmax(0, 1fr)); } }
</style>
