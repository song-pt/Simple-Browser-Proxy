#!/usr/bin/env python3
"""Browser Data Gateway: upstream fetch, downstream/client rendering. Python 3.8+."""
import base64
import gzip
import html
import http.cookiejar
import io
import os
import re
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

VERSION = "2.0.0"
PORT = int(os.environ.get("BDG_PORT", "6789"))
TIMEOUT = int(os.environ.get("BDG_TIMEOUT", "45"))
MAX_BODY = int(os.environ.get("BDG_MAX_BODY", str(32 * 1024 * 1024)))
SESSION_TTL = int(os.environ.get("BDG_SESSION_TTL", "3600"))
SESSION_COOKIE = "BDGSESSION"
TEXT_TYPES = ("text/html", "text/css", "application/xhtml+xml")
DROP_RESPONSE = {"content-length", "content-encoding", "transfer-encoding", "connection", "content-security-policy", "content-security-policy-report-only", "set-cookie", "location"}
DROP_REQUEST = {"host", "content-length", "connection", "proxy-connection", "cookie", "origin", "referer", "accept-encoding"}
ATTR_RE = re.compile(r'''(?P<pre>\b(?:href|src|action|poster|data-src)\s*=\s*["'])(?P<url>[^"']+)(?P<post>["'])''', re.I)
SRCSET_RE = re.compile(r'''(?P<pre>\bsrcset\s*=\s*["'])(?P<body>[^"']+)(?P<post>["'])''', re.I)
CSS_RE = re.compile(r'''url\(\s*(["']?)([^)'"\s]+)\1\s*\)''', re.I)
META_REFRESH_RE = re.compile(r'''(?P<pre>url\s*=\s*)(?P<url>[^;"']+)''', re.I)

class SessionStore(object):
    def __init__(self):
        self.lock = threading.Lock(); self.items = {}
    def get(self, sid):
        now = time.time()
        with self.lock:
            stale = [k for k, v in self.items.items() if now - v[1] > SESSION_TTL]
            for key in stale: self.items.pop(key, None)
            if sid not in self.items: self.items[sid] = (http.cookiejar.CookieJar(), now)
            jar, _ = self.items[sid]; self.items[sid] = (jar, now); return jar
SESSIONS = SessionStore()

def encode_url(url):
    return base64.urlsafe_b64encode(url.encode("utf-8")).decode("ascii").rstrip("=")
def decode_url(value):
    return base64.urlsafe_b64decode((value + "=" * (-len(value) % 4)).encode("ascii")).decode("utf-8")
def normalize_url(value):
    value = urllib.parse.unquote(value.strip())
    if "://" not in value: value = "https://" + value
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("仅支持不含内嵌账号密码的 HTTP/HTTPS 地址")
    return urllib.parse.urlunsplit(parsed)
def proxy_url(value, base):
    value = html.unescape(value.strip())
    if not value or value.startswith(("#", "data:", "blob:", "javascript:", "mailto:", "tel:")): return value
    return "/_p/" + encode_url(urllib.parse.urljoin(base, value))
def rewrite_content(text, base, content_type):
    if "html" in content_type:
        text = ATTR_RE.sub(lambda m: m.group("pre") + proxy_url(m.group("url"), base) + m.group("post"), text)
        def srcset(m):
            parts=[]
            for item in m.group("body").split(","):
                bits=item.strip().split(None, 1); parts.append(proxy_url(bits[0], base) + ((" " + bits[1]) if len(bits)>1 else ""))
            return m.group("pre") + ", ".join(parts) + m.group("post")
        text = SRCSET_RE.sub(srcset, text)
        text = META_REFRESH_RE.sub(lambda m: m.group("pre") + proxy_url(m.group("url").strip(), base), text)
    if "html" in content_type or "css" in content_type:
        text = CSS_RE.sub(lambda m: "url(" + proxy_url(m.group(2), base) + ")", text)
    return text

def session_id(cookie_header):
    match = re.search(r"(?:^|;\s*)" + SESSION_COOKIE + r"=([A-Za-z0-9_-]{20,100})", cookie_header or "")
    return (match.group(1), False) if match else (secrets.token_urlsafe(24), True)

class GatewayHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def do_GET(self): self.handle_request()
    def do_POST(self): self.handle_request()
    def do_PUT(self): self.handle_request()
    def do_PATCH(self): self.handle_request()
    def do_DELETE(self): self.handle_request()
    def do_HEAD(self): self.handle_request()
    def reply(self, status, body, content_type="text/plain; charset=utf-8", extra=None):
        if isinstance(body, str): body=body.encode("utf-8")
        self.send_response(status); self.send_header("Content-Type", content_type); self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or []): self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD": self.wfile.write(body)
    def handle_request(self):
        path = urllib.parse.urlsplit(self.path).path
        if path == "/healthz": return self.reply(200, "ok version=%s\n" % VERSION)
        if path == "/":
            page='''<!doctype html><html lang="zh"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Browser Data Gateway</title><style>body{font:16px sans-serif;max-width:760px;margin:12vh auto;padding:20px}form{display:flex;gap:8px}input{flex:1;padding:12px}button{padding:12px}</style><h1>Browser Data Gateway</h1><p>远端获取，本地渲染</p><form onsubmit="location.href='/'+encodeURIComponent(u.value);return false"><input id="u" required placeholder="https://www.example.com"><button>打开</button></form></html>'''
            return self.reply(200, page, "text/html; charset=utf-8")
        try:
            target = normalize_url(decode_url(path[4:])) if path.startswith("/_p/") else normalize_url(path[1:])
        except Exception as exc:
            return self.reply(400, "Bad target: %s\n" % exc)
        if not path.startswith("/_p/"):
            return self.reply(302, b"", extra=[("Location", "/_p/" + encode_url(target))])
        sid, fresh = session_id(self.headers.get("Cookie")); jar = SESSIONS.get(sid)
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length > MAX_BODY: return self.reply(413, "request too large\n")
        body = self.rfile.read(length) if length else None
        headers = {k:v for k,v in self.headers.items() if k.lower() not in DROP_REQUEST}
        headers["Accept-Encoding"] = "gzip"
        req = urllib.request.Request(target, data=body, headers=headers, method=self.command)
        try:
            response = opener.open(req, timeout=TIMEOUT)
        except urllib.error.HTTPError as exc: response = exc
        except Exception as exc: return self.reply(502, "upstream error: %s\n" % exc)
        data = response.read(MAX_BODY + 1)
        if len(data) > MAX_BODY: return self.reply(502, "upstream response too large\n")
        if response.headers.get("Content-Encoding", "").lower() == "gzip": data = gzip.GzipFile(fileobj=io.BytesIO(data)).read()
        ctype = response.headers.get("Content-Type", "application/octet-stream")
        if ctype.lower().startswith(TEXT_TYPES):
            charset = response.headers.get_content_charset() or "utf-8"
            data = rewrite_content(data.decode(charset, "replace"), response.geturl(), ctype.lower()).encode("utf-8")
            ctype = ctype.split(";",1)[0] + "; charset=utf-8"
        self.send_response(response.status); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(data)))
        if fresh: self.send_header("Set-Cookie", "%s=%s; Path=/; HttpOnly; SameSite=Lax" % (SESSION_COOKIE, sid))
        for k,v in response.headers.items():
            if k.lower() not in DROP_RESPONSE and k.lower() != "content-type": self.send_header(k,v)
        self.end_headers()
        if self.command != "HEAD": self.wfile.write(data)
    def log_message(self, fmt, *args): print("gateway:", fmt % args, flush=True)

def main():
    server=ThreadingHTTPServer(("0.0.0.0", PORT), GatewayHandler); print("Browser Data Gateway %s on :%d" % (VERSION,PORT),flush=True); server.serve_forever()
if __name__ == "__main__": main()
