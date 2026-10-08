<!-- One-time code field (owner request 2026-10-08): six boxes, one digit each. It is ONE real input lying over the boxes,
     so typing, pasting a whole code, the phone's "code from Messages/Mail" suggestion (autocomplete="one-time-code")
     and screen readers all work as with a normal field; the boxes only draw the digits. oncomplete runs at 6 digits.
     Use it for EVERY one-time code field, so they all look alike: boxes centred, filling the width up to ~400 px. -->
<script>
  let { id, value = $bindable(''), length = 6, invalid = false, describedby = undefined, oncomplete = null, ref = $bindable() } = $props();
  let focused = $state(false);
  const cells = $derived(Array.from({ length }, (_, i) => value[i] || ''));
  const active = $derived(Math.min(value.length, length - 1));

  function input(e) {
    const v = e.currentTarget.value.replace(/\D/g, '').slice(0, length);
    e.currentTarget.value = value = v;
    if (v.length === length) oncomplete?.(v);
  }
  // the caret always sits at the end: the boxes are filled left to right
  const toEnd = (e) => { const el = e.currentTarget; requestAnimationFrame(() => el.setSelectionRange(el.value.length, el.value.length)); };
</script>

<div class="otp" class:focused class:invalid style="--n: {length}">
  <input {id} bind:this={ref} class="real" type="text" inputmode="numeric" pattern="[0-9]*" autocomplete="one-time-code"
    maxlength={length} {value} oninput={input} onfocus={(e) => { focused = true; toEnd(e); }} onblur={() => (focused = false)}
    onclick={toEnd} onkeyup={toEnd} aria-invalid={invalid || undefined} aria-describedby={describedby} spellcheck="false" />
  <div class="cells" aria-hidden="true">
    {#each cells as c, i}
      <span class="cell" class:filled={c} class:active={focused && i === active}>{c}{#if focused && i === active && !c}<i class="caret"></i>{/if}</span>
    {/each}
  </div>
</div>

<style>
  /* same look everywhere (owner, 2026-10-08): the boxes fill the width up to ~400 px and sit in the middle */
  .otp { position: relative; width: 100%; max-width: calc(var(--n) * 68px); margin-inline: auto; }
  .cells { display: grid; grid-template-columns: repeat(var(--n), 1fr); gap: 8px; pointer-events: none; }
  .cell {
    height: 56px; display: grid; place-items: center; border: 1px solid var(--line-strong); border-radius: 12px;
    background: var(--bg); color: var(--heading); font-weight: 600; font-size: 1.5rem; line-height: 1;
    font-variant-numeric: tabular-nums; transition: border-color 0.12s, box-shadow 0.12s;
  }
  .cell.filled { border-color: color-mix(in srgb, var(--accent) 45%, var(--line-strong)); }
  .cell.active { border-color: var(--accent); box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 22%, transparent); }
  .invalid .cell { border-color: var(--err); }
  .invalid .cell.active { box-shadow: 0 0 0 3px color-mix(in srgb, var(--err) 22%, transparent); }
  .caret { width: 2px; height: 26px; background: var(--accent); animation: blink 1s steps(1) infinite; }
  @keyframes blink { 50% { opacity: 0; } }
  @media (prefers-reduced-motion: reduce) { .caret { animation: none; } }
  /* the real field covers the boxes: invisible text, but it takes the clicks, the keyboard and the paste */
  .real {
    position: absolute; inset: 0; width: 100%; height: 100%; opacity: 0.01; border: 0; padding: 0; margin: 0;
    color: transparent; caret-color: transparent; background: transparent; font-size: 16px; letter-spacing: 0; z-index: 1;
  }
  .real::selection { background: transparent; }
  @media (max-width: 400px) { .cells { gap: 6px; } .cell { height: 50px; font-size: 1.3rem; } }
</style>
