// "Not compared" note, shown once per page instead of under every KPI (redesign 2026-10-27).
// Each KPI whose change could not be computed (format.js delta kind 'incomplete') registers its text here while it is on
// screen; App.svelte (or the Overview status card) shows the first one.
import { writable } from 'svelte/store';

export const cmpNote = writable(new Map());
let next = 0;

/** Register `text` for as long as the caller keeps it; returns the function that removes it. */
export function holdNote(text) {
  const id = ++next;
  cmpNote.update((m) => new Map(m).set(id, text));
  return () => cmpNote.update((m) => { const n = new Map(m); n.delete(id); return n; });
}
