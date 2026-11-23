// Auto-click Gemini's tool-permission card ("Allow" / "Allow once") for your mcp-gateway connectors.
// ALLOW = connector-name prefixes to auto-allow. Default "mcp " = every connector named mcp-*
// (mcp-main-laptop, mcp-old-laptop, ...). Narrow it with: mcp-gateway extension --only mcp-main-laptop
// Handles every card layout Gemini has used:
//   - Deny / Allow, with "Let Gemini use "<tool>" from <connector>"
//   - Don't allow / Allow once / Always allow, with the connector name as a header above "Let Gemini use <tool>?"
// Buttons, role=button elements and open shadow DOMs all work. A card whose connector can't be identified is ignored.
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
  // connector name: "...from <name>" if present, else the header text right before "Let Gemini use"
  const connectorOf = t => {
    const m = t.match(/Let Gemini use\s+["“][^"”]*["”]\s+from\s+(\S+)/i);
    if (m) return m[1];
    const i = t.indexOf("Let Gemini use");
    return i > 0 ? t.slice(0, i).trim() : "";
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
      // climb until an ancestor holds the card sentence AND names the connector; the cap keeps us out of the whole chat
      let card = parentOf(btn), found = false, name = "", text = "";
      for (let i = 0; i < 25 && card; i++, card = parentOf(card)) {
        const t = card.textContent || "";
        if (t.length > 6000) break;
        if (!t.includes("Let Gemini use")) continue;
        found = true; text = t; name = connectorOf(t);
        if (name) break; // header not inside this ancestor yet: keep climbing
      }
      handled.add(btn);
      if (!found) { log('saw "' + label + '" but no "Let Gemini use" ancestor'); continue; }
      if (name && allowed(name)) {
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
