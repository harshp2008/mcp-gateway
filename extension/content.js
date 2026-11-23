// Auto-click Gemini's permission card ("Allow once") for your mcp-gateway connectors.
// ALLOW = connector-name prefixes to auto-allow. Default "mcp " = every connector named mcp-*
// (mcp-main-laptop, mcp-old-laptop, ...). Narrow it with: mcp-gateway extension --only mcp-main-laptop
// Works with plain buttons, role=button elements and open shadow DOMs.
(() => {
  const norm = s => (s || "").toLowerCase().replace(/[-_\s]+/g, " ").trim();
  const ALLOW = ["mcp "]; // @ALLOW@
  const handled = new WeakSet();
  const log = (...a) => console.log("[gw-autoallow]", ...a);

  function* deepAll(root) {
    for (const el of root.querySelectorAll("*")) {
      yield el;
      if (el.shadowRoot) yield* deepAll(el.shadowRoot);
    }
  }
  const parentOf = el => el.parentElement || (el.getRootNode && el.getRootNode().host) || null;
  const clickable = el => el.closest("button,[role=button],a") || el;
  // the card text starts with the connector name: "Mcp Main Laptop" + "Let Gemini use ..."
  const allowed = t => { const n = norm(t); return ALLOW.some(p => n.startsWith(p)); };

  function tryClick(el, n = 0) {
    const off = el.disabled || el.getAttribute("aria-disabled") === "true";
    if (off) { if (n < 40) setTimeout(() => tryClick(el, n + 1), 250); return; }
    for (const type of ["pointerdown", "mousedown", "pointerup", "mouseup", "click"]) {
      el.dispatchEvent(new MouseEvent(type, { bubbles: true, cancelable: true, composed: true, view: window }));
    }
    log("clicked", (el.textContent || "").trim());
  }

  function scan() {
    for (const el of deepAll(document)) {
      if ((el.textContent || "").trim().toLowerCase() !== "allow once") continue;
      if (el.children.length > 1) continue;
      const btn = clickable(el);
      if (handled.has(btn)) continue;
      // climb to the card: contains "Let Gemini use", starts with an allowed connector
      // name, and stays small (< 600 chars) so we never match the whole chat.
      let card = parentOf(btn), found = false, ok = false;
      for (let i = 0; i < 20 && card; i++, card = parentOf(card)) {
        const t = card.textContent || "";
        if (t.length > 600) break;
        if (t.includes("Let Gemini use")) {
          found = true;
          if (allowed(t)) { ok = true; break; }
        }
      }
      if (ok) {
        handled.add(btn);
        log("card for", norm(card.textContent).slice(0, 40), "->", btn.tagName);
        setTimeout(() => tryClick(btn), 200);
        continue;
      }
      handled.add(btn);
      log(found ? "card is for a connector not in ALLOW, ignoring" : 'saw "Allow once" but no "Let Gemini use" ancestor');
    }
  }
  let timer = null;
  new MutationObserver(() => { clearTimeout(timer); timer = setTimeout(scan, 150); })
    .observe(document.documentElement, { childList: true, subtree: true });
  scan();
  log("active; auto-allowing connectors starting with:", ALLOW.join(" | "));
})();
