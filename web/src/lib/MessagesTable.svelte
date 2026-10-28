<!-- Grouped error/warning messages table (DRD §4.3, inv. §2.10 no. 19 and §2.1): Level, Message (click -> original log
     line, UTC time, with a copy button), Count; the filter searches all messages on the server. crossService: Service
     column for Overview ("Top pesan error lintas layanan", top 25). -->
<script>
  import { t } from '../i18n.js';
  import { sysName } from '../format.js';
  import DataTable from './DataTable.svelte';
  let { title, folder, service = null, initial = null, crossService = false, chip = null, limit = null } = $props();

  // msg_key has the form "LEVEL | message" (same as the old key); the Message column shows the part after the level
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
