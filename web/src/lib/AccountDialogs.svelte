<!-- Own-account pop-ups (owner request 2026-10-08): "Change password" and "Account email" open as a dialog over the
     current page instead of a page of their own. Opened from the user menu with openAccount('password' | 'email');
     the old addresses #/sandi and #/email open the same dialog (App.svelte). The forced password change after sign-in
     stays a full screen (ChangePassword forced). -->
<script module>
  import { writable } from 'svelte/store';
  export const account = writable(null);   // null | 'password' | 'email'
  export function openAccount(kind) { account.set(kind); }
</script>

<script>
  import { t } from '../i18n.js';
  import Dialog from './Dialog.svelte';
  import ChangePassword from '../pages/ChangePassword.svelte';
  import AccountEmail from '../pages/AccountEmail.svelte';
  let { onme = null, returnFocus = null } = $props();

  const close = () => account.set(null);
  let pwOpen = $state(false), emOpen = $state(false);
  $effect(() => { pwOpen = $account === 'password'; emOpen = $account === 'email'; });
</script>

<Dialog bind:open={pwOpen} title={$t('pw.title')} onclose={close} {returnFocus}>
  {#if pwOpen}<ChangePassword embedded ondone={close} oncancel={close} />{/if}
</Dialog>
<Dialog bind:open={emOpen} title={$t('em.title')} onclose={close} {returnFocus}>
  {#if emOpen}<AccountEmail embedded ondone={() => { onme?.(); close(); }} />{/if}
</Dialog>
