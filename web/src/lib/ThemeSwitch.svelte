<!-- Dark theme button in the header (owner request 2026-11-05): an icon button like search and sync (44 x 44, theme.css .icon-btn), a
     moon in the dark theme and a sun in the light theme. A real button: aria-pressed = dark theme is on, the name is "Dark theme",
     the tooltip says what a click does. -->
<script>
  import { t } from '../i18n.js';
  import { theme } from '../theme.js';
  import Icon from './Icon.svelte';
  const dark = $derived($theme === 'dark');
</script>

<button class="icon-btn" type="button" aria-pressed={dark} aria-label={$t('theme.dark')} title={$t(dark ? 'theme.to_light' : 'theme.to_dark')}
  onclick={() => theme.set(dark ? 'light' : 'dark')}>
  <Icon name={dark ? 'moon' : 'sun'} size={17} />
</button>
