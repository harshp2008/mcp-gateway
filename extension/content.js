// Auto-click Gemini's tool-permission card ("Allow" / "Allow once") for your mcp-gateway connectors.
// ALLOW = connector-name prefixes to auto-allow. Default "mcp " = every connector named mcp-*
// (mcp-main-laptop, mcp-old-laptop, ...). Narrow it with: mcp-gateway extension --only mcp-main-laptop
// Handles both card layouts (Allow once / Always allow / Don't allow  and  Deny / Allow), buttons,
// role=button elements and open shadow DOMs. The connector is read from: Let Gemini use "<tool>" from <connector>
(() => {
  const norm = s => (s || "").toLowerCase().replace(/[-_\s]+/g, " ").trim();
  const ALLOW = ["mcp "]; // @ALLOW@
  const BTN = new Set(["allow once", "allow"]); // never "always allow", "deny", "don't allow"
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
  const allowed = name => { const n = norm(name); return ALLOW.some(p => n.startsWith(p)); };
  // connector name from the card sentence; falls back to the text before it
  const connectorOf = t => {
    const m = t.match(/Let Gemini use\s+["“][^"”]*["”]\s+from\s+(\S+)/i);
    if (m) return m[1];
    const i = t.indexOf("Let Gemini use");
    return i > 0 ? t.slice(0, i) : "";
  };

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
      const label = (el.textContent || "").trim().toLowerCase();
      if (!BTN.has(label)) continue;
      if (el.children.length > 1) continue;
      const btn = clickable(el);
      if (handled.has(btn)) continue;
      // climb to the smallest ancestor holding the card sentence; cap keeps us out of the whole chat
      let card = parentOf(btn), found = false, name = "", text = "";
      for (let i = 0; i < 20 && card; i++, card = parentOf(card)) {
        const t = card.textContent || "";
        if (t.length > 6000) break;
        if (t.includes("Let Gemini use")) { found = true; text = t; name = connectorOf(t); break; }
      }
      handled.add(btn);
      if (!found) { log('saw "' + label + '" but no "Let Gemini use" ancestor'); continue; }
      if (allowed(name)) {
        log("card for", name, "->", btn.tagName, '"' + label + '"');
        setTimeout(() => tryClick(btn), 200);
      } else {
        log("connector not in ALLOW, ignoring:", JSON.stringify(name), "card:", JSON.stringify(norm(text).slice(0, 120)));
      }
    }
  }
  let timer = null;
  new MutationObserver(() => { clearTimeout(timer); timer = setTimeout(scan, 150); })
    .observe(document.documentElement, { childList: true, subtree: true });
  scan();
  log("active; auto-allowing connectors starting with:", ALLOW.join(" | "));
})();
