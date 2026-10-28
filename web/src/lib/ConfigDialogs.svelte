<!-- Configuration pop-ups (owner request 2026-10-08): every part of the former Configuration page opens from the
     sidebar group "Configuration" as a dialog over the current page, instead of one long page. openConfig(section)
     with section = storage | kafka | maxmind | smtp | notif | blocklist | retention | public | server. The old addresses
     #/admin/konfigurasi and #/admin/notifikasi open the matching dialog (App.svelte). Admin only. -->
<script module>
  import { writable } from 'svelte/store';
  export const CONFIG = [
    { id: 'storage', icon: 'bucket' }, { id: 'kafka', icon: 'broker' }, { id: 'maxmind', icon: 'globe' }, { id: 'smtp', icon: 'mail' },
    { id: 'notif', icon: 'bell' }, { id: 'blocklist', icon: 'ban' }, { id: 'retention', icon: 'archive' }, { id: 'public', icon: 'globe' }, { id: 'server', icon: 'key' },
  ];
  export const configOpen = writable(null);
  export function openConfig(id) { configOpen.set(id); }
</script>

<script>
  import { t } from '../i18n.js';
  import Dialog from './Dialog.svelte';
  import AdminConfig from '../pages/AdminConfig.svelte';
  let { returnFocus = null } = $props();

  let open = $state(false), shown = $state(null);
  $effect(() => { open = !!$configOpen; if ($configOpen) shown = $configOpen; });
</script>

<Dialog bind:open title={shown ? $t(`nav.cfg.${shown}`) : ''} wide onclose={() => configOpen.set(null)} {returnFocus}>
  {#if open && shown}{#key shown}<AdminConfig only={shown} embedded />{/key}{/if}
</Dialog>
