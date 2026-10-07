<!-- Kelola folder log (permintaan pemilik 2026-10-07; admin, halaman Ingest & impor). GET /api/admin/folders: folder di
     dashboard, di disk, dan yang diabaikan. "Hapus" -> dialog konfirmasi -> POST /api/admin/folders/{f}/delete:
     data folder dihapus dari dashboard; file di kotak masuk (hasil impor S3) ikut dihapus bila dicentang; file di folder
     log utama TIDAK pernah dihapus (hanya dibaca) — folder itu ditandai "diabaikan" agar sinkronisasi tidak
     memasukkannya lagi. "Pulihkan" -> POST …/restore, lalu sinkronisasi memasukkannya kembali. -->
<script>
  import { onMount } from 'svelte';
  import { lang, t } from '../i18n.js';
  import { api } from '../api.js';
  import { num, dLabel, tWIB, utcToWib } from '../format.js';
  import { toast } from './Toast.svelte';
  import DataTable from './DataTable.svelte';
  import Dialog from './Dialog.svelte';
  import SeverityTag from './SeverityTag.svelte';

  let { onchanged = null } = $props();
  let rows = $state.raw(null), target = $state(null), open = $state(false), delInbox = $state(true), busy = $state(false);

  async function load() { try { rows = (await api.get('/api/admin/folders')).rows; } catch (e) { toast(e.message); } }
  onMount(load);

  function ask(r) { target = r; delInbox = true; open = true; }
  async function del() {
    busy = true;
    try {
      const r = await api.post(`/api/admin/folders/${target.folder}/delete`, { delete_inbox: delInbox });
      toast($t(r.ignored ? 'fm.done_ignored' : 'fm.done', { date: dLabel(target.folder, $lang) }));
      open = false; await load(); onchanged?.();
    } catch (e) { toast(e.status === 409 ? $t('fm.busy') : e.message); }
    finally { busy = false; }
  }
  async function restore(r) {
    try { await api.post(`/api/admin/folders/${r.folder}/restore`, {}); toast($t('fm.restored', { date: dLabel(r.folder, $lang) })); await load(); onchanged?.(); }
    catch (e) { toast(e.message); }
  }
</script>

{#if rows}
  <DataTable title={$t('fm.title')} {rows} limit={30} columns={[
    { key: 'folder', label: $t('ipp.col.folder'), fmt: (r) => dLabel(r.folder, $lang), cls: () => 'nowrap', sort: true },
    { key: 'files', label: $t('kpi.files'), type: 'num', sort: true },
    { key: 'lines', label: $t('col.lines'), type: 'num', sort: true },
    { key: 'where', label: $t('fm.col.where'), custom: true, minw: 200 },
    { key: 'act', label: $t('fm.col.action'), custom: true },
  ]}>
    {#snippet cell(r, c)}
      {#if c.key === 'where'}
        <div class="tags">
          {#if r.ignored}<SeverityTag level={2} text={$t('fm.tag.ignored')} />{:else if !r.in_db}<SeverityTag level={1} text={$t('fm.tag.new')} />{/if}
          {#if r.log}<SeverityTag level="ok" text={$t('fm.tag.log')} />{/if}
          {#if r.inbox}<SeverityTag level="ok" text={$t('fm.tag.inbox')} />{/if}
        </div>
        {#if r.ignored && r.ignored_by}<div class="muted small">{$t('fm.ignored_by', { user: r.ignored_by, time: r.ignored_at ? tWIB(utcToWib(r.ignored_at), $lang) : '' })}</div>{/if}
      {:else if r.ignored}
        <button class="btn sm" onclick={() => restore(r)}>{$t('fm.restore')}</button>
      {:else if r.in_db || r.inbox}
        <button class="btn sm danger" onclick={() => ask(r)} aria-label={$t('fm.delete_aria', { date: dLabel(r.folder, $lang) })}>{$t('fm.delete')}</button>
      {/if}
    {/snippet}
  </DataTable>
{/if}

<Dialog bind:open title={target ? $t('fm.confirm_title', { date: dLabel(target.folder, $lang) }) : ''}>
  {#if target}
    <p>{$t('fm.confirm_text', { files: num(target.files, $lang), lines: num(target.lines, $lang) })}</p>
    {#if target.inbox}
      <label class="chk"><input type="checkbox" bind:checked={delInbox} /> {$t('fm.del_inbox')}</label>
    {/if}
    {#if target.log}<p class="muted small">{$t('fm.log_note')}</p>{/if}
  {/if}
  {#snippet footer()}
    <button class="btn" onclick={() => (open = false)}>{$t('action.cancel')}</button>
    <button class="btn danger primary" onclick={del} disabled={busy}>{$t('fm.delete')}</button>
  {/snippet}
</Dialog>

<style>
  .tags { display: flex; flex-wrap: wrap; gap: 4px; }
  .small { font-size: 0.75rem; }
  .chk { display: flex; align-items: center; gap: 8px; margin: 10px 0; font-size: 0.875rem; }
  .chk input { width: auto; min-height: 0; }
  .btn.sm { min-height: 32px; padding: 0.3rem 0.8rem; font-size: 0.8125rem; }
  .btn.danger { color: var(--err); border-color: color-mix(in srgb, var(--err) 45%, transparent); }
  .btn.danger.primary { background: var(--err); color: #fff; border-color: var(--err); }
</style>
