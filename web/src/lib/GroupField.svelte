<!-- The Group field of a collector (add dialog and "Change Group"): a text field, the existing groups as buttons to pick one, and a note saying
     what will happen (joins an existing group, creates a new one, or no group). `value` is edited in place; the server checks the name again. -->
<script>
  import { t } from '../i18n.js';
  import { checkGroup, groupNote } from '../collectors.js';
  let { value = $bindable(''), groups = [], idp = 'gf' } = $props();
  const note = $derived(groupNote(value, groups));
  const bad = $derived(checkGroup(value));
</script>

<div class="gf">
  <label for="{idp}-in">{$t('cl.f.group')} <span class="hint">{$t('cl.f.group_hint')}</span></label>
  <input id="{idp}-in" type="text" autocomplete="off" spellcheck="false" maxlength="40" placeholder={$t('cl.no_group')} bind:value
    aria-invalid={!!bad} aria-describedby="{idp}-note" />
  {#if groups.length}
    <div class="chips" role="group" aria-label={$t('cl.f.group_pick')}>
      {#each groups as g}
        <button type="button" class="pick" aria-pressed={note.name === g && note.kind === 'join'} onclick={() => (value = note.name === g && note.kind === 'join' ? '' : g)}>{g}</button>
      {/each}
    </div>
  {/if}
  <p id="{idp}-note" class="note" class:err={!!bad}>
    {#if bad}{$t('cl.err.group_invalid')}
    {:else if note.kind === 'join'}{$t('cl.f.group_join', { name: note.name })}
    {:else if note.kind === 'new'}{$t('cl.f.group_new', { name: note.name })}
    {:else}{$t('cl.f.group_none')}{/if}
  </p>
</div>

<style>
  .gf { display: flex; flex-direction: column; gap: 6px; margin-top: 12px; }
  label { font-size: 0.8125rem; color: var(--kpi-label); display: flex; flex-direction: column; gap: 2px; }
  .hint { color: var(--muted); }
  input[type='text'] { width: 100%; min-height: var(--touch); font-size: 1rem; border-radius: var(--r-ctl); }
  input[aria-invalid='true'] { border-color: var(--err); }
  .chips { display: flex; flex-wrap: wrap; gap: 6px; }
  .pick {
    min-height: var(--touch); padding: 0 14px; border-radius: var(--r-ctl); font: inherit; font-size: 0.875rem; cursor: pointer; color: var(--fg);
    background: var(--bg2); border: 1px solid var(--line-strong);
  }
  .pick[aria-pressed='true'] { border: 1.5px solid var(--accent); background: var(--seg-on); color: var(--accent-text); font-weight: 600; }
  .note { margin: 0; font-size: 0.8125rem; color: var(--muted); }
  .note.err { color: var(--err); }
</style>
