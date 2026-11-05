// Giving focus back after a dialog or menu closes (owner report 2026-11-05: a thick ring stayed on the header button after a
// mouse click). Browsers show :focus-visible for a focus() call from script when the previous focus was in a text field, so the
// ring appeared after closing a dialog with the mouse. The ring is meant for the keyboard: restoreFocus() asks for it only when the
// last thing the user did was a key press. Chromium has no `focusVisible: false` option yet, so the element is also marked
// `data-quiet` (theme.css hides its ring) until it loses focus or a key is pressed.
let byKey = true;
if (typeof window !== 'undefined') {
  window.addEventListener('keydown', () => { byKey = true; }, true);
  window.addEventListener('pointerdown', () => { byKey = false; }, true);
}

/** True when the last user action was a key press (so a ring on the element that gets the focus is wanted). */
export const lastWasKey = () => byKey;

/** focus() without a ring; the ring comes back with the next key press or a new focus. */
export function focusQuiet(el) {
  if (!el?.focus) return;
  el.setAttribute('data-quiet', '');
  const off = () => { el.removeAttribute('data-quiet'); el.removeEventListener('blur', off); document.removeEventListener('keydown', off, true); };
  el.addEventListener('blur', off);
  document.addEventListener('keydown', off, true);
  el.focus({ focusVisible: false });   // browsers that do not know the option ignore it
}

/** Give the focus back to `el` after a dialog or menu closed: with a ring after the keyboard, without one after the mouse or touch. */
export function restoreFocus(el) {
  if (!el?.focus) return;
  if (byKey) el.focus(); else focusQuiet(el);
}
