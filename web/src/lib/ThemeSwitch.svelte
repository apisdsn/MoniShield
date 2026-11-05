<!-- Dark theme switch in the header (owner request 2026-11-04): role="switch", checked = dark. A 56 x 30 track with a round
     knob that slides left (light, sun) or right (dark, moon), inside a 44 px bordered box like the other header controls. -->
<script>
  import { t } from '../i18n.js';
  import { theme } from '../theme.js';
  import Icon from './Icon.svelte';
  const dark = $derived($theme === 'dark');
</script>

<button class="sw" type="button" role="switch" aria-checked={dark} aria-label={$t('theme.dark')} title={$t('theme.dark')}
  onclick={() => theme.set(dark ? 'light' : 'dark')}>
  <span class="track" aria-hidden="true"><span class="knob"><Icon name={dark ? 'moon' : 'sun'} size={15} stroke={2} /></span></span>
</button>

<style>
  /* the same 44 px bordered box as the other header controls; the track and knob stay round inside it */
  .sw {
    display: inline-grid; place-items: center; height: var(--touch); min-width: var(--touch); padding: 0 6px; margin: 0;
    border: 1px solid var(--line-strong); background: var(--bg2); cursor: pointer; border-radius: var(--r-ctl);
  }
  .sw:hover { background: var(--ctl-hover); }
  .track {
    position: relative; width: 56px; height: 30px; border-radius: 999px; background: var(--line); border: 1px solid transparent;
    transition: background-color 0.18s ease, border-color 0.18s ease;
  }
  .sw[aria-checked='true'] .track { background: var(--seg-on); border-color: var(--accent); }
  .knob {
    position: absolute; top: 2px; left: 2px; width: 24px; height: 24px; border-radius: 50%; display: grid; place-items: center;
    background: var(--accent); color: var(--brand-fg); transition: transform 0.18s ease;
  }
  .sw[aria-checked='true'] .knob { transform: translateX(26px); }
  @media (max-width: 420px) { .sw { padding: 0 4px; } }
  @media (prefers-reduced-motion: reduce) { .track, .knob { transition: none; } }
</style>
