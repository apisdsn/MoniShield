<!-- Ready-to-use blocklist (owner request 2026-10-07, suggestion 6; API GET …/security/blocklist). Choose a format
     (nginx `deny`, ingress-nginx annotation, text), range (this folder / 7 / 30 days), minimum severity -> preview of the IP
     count + those excluded (private, own network, server exclusion list) -> Download or Copy. -->
<script>
  import { lang, t } from '../i18n.js';
  import { api } from '../api.js';
  import { num } from '../format.js';
  import { errText } from '../srv.js';
  import Dialog from './Dialog.svelte';

  let { folder, open = $bindable(false) } = $props();
  let format = $state('nginx'), days = $state(1), sev = $state(1), prev = $state.raw(null), err = $state(null), copied = $state(false), seq = 0;

  const q = (f) => `/api/folders/${encodeURIComponent(folder)}/security/blocklist?format=${f}&days=${days}&min_severity=${sev}&lang=${$lang}`;
  $effect(() => {
    if (!open) return;
    void [days, sev, folder];
    const my = ++seq; err = null;
    api.get(q('json')).then((r) => { if (my === seq) prev = r; }, (e) => { if (my === seq) err = $errText(e); });
  });
  async function copy() {
    try {
      const txt = await fetch(q(format), { credentials: 'same-origin' }).then((r) => r.text());
      await navigator.clipboard.writeText(txt);
      copied = true; setTimeout(() => (copied = false), 1500);
    } catch (e) { err = $t('bl.copy_fail'); }
  }
  const ex = $derived(prev ? Object.values(prev.excluded).reduce((a, b) => a + b, 0) : 0);
</script>

<Dialog bind:open title={$t('bl.title')}>
  <div class="grid">
    <label for="bl-f">{$t('bl.format')}</label>
    <select id="bl-f" bind:value={format}>
      <option value="nginx">{$t('bl.f.nginx')}</option>
      <option value="ingress">{$t('bl.f.ingress')}</option>
      <option value="txt">{$t('bl.f.txt')}</option>
    </select>
    <label for="bl-d">{$t('bl.range')}</label>
    <select id="bl-d" bind:value={days}>
      <option value={1}>{$t('bl.d1')}</option><option value={7}>{$t('bl.dn', { n: 7 })}</option><option value={30}>{$t('bl.dn', { n: 30 })}</option>
    </select>
    <label for="bl-s">{$t('bl.sev')}</label>
    <select id="bl-s" bind:value={sev}>
      <option value={1}>{$t('bl.s1')}</option><option value={2}>{$t('bl.s2')}</option><option value={3}>{$t('bl.s3')}</option>
    </select>
  </div>
  <div aria-live="polite">
    {#if err}<p class="err">{err}</p>
    {:else if prev}
      <p class="sum">{$t('bl.preview', { n: num(prev.count, $lang) })}{#if ex} {$t('bl.excluded', { n: num(ex, $lang) })}{/if}</p>
      {#if prev.count}<p class="muted small ips"><code>{prev.ips.slice(0, 8).map((x) => x.ip).join(', ')}{prev.count > 8 ? ', …' : ''}</code></p>{/if}
    {/if}
  </div>
  <p class="muted small">{$t('bl.note')}</p>
  {#snippet footer()}
    <button class="btn" onclick={copy} disabled={!prev?.count}>{copied ? $t('bl.copied') : $t('bl.copy')}</button>
    <a class="btn primary" class:disabled={!prev?.count} href={q(format)} download>{$t('bl.download')}</a>
  {/snippet}
</Dialog>

<style>
  .grid { display: grid; grid-template-columns: max-content minmax(0, 1fr); gap: 10px 14px; align-items: center; margin-bottom: 12px; }
  label { font-size: 0.8125rem; color: var(--kpi-label); }
  select { min-height: var(--touch); border-radius: 12px; }
  .sum { font-size: 0.9375rem; font-weight: 600; margin-top: 4px; }
  .ips code { word-break: break-all; }
  .err { color: var(--err); }
  .small { font-size: 0.75rem; margin-top: 8px; }
  .disabled { pointer-events: none; opacity: 0.5; }
  @media (max-width: 420px) { .grid { grid-template-columns: minmax(0, 1fr); } }
</style>
