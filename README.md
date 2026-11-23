# mcp-gateway

One OAuth-protected MCP endpoint on your PC that fronts all your MCP servers (terminal, Figma, WhatsApp, anything) for **Claude Desktop, Claude Code, Gemini web, agy, or any MCP client**.

- **Nothing gets in without a click on the PC.** Every new client (OAuth or token) triggers a popup on the machine. No click, no access. Click "Approve & trust" once and that client is trusted until you revoke it.
- **Command filter.** Terminal commands pass through [dcg](https://github.com/Dicklesworthstone/destructive_command_guard) (blocks `rm -rf /`-class stuff); everything else flows.
- **Multi-PC friendly.** Each PC has a name (default: hostname). The server is called `mcp-<name>` and every tool description says which PC it runs on, so agents don't mix laptops up.
- Built on [hoophq/mcpproxy](https://github.com/hoophq/mcpproxy) (MIT) + a patch set in `patches/`.

## Install

```bash
git clone https://github.com/harshp2008/mcp-gateway && cd mcp-gateway
./install.sh                      # name = this PC's hostname
./install.sh --name main-laptop   # or pick one
```

Needs: `git python3 curl tar systemd(--user)`, `zenity` for popups. Go is downloaded privately if missing. No root. Installs to `~/.mcp-gateway`, runs as two user services (`mcp-gateway`, `mcp-gateway-approver`), CLI at `~/.local/bin/mcp-gateway`.

It auto-adds backends it finds (`open-terminal`, `figcraft-cli`). Add anything else:

```bash
mcp-gateway backend add whatsapp -- uv --directory ~/whatsapp-mcp/whatsapp-mcp-server run main.py
mcp-gateway backend list
```

## CLI

| command | what |
|---|---|
| `mcp-gateway name [NAME]` | show / set this PC's name |
| `mcp-gateway url [URL]` | set public HTTPS URL (needed for web apps) |
| `mcp-gateway backend add\|list\|remove` | manage MCP servers behind the gateway |
| `mcp-gateway client add NAME` | static token for scripts / Claude Code |
| `mcp-gateway trust list\|revoke SUBJECT\|add SUBJECT [DAYS]` | who is trusted |
| `mcp-gateway connect [claude-desktop\|claude-code\|gemini\|other]` | copy-paste linking steps with your name/URL filled in |
| `mcp-gateway status \| restart \| logs` | ops |

## Link it to your apps

### Claude Desktop
```bash
mcp-gateway client add claude-desktop      # prints a token
```
Add to `claude_desktop_config.json` → `mcpServers` (key = `mcp-<name>`):
```json
"mcp-main-laptop": {
  "command": "npx",
  "args": ["-y", "mcp-remote", "http://127.0.0.1:8765/mcp", "--header", "Authorization: Bearer ${GW_AUTH}"],
  "env": { "GW_AUTH": "<token>" }
}
```
Restart Claude Desktop. First use → popup on the PC → "Trust this client".
If you previously added the same MCP servers directly, remove them to avoid duplicates.

### Claude Code
```bash
mcp-gateway client add claude-code
claude mcp add --transport http mcp-main-laptop http://127.0.0.1:8765/mcp --header "Authorization: Bearer <token>"
```

### Gemini web (or any web app / phone)
Web apps need a public HTTPS URL. With Tailscale Funnel (only expose the MCP paths, on a non-443 port so you don't expose other things):
```bash
for p in /mcp /token /register /authorize /.well-known; do
  tailscale funnel --bg --https=10000 --set-path=$p http://127.0.0.1:8765$p
done
mcp-gateway url https://<machine>.<tailnet>.ts.net:10000
```
Gemini → Settings → connectors → add custom MCP connector: name `mcp-main-laptop`, URL `https://<machine>.<tailnet>.ts.net:10000/mcp`, auth OAuth. A popup appears **on the PC**: "Approve & trust". In chats, @mention the connector.

#### Optional: stop Gemini's per-call "Allow" cards
Gemini asks permission on every tool call and that can't be disabled server-side. The repo ships a small Chrome extension (`extension/`) that clicks **Allow once** for every connector named `mcp-*`, so one install in your browser covers all your PCs (`mcp-main-laptop`, `mcp-old-laptop`, ...):
```bash
mcp-gateway extension                       # writes ~/.mcp-gateway/extension and prints the steps
mcp-gateway extension --only mcp-main-laptop   # restrict to specific connectors
```
Chrome -> `chrome://extensions` -> Developer mode -> **Load unpacked** -> pick the folder -> reload Gemini. On a machine without a gateway, just clone this repo and load its `extension/` folder. Dangerous shell commands are still blocked by dcg on each gateway.

### Two (or more) PCs
Run `./install.sh --name old-laptop` on each, give each its own Funnel URL, add one connector per PC (`@mcp-main-laptop`, `@mcp-old-laptop`). Connectors live in your Google account, so any browser/laptop signed into Gemini can drive any of your PCs - nothing needs installing on the PC you're typing from. The name appears in the server name and in tool instructions ("you are running on OLD-LAPTOP").

### Revoke
```bash
mcp-gateway trust list
mcp-gateway trust revoke oauth:<client_id>     # or client:<name>
```

## Security notes
- Trusted client ⇒ full access to every backend (incl. the terminal). The popup is the gate; only approve what *you* just started. Keep the Funnel path-restricted.
- WhatsApp backend sends are not filtered by dcg.
- Secrets live in `~/.mcp-gateway/gateway.env` (mode 600). Never commit it (see `.gitignore`).
- The gateway is a patched build of mcpproxy v0.2.0 (`5566d29`); see `patches/mcpproxy.patch`.

## Tests
`tests/oauth-test.py` exercises the OAuth + consent flow against a running gateway.
