<!-- Tabel pesan error/warning terkelompok (DRD §4.3, inv. §2.10 no. 19 dan §2.1): Level, Pesan (klik -> baris log
     asli, waktu UTC, dengan tombol salin), Jumlah; filter mencari seluruh pesan di server. crossService: kolom
     Layanan untuk Overview ("Top pesan error lintas layanan", 25 teratas). -->
<script>
  import { t } from '../i18n.js';
  import { sysName } from '../format.js';
  import DataTable from './DataTable.svelte';
  let { title, folder, service = null, initial = null, crossService = false, chip = null, limit = null } = $props();

  // msg_key berbentuk "LEVEL | pesan" (sama dengan kunci lama); kolom Pesan menampilkan bagian sesudah level
  const text = (r) => (r.msg_key.startsWith(r.level + ' | ') ? r.msg_key.slice(r.level.length + 3) : r.msg_key);
  const columns = $derived([
    ...(crossService ? [{ key: 'service', label: $t('col.service'), fmt: (r) => sysName(r.service), cls: () => 'nowrap', sort: true }] : []),
    { key: 'level', label: $t('col.level'), cls: (r) => r.level, sort: true },
    { key: 'msg_key', label: $t('col.message'), fmt: text, detail: (r) => r.sample },
    { key: 'n', label: $t('table.count'), type: 'num', sort: true },
  ]);
  const hasExc = $derived(!!initial?.rows?.some((r) => r.level === 'EXC'));
</script>

<DataTable {title} {folder} table="messages" params={service ? { service } : {}} {initial} {columns} {chip} {limit}
  bar={crossService ? 'n' : null} maxHeight={crossService ? 440 : 600} />
{#if hasExc}<p class="muted note">{$t('msg.exc_note')}</p>{/if}

<style>
  .note { grid-column: 1 / -1; margin: -10px 4px 0; font-size: 0.75rem; }
</style>
