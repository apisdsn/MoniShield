<!-- What an admin does after a collector is added (Collectors page): the one-time enrollment token and the commands for the
     platform, each with a copy button. The token is shown only here (the server keeps a hash). Kubernetes also offers the
     Helm values for download: they hold no key. -->
<script>
  import { lang, t } from '../i18n.js';
  import { tLocal, utcToLocal } from '../format.js';
  import { installSteps } from '../collectors.js';
  import { toast } from './Toast.svelte';
  import CopyBlock from './CopyBlock.svelte';
  import Icon from './Icon.svelte';
  let { id, name, platform, token, expires, base } = $props();

  const steps = $derived(installSteps(platform, base, name, token));
  async function copyToken() {
    try { await navigator.clipboard.writeText(token); toast($t('adm.copied')); } catch { /* no clipboard permission: the token can be selected by hand */ }
  }
</script>

<p class="lead">{$t('cl.tok.note', { time: tLocal(utcToLocal(expires), $lang) })}</p>
<p class="lbl" id="tok-l">{$t('cl.tok.token')}</p>
<div class="row">
  <code class="tok" aria-labelledby="tok-l">{token}</code>
  <button type="button" class="btn" onclick={copyToken} aria-label={$t('cl.copy_token')}><Icon name="copy" size={16} />{$t('adm.copy')}</button>
</div>

<h3>{$t(`cl.tok.h.${platform}`)}</h3>
<p class="muted small">{$t('cl.tok.read')}</p>
{#if platform === 'kubernetes'}
  <p class="vals">
    <a class="btn accent" href="/api/v1/admin/collectors/{id}/config" download="values.yaml"><Icon name="download" size={16} />{$t('cl.tok.values')}</a>
  </p>
  <p class="muted small">{$t('cl.tok.values_hint')}</p>
{/if}
{#each steps as s}
  <CopyBlock title={$t(`cl.step.${s.id}`)} lines={s.lines} />
{/each}

<style>
  .lead { margin: 4px 0 12px; font-size: 0.875rem; }
  .lbl { margin: 0 0 6px; font-size: 0.8125rem; color: var(--kpi-label); }
  .row { display: flex; gap: 8px; align-items: flex-start; }
  .tok {
    flex: 1; min-width: 0; padding: 10px 12px; border-radius: var(--r-ctl); background: var(--bg2); border: 1px solid var(--line-strong);
    font-size: 0.875rem; overflow-wrap: anywhere; user-select: all; color: var(--fg);
  }
  .row .btn { flex: none; min-height: var(--touch); }
  h3 { margin: 22px 0 4px; font-size: 0.9375rem; font-weight: 600; color: var(--heading); }
  .small { margin: 0; font-size: 0.8125rem; }
  .vals { margin: 12px 0 4px; }
  .vals .btn { min-height: var(--touch); }
  @media (max-width: 560px) { .row { flex-direction: column; align-items: stretch; } }
</style>
