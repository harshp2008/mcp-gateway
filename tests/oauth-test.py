#!/usr/bin/env python3
"""OAuth flow regression test. Run with approver stopped; it resolves approvals itself."""
import base64, hashlib, json, os, secrets, subprocess, sys, threading, time, urllib.parse, urllib.request, urllib.error
B="http://127.0.0.1:8765"; AT=os.environ["MCPPROXY_APPROVAL_TOKEN"]
res=[]
def check(n,ok,extra=""):
    res.append(ok); print(("PASS " if ok else "FAIL ")+n, extra if not ok else "")
class NoRedir(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*a,**k): return None
op=urllib.request.build_opener(NoRedir)
def req(method,url,data=None,headers=None,form=False):
    h=dict(headers or {}); body=None
    if data is not None:
        if form: body=urllib.parse.urlencode(data).encode(); h["Content-Type"]="application/x-www-form-urlencoded"
        else: body=json.dumps(data).encode(); h["Content-Type"]="application/json"
    try:
        r=op.open(urllib.request.Request(url,data=body,method=method,headers=h),timeout=60)
        return r.status,dict(r.headers),r.read()
    except urllib.error.HTTPError as e: return e.code,dict(e.headers),e.read()
def approvals(): return json.loads(req("GET",B+"/approvals/",headers={"Authorization":"Bearer "+AT})[2] or b"[]")
def resolve(i,ok): req("POST",f"{B}/approvals/{i}/{'approve' if ok else 'reject'}",headers={"Authorization":"Bearer "+AT})
def wait_item(pred,t=15):
    for _ in range(t*5):
        for it in approvals():
            if pred(it): return it
        time.sleep(.2)
def authorize(cid,redir,chal,out):
    q=urllib.parse.urlencode(dict(response_type="code",client_id=cid,redirect_uri=redir,code_challenge=chal,code_challenge_method="S256",state="xyz"))
    out.append(req("GET",B+"/authorize?"+q))
def new_client(name):
    s,_,b=req("POST",B+"/register",{"redirect_uris":["https://example.test/cb"],"client_name":name}); return json.loads(b)["client_id"]
def pkce():
    v=secrets.token_urlsafe(48); return v,base64.urlsafe_b64encode(hashlib.sha256(v.encode()).digest()).rstrip(b"=").decode()
def mcp(tok,method,params=None):
    h={"Authorization":"Bearer "+tok,"Accept":"application/json, text/event-stream"}
    s,hd,b=req("POST",B+"/mcp",{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"oauth-test","version":"1"}}},h)
    if s!=200: return s,hd,b
    sid=hd.get("Mcp-Session-Id") or hd.get("Mcp-session-id")
    if sid: h["Mcp-Session-Id"]=sid
    req("POST",B+"/mcp",{"jsonrpc":"2.0","method":"notifications/initialized"},h)
    return req("POST",B+"/mcp",{"jsonrpc":"2.0","id":2,"method":method,"params":params or {}},h)

s,_,b=req("GET",B+"/.well-known/oauth-authorization-server"); check("AS metadata",s==200 and b"S256" in b)
s,_,b=req("GET",B+"/.well-known/oauth-protected-resource"); check("protected-resource metadata",s==200)
s,_,_=req("POST",B+"/mcp",{"jsonrpc":"2.0","id":1,"method":"ping"}); check("no token -> 401",s==401)

# deny path
cid=new_client("Fake Gemini"); v,c=pkce(); out=[]
t=threading.Thread(target=authorize,args=(cid,"https://example.test/cb",c,out)); t.start()
it=wait_item(lambda i:i.get("tool")=="oauth-consent")
check("consent held on /authorize",bool(it) and it["args"]["client_name"]=="Fake Gemini")
if it: resolve(it["id"],False)
t.join(); loc=out[0][1].get("Location","")
check("deny -> access_denied redirect",out[0][0]==302 and "error=access_denied" in loc and "code=" not in loc,loc)
out=[]; authorize(cid,"https://example.test/cb",c,out)
check("cooldown after deny (no popup)", "error=access_denied" in out[0][1].get("Location","") and not [i for i in approvals() if i.get("tool")=="oauth-consent"])

# unregistered redirect
q=urllib.parse.urlencode(dict(response_type="code",client_id=cid,redirect_uri="https://evil.test/cb",code_challenge=c,code_challenge_method="S256"))
s,_,_=req("GET",B+"/authorize?"+q); check("unregistered redirect refused",s==400)

# approve path
cid=new_client("Real Gemini"); v,c=pkce(); out=[]
t=threading.Thread(target=authorize,args=(cid,"https://example.test/cb",c,out)); t.start()
it=wait_item(lambda i:i.get("tool")=="oauth-consent"); resolve(it["id"],True); t.join()
loc=out[0][1].get("Location",""); code=urllib.parse.parse_qs(urllib.parse.urlparse(loc).query).get("code",[None])[0]
check("approve -> code issued",bool(code),loc)
s,_,b=req("POST",B+"/token",{"grant_type":"authorization_code","code":code,"redirect_uri":"https://example.test/cb","client_id":cid,"code_verifier":"wrong"+v},form=True)
check("wrong PKCE verifier rejected",s==400)
# code is consumed once even on failed attempt? re-authorize for clean test
cid2=new_client("Real Gemini 2"); v,c=pkce(); out=[]
t=threading.Thread(target=authorize,args=(cid2,"https://example.test/cb",c,out)); t.start()
it=wait_item(lambda i:i.get("tool")=="oauth-consent"); resolve(it["id"],True); t.join()
code=urllib.parse.parse_qs(urllib.parse.urlparse(out[0][1]["Location"]).query)["code"][0]
s,_,b=req("POST",B+"/token",{"grant_type":"authorization_code","code":code,"redirect_uri":"https://example.test/cb","client_id":cid2,"code_verifier":v},form=True)
tok=json.loads(b).get("access_token"); check("token issued",s==200 and bool(tok))
s,_,_=req("POST",B+"/token",{"grant_type":"authorization_code","code":code,"redirect_uri":"https://example.test/cb","client_id":cid2,"code_verifier":v},form=True)
check("code replay rejected",s==400)

# session gate on oauth identity: untrusted -> held; trusted -> through
out=[]; t=threading.Thread(target=lambda:out.append(mcp(tok,"tools/list"))); t.start()
it=wait_item(lambda i:str(i.get("rule","")).startswith("session-gate") and i.get("user")=="oauth:"+cid2)
check("untrusted oauth client gated",bool(it))
if it: resolve(it["id"],False)
t.join()
check("denied gate blocks tools/list", b"tools" not in out[0][2] or b"inputSchema" not in out[0][2])
subprocess.run(["python3","trust.py","add","oauth:"+cid2],check=True,capture_output=True)
s,h,b=mcp(tok,"tools/list"); check("trusted oauth client sees tools",s==200 and b"inputSchema" in b)
subprocess.run(["python3","trust.py","revoke","oauth:"+cid2],check=True,capture_output=True)
out=[]; t=threading.Thread(target=lambda:out.append(mcp(tok,"tools/list"))); t.start()
it=wait_item(lambda i:i.get("user")=="oauth:"+cid2,8)
check("revoked -> gated again",bool(it))
if it: resolve(it["id"],False)
t.join()
s,_,_=mcp("garbage.token.value","tools/list"); check("forged token -> 401",s==401)
check("clients persisted",os.path.exists("oauth-clients.json") and cid2 in open("oauth-clients.json").read())
print("ALL PASSED" if all(res) else "SOME FAILED"); sys.exit(0 if all(res) else 1)
