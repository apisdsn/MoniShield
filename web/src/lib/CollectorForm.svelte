<!-- The log inputs of a collector (Collectors page, step 6): which files, journal, containers or Windows channels it sends.
     Only the options the platform really has are shown. A second group, Metrics, switches on the server metrics (every platform) and the
     container metrics (Docker hosts only; the reason is shown on the other platforms).
     `o` is edited in place (bindable); `show` makes empty fields count as mistakes (after "Create" was pressed). The server
     checks everything again (collector_config.py); the rules here are the same (collectors.js). -->
<script>
  import { t } from '../i18n.js';
  import { CHANNELS, MAX_FILES, checkOptions, containerMetricsOff, parseUnits } from '../collectors.js';
  import Icon from './Icon.svelte';
  let { platform, o = $bindable(), show = false, idp = 'cf' } = $props();

  const errs = $derived(checkOptions(platform, o));
  // an empty field is a mistake only after "Create" was pressed; a field with a wrong value is flagged while typing
  const rowErr = (i, k) => {
    const e = errs.files?.[i]?.[k];
    if (!e) return '';
    return e === 'empty' && !show ? '' : $t(k === 'path' ? `cl.err.path.${e}` : `cl.err.service.${e}`);
  };
  const noneErr = $derived(errs.none && show ? $t('cl.err.no_inputs') : '');
  const noContainers = $derived(containerMetricsOff(platform));
  const anyMetrics = $derived(!!o.host_metrics || (platform === 'docker' && !!o.container_metrics));
  const unitsErr = $derived(errs.units ? $t(`cl.err.${errs.units}`) : '');
  let unitsText = $state((o.units || []).join(' '));
  const PH = $derived(platform === 'windows' ? 'C:\\inetpub\\logs\\*.log' : '/var/log/app/*.log');

  function addFile() { if (o.files.length < MAX_FILES) o.files = [...o.files, { path: '', service: '' }]; }
  function removeFile(i) { o.files = o.files.filter((_, j) => j !== i); }
  function toggleChannel(c, on) { o.channels = on ? [...o.channels, c] : o.channels.filter((x) => x !== c); }
</script>

{#if platform === 'kubernetes'}
  <p class="muted note">{$t('cl.f.k8s')}</p>
{:else}
  <fieldset class="grp">
    <legend>{$t('cl.f.inputs')}</legend>

    {#if platform === 'windows'}
      <div class="sub" id="{idp}-ch">{$t('cl.f.channels')}</div>
      <div class="checks" role="group" aria-labelledby="{idp}-ch">
        {#each CHANNELS as c}
          <label class="check"><input type="checkbox" checked={o.channels.includes(c)} onchange={(e) => toggleChannel(c, e.currentTarget.checked)} /> {$t(`cl.ch.${c}`)}</label>
        {/each}
      </div>
    {:else}
      <label class="check"><input type="checkbox" bind:checked={o.journald} /> {$t('cl.f.journald')}</label>
      {#if o.journald}
        <div class="indent">
          <label for="{idp}-units" class="lbl">{$t('cl.f.units')}</label>
          <input id="{idp}-units" type="text" autocomplete="off" autocapitalize="none" spellcheck="false" placeholder="ssh.service cron.service"
            bind:value={unitsText} oninput={() => (o.units = parseUnits(unitsText))}
            aria-invalid={!!unitsErr} aria-describedby="{idp}-units-h{unitsErr ? ` ${idp}-units-e` : ''}" />
          <p id="{idp}-units-h" class="hint">{$t('cl.f.units_hint')}</p>
          {#if unitsErr}<p id="{idp}-units-e" class="err">{unitsErr}</p>{/if}
        </div>
      {/if}
      {#if platform === 'docker'}
        <label class="check"><input type="checkbox" bind:checked={o.containers} /> {$t('cl.f.containers')}</label>
        <p class="hint indent">{$t('cl.f.containers_hint')}</p>
      {/if}
    {/if}

    <div class="sub files-h" id="{idp}-files">{$t('cl.f.files')}</div>
    <p class="hint" id="{idp}-files-h">{$t('cl.f.files_hint')}</p>
    {#each o.files as f, i}
      <div class="frow" role="group" aria-label="{$t('cl.f.files')} {i + 1}">
        <div class="cell">
          <label class="sr-only" for="{idp}-p{i}">{$t('cl.f.path')} {i + 1}</label>
          <input id="{idp}-p{i}" type="text" autocomplete="off" autocapitalize="none" spellcheck="false" placeholder={PH} bind:value={f.path}
            aria-invalid={!!rowErr(i, 'path')} aria-describedby={rowErr(i, 'path') ? `${idp}-p${i}-e` : undefined} />
          {#if rowErr(i, 'path')}<p id="{idp}-p{i}-e" class="err">{rowErr(i, 'path')}</p>{/if}
        </div>
        <div class="cell svc">
          <label class="sr-only" for="{idp}-s{i}">{$t('cl.f.service')} {i + 1}</label>
          <input id="{idp}-s{i}" type="text" autocomplete="off" autocapitalize="none" spellcheck="false" placeholder={$t('cl.f.service')} bind:value={f.service}
            aria-invalid={!!rowErr(i, 'service')} aria-describedby={rowErr(i, 'service') ? `${idp}-s${i}-e` : undefined} />
          {#if rowErr(i, 'service')}<p id="{idp}-s{i}-e" class="err">{rowErr(i, 'service')}</p>{/if}
        </div>
        <button type="button" class="icon-btn rm" onclick={() => removeFile(i)} aria-label={$t('cl.f.remove_file', { n: i + 1 })} title={$t('cl.f.remove_file', { n: i + 1 })}>×</button>
      </div>
    {/each}
    {#if errs.toomany}<p class="err">{$t('cl.err.too_many_files')}</p>{/if}
    <button type="button" class="btn addf" onclick={addFile} disabled={o.files.length >= MAX_FILES}><Icon name="plus" size={16} />{$t('cl.f.add_file')}</button>
    {#if noneErr}<p class="err" role="alert">{noneErr}</p>{/if}
  </fieldset>
{/if}

<fieldset class="grp met">
  <legend>{$t('cl.f.metrics')}</legend>
  <label class="check"><input type="checkbox" bind:checked={o.host_metrics} /> {$t('cl.f.host_metrics')}</label>
  <p class="hint indent">{$t(platform === 'kubernetes' ? 'cl.f.host_metrics_hint.kubernetes' : platform === 'windows' ? 'cl.f.host_metrics_hint.windows' : 'cl.f.host_metrics_hint')}</p>
  <label class="check" class:off={!!noContainers}>
    <input type="checkbox" checked={platform === 'docker' && !!o.container_metrics} disabled={!!noContainers} onchange={(e) => { if (!noContainers) o.container_metrics = e.currentTarget.checked; }}
      aria-describedby={noContainers ? `${idp}-cm-why` : undefined} /> {$t('cl.f.container_metrics')}
  </label>
  <p class="hint indent" id="{idp}-cm-why">{noContainers ? $t(`cl.f.container_metrics_off.${noContainers}`) : $t('cl.f.container_metrics_hint')}</p>
  <p class="store" role="note">{anyMetrics ? $t('cl.f.metrics_store') : $t('cl.f.metrics_none')}</p>
</fieldset>

<style>
  .note { margin: 6px 0 0; font-size: 0.875rem; }
  .grp { border: 0; padding: 0; margin: 0; min-width: 0; }
  legend { font-size: 0.8125rem; color: var(--kpi-label); padding: 0; margin-bottom: 4px; }
  .sub { font-size: 0.8125rem; color: var(--kpi-label); margin-top: 12px; }
  .files-h { margin-top: 16px; }
  .checks { display: flex; flex-wrap: wrap; column-gap: 20px; }
  .check { display: flex; align-items: center; gap: 10px; min-height: var(--touch); font-size: 0.9375rem; color: var(--fg); cursor: pointer; }
  .check input { width: 18px; height: 18px; accent-color: var(--accent); flex: none; }
  .indent { margin-left: 28px; }
  .met { margin-top: 18px; }
  .check.off { cursor: not-allowed; color: var(--muted); }
  .check.off input { cursor: not-allowed; }
  .store { margin: 12px 0 0; padding: 10px 12px; border-radius: var(--r-ctl); background: var(--bg2); border: 1px solid var(--line); font-size: 0.8125rem; color: var(--muted); line-height: 1.55; }
  .lbl { display: block; font-size: 0.8125rem; color: var(--kpi-label); margin-top: 2px; }
  .hint { margin: 4px 0 0; font-size: 0.8125rem; color: var(--muted); }
  .err { margin: 4px 0 0; font-size: 0.8125rem; color: var(--err); }
  input[type='text'] { width: 100%; min-height: var(--touch); font-size: 1rem; border-radius: var(--r-ctl); margin-top: 4px; }
  input[aria-invalid='true'] { border-color: var(--err); }
  .frow { display: grid; grid-template-columns: minmax(0, 1.6fr) minmax(0, 1fr) var(--touch); gap: 8px; align-items: start; margin-top: 8px; }
  .rm { margin-top: 4px; font-size: 1.25rem; }
  .addf { margin-top: 12px; min-height: var(--touch); }
  @media (max-width: 640px) {
    .frow { grid-template-columns: minmax(0, 1fr) var(--touch); padding-bottom: 8px; border-bottom: 1px solid var(--row-line); }
    .cell.svc { grid-column: 1; }
    .rm { grid-column: 2; grid-row: 1; }
  }
</style>
