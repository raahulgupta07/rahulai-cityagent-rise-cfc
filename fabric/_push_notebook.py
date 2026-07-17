"""
Push fabric/CFC_ML_Pipeline_Fabric.ipynb to the HUB-AI notebook + (optionally) create
a daily schedule. Auth = ROPC from .env.prod (same creds as the app). Run:
    set -a && . ./.env.prod && set +a && python3 fabric/_push_notebook.py [--schedule]
"""
import base64, json, os, sys, time, urllib.parse, urllib.request, urllib.error, pathlib

T = os.environ["FABRIC_TENANT_ID"]; U = os.environ["FABRIC_USER"]; P = os.environ["FABRIC_PASSWORD"]
WS = os.environ["FABRIC_WORKSPACE_ID"]; NB = os.environ["FABRIC_NOTEBOOK_ID"]
CLIENT = "04b07795-8ddb-461a-bbee-02f9e1bf7b46"
API = "https://api.fabric.microsoft.com/v1"
IPYNB = pathlib.Path(__file__).with_name("CFC_ML_Pipeline_Fabric.ipynb")


def token():
    d = urllib.parse.urlencode({"grant_type": "password", "client_id": CLIENT,
        "scope": "https://api.fabric.microsoft.com/.default", "username": U, "password": P}).encode()
    return json.load(urllib.request.urlopen(f"https://login.microsoftonline.com/{T}/oauth2/v2.0/token", d))["access_token"]


def _req(method, url, tok, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method,
        headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
    return urllib.request.urlopen(r)


def push(tok):
    b64 = base64.b64encode(IPYNB.read_bytes()).decode()
    body = {"definition": {"parts": [
        {"path": "notebook-content.ipynb", "payload": b64, "payloadType": "InlineBase64"}]}}
    try:
        resp = _req("POST", f"{API}/workspaces/{WS}/items/{NB}/updateDefinition?updateMetadata=false", tok, body)
        print("updateDefinition:", resp.status, "pushed")
    except urllib.error.HTTPError as e:
        if e.code == 202:  # long-running op → poll
            loc = e.headers.get("Location")
            for _ in range(40):
                time.sleep(3)
                j = json.load(_req("GET", loc, tok))
                if j.get("status") in ("Succeeded", "Failed"):
                    print("updateDefinition op:", j.get("status")); break
        else:
            print("updateDefinition ERR", e.code, e.read()[:300].decode()); raise


def schedule(tok):
    """Daily RunNotebook schedule (runs with baked default MODE=auto)."""
    body = {"enabled": True, "configuration": {
        "type": "Daily", "times": ["02:00"],
        "startDateTime": "2026-07-17T00:00:00", "endDateTime": "2030-01-01T00:00:00",
        "localTimeZoneId": "Myanmar Standard Time"}}
    try:
        resp = _req("POST", f"{API}/workspaces/{WS}/items/{NB}/jobs/RunNotebook/schedules", tok, body)
        print("schedule created:", resp.status, json.load(resp).get("id"))
    except urllib.error.HTTPError as e:
        print("schedule ERR", e.code, e.read()[:400].decode())


def list_schedules(tok):
    try:
        j = json.load(_req("GET", f"{API}/workspaces/{WS}/items/{NB}/jobs/RunNotebook/schedules", tok))
        for s in j.get("value", []):
            print("SCHED", s.get("id"), s.get("enabled"), s.get("configuration", {}).get("type"),
                  s.get("configuration", {}).get("times"))
    except urllib.error.HTTPError as e:
        print("list ERR", e.code, e.read()[:300].decode())


if __name__ == "__main__":
    tok = token()
    push(tok)
    if "--schedule" in sys.argv:
        schedule(tok)
    list_schedules(tok)
