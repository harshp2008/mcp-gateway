#!/usr/bin/env python3
"""Fix for open-terminal's `mcp` command with recent fastmcp.

Upstream open_terminal/cli.py calls mcp_server.run(transport=..., host=..., port=...) even for the
stdio transport; fastmcp 4.2.x rejects host/port there ("unexpected keyword argument 'host'")
and `open-terminal mcp` exits 1, which breaks every gateway session.
This passes host/port only for non-stdio transports. Idempotent. Usage: patch_open_terminal.py [extra-root ...]
"""
import glob, os, sys

OLD = "    mcp_server.run(transport=transport, host=host, port=port)"
NEW = ('    mcp_server.run(transport=transport) if transport == "stdio" '
       'else mcp_server.run(transport=transport, host=host, port=port)')

home = os.path.expanduser("~")
roots = sys.argv[1:] + [
    f"{home}/.local/share/uv/tools/open-terminal",
    f"{home}/.local/share/pipx/venvs/open-terminal",
    f"{home}/.local/lib",
]
found = patched = 0
for r in roots:
    for f in glob.glob(f"{r}/**/open_terminal/cli.py", recursive=True):
        found += 1
        s = open(f).read()
        if NEW in s:
            continue
        if OLD in s:
            open(f, "w").write(s.replace(OLD, NEW))
            patched += 1
            print("patched", f)
if not found:
    sys.exit("open_terminal/cli.py not found; is open-terminal installed?")
print(f"open-terminal cli.py: {found} found, {patched} patched")
