#!/usr/bin/env bash
# Installs the MCP gateway for the current user (no root needed).
#   ./install.sh [--name NAME] [--yes] [--no-desktop] [--no-funnel] [--no-open-terminal] [--no-backends]
# NAME defaults to this PC's hostname.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOME_DIR="${MCPGW_HOME:-$HOME/.mcp-gateway}"
UPSTREAM=https://github.com/hoophq/mcpproxy
UPSTREAM_COMMIT=5566d29d02165158a57164ff8c3c23dd895355cc
DCG_VERSION=v0.17.0
NAME=""; URL=""; BACKENDS=1; YES=0; DESKTOP=1; FUNNEL=1; OPENTERM=1
while [ $# -gt 0 ]; do
  case "$1" in
    --name) NAME="$2"; shift 2;;
    --url) URL="$2"; shift 2;;
    --no-backends) BACKENDS=0; shift;;
    --yes|-y) YES=1; shift;;
    --no-desktop) DESKTOP=0; shift;;
    --no-funnel) FUNNEL=0; shift;;
    --no-open-terminal) OPENTERM=0; shift;;
    -h|--help) sed -n 2,4p "$0"; exit 0;;
    *) echo "unknown option $1"; exit 1;;
  esac
done

say() { printf '\n==> %s\n' "$*"; }
need() { command -v "$1" >/dev/null 2>&1 || { echo "missing required tool: $1"; exit 1; }; }
for t in git python3 curl tar systemctl; do need "$t"; done
command -v zenity >/dev/null || echo "WARNING: zenity not found - approval popups need it (sudo apt install zenity)"

case "$(uname -m)" in
  x86_64) GOARCH=amd64; DCG_TARGET=x86_64-unknown-linux-musl;;
  aarch64|arm64) GOARCH=arm64; DCG_TARGET=aarch64-unknown-linux-gnu;;
  *) echo "unsupported CPU $(uname -m)"; exit 1;;
esac
mkdir -p "$HOME_DIR/bin" "$HOME_DIR/app" "$HOME/.local/bin" "$HOME/.config/systemd/user"
chmod 700 "$HOME_DIR"

# ---- Go toolchain (upstream needs a recent one; fetch a private copy if needed) ----
say "Go toolchain"
want=1.26.2
have=$(go env GOVERSION 2>/dev/null | sed 's/^go//' || true)
ver_ge() { [ "$(printf '%s\n%s\n' "$2" "$1" | sort -V | head -1)" = "$2" ]; }
if [ -n "$have" ] && ver_ge "$have" "$want" && GO=$(command -v go); then
  echo "using system go $have"
else
  if [ ! -x "$HOME_DIR/go/bin/go" ]; then
    f=$(curl -fsSL 'https://go.dev/dl/?mode=json' | python3 -c "
import json,sys
for r in json.load(sys.stdin):
    for f in r['files']:
        if f['os']=='linux' and f['arch']=='$GOARCH' and f['kind']=='archive':
            print(f['filename'], f['sha256']); sys.exit()")
    fn=${f% *}; sum=${f#* }
    curl -fsSL "https://go.dev/dl/$fn" -o "/tmp/$fn"
    echo "$sum  /tmp/$fn" | sha256sum -c -
    tar -C "$HOME_DIR" -xzf "/tmp/$fn"; rm -f "/tmp/$fn"
  fi
  GO="$HOME_DIR/go/bin/go"
fi

# ---- build patched mcpproxy ----
say "Building patched mcpproxy"
SRC="$HOME_DIR/src"
[ -d "$SRC/.git" ] || git clone "$UPSTREAM" "$SRC"
git -C "$SRC" fetch -q origin 2>/dev/null || true
git -C "$SRC" checkout -q -f "$UPSTREAM_COMMIT"
git -C "$SRC" clean -fdq
git -C "$SRC" apply --whitespace=nowarn "$REPO_DIR/patches/mcpproxy.patch"
( cd "$SRC" && "$GO" build -o "$HOME_DIR/bin/mcpproxyd.new" ./cmd/mcpproxyd )
mv -f "$HOME_DIR/bin/mcpproxyd.new" "$HOME_DIR/bin/mcpproxyd"

# ---- dcg (command guard): download + verify checksum, never run its own installer ----
say "Destructive Command Guard $DCG_VERSION"
if [ ! -x "$HOME_DIR/bin/dcg" ]; then
  t=$(mktemp -d); b="https://github.com/Dicklesworthstone/destructive_command_guard/releases/download/$DCG_VERSION"
  curl -fsSL "$b/dcg-$DCG_TARGET.tar.xz" -o "$t/dcg.tar.xz"
  curl -fsSL "$b/dcg-$DCG_TARGET.tar.xz.sha256" -o "$t/dcg.sha256"
  [ "$(sha256sum "$t/dcg.tar.xz" | cut -d' ' -f1)" = "$(cut -d' ' -f1 "$t/dcg.sha256")" ] || { echo "dcg checksum mismatch"; exit 1; }
  tar -C "$t" -xJf "$t/dcg.tar.xz"
  install -m 755 "$(find "$t" -type f -name dcg | head -1)" "$HOME_DIR/bin/dcg"; rm -rf "$t"
fi

# ---- app files + CLI ----
say "Installing CLI and approval popup"
install -m 755 "$REPO_DIR/bin/mcp-gateway" "$HOME_DIR/bin/mcp-gateway"
install -m 644 "$REPO_DIR/gateway/approver.py" "$HOME_DIR/approver.py"
mkdir -p "$HOME_DIR/app/tests" "$HOME_DIR/app/extension"
cp -r "$REPO_DIR/tests/." "$HOME_DIR/app/tests/"
cp -r "$REPO_DIR/extension/." "$HOME_DIR/app/extension/"
ln -sf "$HOME_DIR/bin/mcp-gateway" "$HOME/.local/bin/mcp-gateway"
case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *) echo "NOTE: add ~/.local/bin to PATH";; esac

# ---- systemd user services ----
sed "s|@HOME@|$HOME_DIR|g" "$REPO_DIR/templates/mcp-gateway.service" > "$HOME/.config/systemd/user/mcp-gateway.service"
sed "s|@HOME@|$HOME_DIR|g" "$REPO_DIR/templates/mcp-gateway-approver.service" > "$HOME/.config/systemd/user/mcp-gateway-approver.service"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
loginctl enable-linger "$USER" 2>/dev/null || true

# ---- settings: name (default hostname), url, backends ----
say "Configuring"
CLI="$HOME_DIR/bin/mcp-gateway"
export MCPGW_HOME="$HOME_DIR"
[ -f "$HOME_DIR/settings.json" ] || echo '{"name":"","public_url":"","backends":{},"clients":[]}' > "$HOME_DIR/settings.json"
python3 - "$HOME_DIR/settings.json" "$NAME" "$URL" <<'PY'
import json,sys
p,n,u=sys.argv[1:]
s=json.load(open(p))
if n: s["name"]=n
if u: s["public_url"]=u.rstrip("/")
json.dump(s,open(p,"w"),indent=2)
PY
# open-terminal = the shell/files MCP server. It needs the [mcp] extra, or `open-terminal mcp` exits 1.
ot_ok() { command -v open-terminal >/dev/null 2>&1 && OPEN_TERMINAL_API_KEY=probe timeout 8 open-terminal mcp --cwd / </dev/null >/dev/null 2>&1; }
if [ "$BACKENDS" = 1 ] && [ "$OPENTERM" = 1 ] && ! ot_ok; then
  say "Installing open-terminal[mcp]"
  if command -v uv >/dev/null 2>&1; then uv tool install --force 'open-terminal[mcp]'
  elif command -v pipx >/dev/null 2>&1; then pipx install --force 'open-terminal[mcp]'
  else python3 -m pip install --user --break-system-packages 'open-terminal[mcp]'; fi || echo "open-terminal install failed; install 'open-terminal[mcp]' manually, then: mcp-gateway backend add terminal"
  export PATH="$HOME/.local/bin:$PATH"
  ot_ok || echo "WARNING: 'open-terminal mcp' still fails to start; the terminal backend will break the gateway. Run it by hand to see why."
fi
if [ "$BACKENDS" = 1 ]; then
  command -v open-terminal >/dev/null && "$CLI" backend add terminal >/dev/null && echo "backend: terminal (open-terminal found)" || echo "skip terminal (open-terminal not installed: pip install open-terminal)"
  command -v figcraft-cli >/dev/null && "$CLI" backend add figcraft >/dev/null && echo "backend: figcraft" || true
fi
"$CLI" render >/dev/null
"$CLI" extension >/dev/null
systemctl --user daemon-reload
systemctl --user enable --now mcp-gateway.service
systemctl --user enable --now mcp-gateway-approver.service 2>/dev/null || echo "(approver starts with your desktop session)"

ask() { # ask "question" -> 0 for yes
  [ "$YES" = 1 ] && return 0
  [ -r /dev/tty ] || return 1
  printf '%s [y/N] ' "$1" > /dev/tty; read -r a < /dev/tty; case "$a" in y|Y|yes) return 0;; *) return 1;; esac
}
YF=""; [ "$YES" = 1 ] && YF="--yes"

if [ "$DESKTOP" = 1 ]; then
  say "Claude Desktop"
  "$CLI" desktop $YF || echo "(skipped; run later: mcp-gateway desktop)"
fi

if [ "$FUNNEL" = 1 ]; then
  say "Public access (Tailscale Funnel) - needed for Gemini/web apps, not for Claude Desktop/Code"
  if command -v tailscale >/dev/null 2>&1; then
    if ask "Expose this PC through Tailscale Funnel now?"; then "$CLI" funnel || echo "(fix the message above, then run: mcp-gateway funnel)"; fi
  else
    echo "Tailscale not installed. Later: curl -fsSL https://tailscale.com/install.sh | sh && sudo tailscale up && mcp-gateway funnel"
  fi
fi

say "Done"
"$CLI" status || true
cat <<EOF

Next:
  mcp-gateway extension          # Chrome extension that auto-clicks Gemini's Allow card (steps printed)
  mcp-gateway connect            # copy-paste setup for Claude Desktop / Claude Code / Gemini
  mcp-gateway name my-laptop     # rename this PC (default is hostname)
  mcp-gateway backend add NAME -- <command> <args>   # add any other MCP server
EOF
