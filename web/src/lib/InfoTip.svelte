<!-- "(i)" tooltip (DRD §4.1 U8): appears on hover AND focus, closed by Esc, does not disappear when the pointer moves onto
     it (§9.5). -->
<script>
  import { t } from '../i18n.js';
  let { text } = $props();
  let open = $state(false);
  const id = 'tip-' + Math.random().toString(36).slice(2, 9);
</script>

<span class="tip" role="presentation" onmouseenter={() => (open = true)} onmouseleave={() => (open = false)}>
  <button type="button" class="i" aria-describedby={id} aria-label={$t('ui.info')} aria-expanded={open}
    onfocus={() => (open = true)} onblur={() => (open = false)} onclick={() => (open = !open)}
    onkeydown={(e) => e.key === 'Escape' && (open = false)}><span class="c" aria-hidden="true">i</span></button>
  <span {id} role="tooltip" class="box" class:open>{text}</span>
</span>

<style>
  .tip { position: relative; display: inline-flex; vertical-align: middle; margin-left: 4px; }
  .i { width: 18px; height: 18px; border: 0; background: transparent; padding: 0; cursor: help; display: grid; place-items: center; border-radius: 50%; }
  .c {
    width: 18px; height: 18px; border-radius: 50%; border: 1px solid var(--line-strong); display: grid; place-items: center;
    color: var(--muted); font-size: 0.6875rem; font-weight: 700; font-style: italic; line-height: 1;
  }
  /* touch screens: 44 px tap area (DRD §8.2) without changing the layout; the circle stays 18 px */
  @media (max-width: 900px) { .i { width: 44px; height: 44px; margin: -13px; } }
  .box {
    position: absolute; left: 50%; top: calc(100% + 6px); transform: translateX(-50%); z-index: 30;
    width: max-content; max-width: min(280px, 80vw); padding: 8px 10px; border-radius: 10px;
    background: var(--tooltip-bg); border: 1px solid var(--tooltip-line); color: #e2ecf3;
    font-size: 0.75rem; font-weight: 400; line-height: 1.4; text-transform: none; display: none;
  }
  .box.open { display: block; }
</style>
