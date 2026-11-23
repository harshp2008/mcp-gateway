#!/usr/bin/env python3
"""Local approval popup for mcpproxy: polls /approvals/, asks via zenity, approves/rejects."""
import json, os, subprocess, sys, time, urllib.request

HOME_DIR = os.environ.get("MCPGW_HOME", os.path.expanduser("~/.mcp-gateway"))
BASE = os.environ.get("MCPGW_URL", "http://127.0.0.1:8765")
TOKEN = os.environ["MCPPROXY_APPROVAL_TOKEN"]
seen = set()

def api(method, path):
    req = urllib.request.Request(BASE + path, method=method,
                                 headers={"Authorization": f"Bearer {TOKEN}"})
    with urllib.request.urlopen(req, timeout=10) as r:
        body = r.read()
        return json.loads(body) if body else None

def trust_subject(subject):
    import datetime
    path = HOME_DIR + "/trusted.json"
    try:
        d = json.load(open(path))
    except FileNotFoundError:
        d = {}
    d[subject] = {"trusted_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
    tmp = path + ".tmp"
    open(tmp, "w").write(json.dumps(d, indent=2)); os.chmod(tmp, 0o600); os.replace(tmp, path)

def ask_session(item):
    """returns 'trust' | 'once' | 'deny'"""
    client = (item.get("rule") or "").partition("|")[2] or "unknown client"
    subject = str(item.get("user"))
    can_trust = subject.startswith("client:")
    text = (f"Allow this client to use the MCP gateway?\n\n"
            f"Credential: {subject}\nClient says it is: {client}\n"
            f"Session: {str(item.get('session'))[:8]}\n\n"
            + ("'Trust this client' lets this credential in without asking again until you revoke it "
               "(mcp-gateway trust revoke). Dangerous terminal commands are blocked by dcg."
               if can_trust else "This shared token cannot be trusted permanently; allowing for 1 hour."))
    cmd = ["zenity", "--question", "--title=MCP gateway: client access", "--width=500",
           "--cancel-label=Deny", "--timeout=280", "--no-markup", f"--text={text}"]
    if can_trust:
        cmd += ["--ok-label=Trust this client", "--extra-button=Allow 1 hour"]
    else:
        cmd += ["--ok-label=Allow 1 hour"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode == 0:
        return "trust" if can_trust else "once"
    if "Allow 1 hour" in r.stdout:
        return "once"
    return "deny"

def ask_oauth(item):
    a = item.get("args") or {}
    text = ("A NEW app wants OAuth access to your MCP gateway (full access: terminal, figma...).\n\n"
            f"App name (self-declared, can be fake): {a.get('client_name') or '(none)'}\n"
            f"Redirects to: {a.get('redirect_host')}\n"
            f"Client id: {str(a.get('client_id'))[:10]}...\n\n"
            "Only approve if YOU just started connecting this app (e.g. Gemini). "
            "Approving trusts this client until you revoke it (mcp-gateway trust revoke). Dangerous terminal commands are blocked by dcg.")
    r = subprocess.run(["zenity", "--question", "--title=MCP gateway: NEW OAuth client", "--width=520",
                        "--ok-label=Approve & trust", "--cancel-label=Deny", "--timeout=280",
                        "--no-markup", f"--text={text}"], capture_output=True)
    return "trust" if r.returncode == 0 else "deny"

def ask(item):
    if item.get("tool") == "oauth-consent":
        return ask_oauth(item)
    if str(item.get("rule", "")).startswith("session-gate"):
        return ask_session(item)   # 'trust' | 'once' | 'deny'
    args = json.dumps(item.get("args"), indent=2, ensure_ascii=False)
    if len(args) > 1500:
        args = args[:1500] + "\n…(truncated)"
    text = f"Tool: {item.get('tool')}\nCaller: {item.get('user')}\n\nArguments:\n{args}"
    r = subprocess.run(
        ["zenity", "--question", "--title=MCP gateway approval", "--width=520",
         "--ok-label=Approve", "--cancel-label=Deny", "--timeout=280",
         "--no-markup", f"--text={text}"],
        capture_output=True)
    return r.returncode == 0   # 0 = Approve; 1 = Deny; 5 = timeout (-> deny)

while True:
    try:
        for item in api("GET", "/approvals/") or []:
            iid = item["id"]
            if iid in seen:
                continue
            seen.add(iid)
            res = ask(item)
            if res == "trust":
                trust_subject(str(item.get("user")))
            ok = res in (True, "trust", "once")
            api("POST", f"/approvals/{iid}/{'approve' if ok else 'reject'}")
            print(time.strftime("%F %T"), iid, item.get("tool") or item.get("rule"), res if isinstance(res, str) else ("APPROVED" if ok else "DENIED"), flush=True)
    except Exception as e:
        print("err:", e, file=sys.stderr, flush=True)
    time.sleep(1)
