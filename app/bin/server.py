#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""One-click restore helper for fnOS WebDAV shares."""
import html
import os
import subprocess
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DEFAULT_PORT = 7598
UNITS = ("share_service.service", "webdav.service")


def load_config():
    cfg = {
        "port": int(os.environ.get("WEBDAVFIX_PORT", str(DEFAULT_PORT))),
        "user": os.environ.get("WEBDAVFIX_DAV_USER", ""),
        "password": os.environ.get("WEBDAVFIX_DAV_PASSWORD", ""),
        "need": os.environ.get("WEBDAVFIX_NEED_SHARES", ""),
    }
    etc = os.environ.get("WEBDAVFIX_ETC", "")
    path = os.path.join(etc, "config.env") if etc else ""
    if path and os.path.isfile(path):
        for raw in open(path, encoding="utf-8"):
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key == "WEBDAVFIX_PORT" and value.strip():
                cfg["port"] = int(value.strip())
            elif key == "WEBDAVFIX_DAV_USER":
                cfg["user"] = value
            elif key == "WEBDAVFIX_DAV_PASSWORD":
                cfg["password"] = value
            elif key == "WEBDAVFIX_NEED_SHARES":
                cfg["need"] = value
    if isinstance(cfg["need"], str):
        cfg["need"] = [item.strip() for item in cfg["need"].split(",") if item.strip()]
    return cfg


def wait_active(unit):
    subprocess.run(["systemctl", "restart", unit], check=True, timeout=60)
    state = "unknown"
    for _ in range(20):
        state = subprocess.run(
            ["systemctl", "is-active", unit],
            stdout=subprocess.PIPE,
            text=True,
            timeout=10,
        ).stdout.strip()
        if state == "active":
            return state
        time.sleep(1)
    raise RuntimeError("%s 未就绪: %s" % (unit, state))


def dav_names(cfg):
    user = cfg.get("user") or ""
    password = cfg.get("password") or ""
    if not user or not password:
        return None
    base = "http://127.0.0.1:5005"
    manager = urllib.request.HTTPPasswordMgrWithDefaultRealm()
    manager.add_password(None, base + "/", user, password)
    client = urllib.request.build_opener(
        urllib.request.HTTPDigestAuthHandler(manager),
        urllib.request.HTTPBasicAuthHandler(manager),
    )
    body = b'<?xml version="1.0"?><d:propfind xmlns:d="DAV:"><d:prop><d:displayname/></d:prop></d:propfind>'
    request = urllib.request.Request(
        base + "/",
        data=body,
        method="PROPFIND",
        headers={"Depth": "1", "Content-Type": "application/xml; charset=utf-8"},
    )
    with client.open(request, timeout=20) as response:
        tree = ET.fromstring(response.read())
    names = []
    for entry in tree.findall("{DAV:}response"):
        href = urllib.parse.unquote(
            urllib.parse.urlsplit(entry.findtext("{DAV:}href", "")).path
        ).strip("/")
        if not href:
            continue
        prop = entry.find(".//{DAV:}prop")
        name = prop.findtext("{DAV:}displayname", "") if prop is not None else ""
        names.append(name or href)
    return names


def restore():
    cfg = load_config()
    before = None
    before_error = ""
    try:
        before = dav_names(cfg)
    except Exception as exc:
        before_error = type(exc).__name__
        before = []
    for unit in UNITS:
        wait_active(unit)
        time.sleep(2)
    after = None
    after_error = ""
    try:
        after = dav_names(cfg)
    except Exception as exc:
        after_error = type(exc).__name__
        after = []
    need = cfg.get("need") or []
    missing = [name for name in need if after is not None and name not in after]
    return {
        "cfg": cfg,
        "before": before,
        "before_error": before_error,
        "after": after,
        "after_error": after_error,
        "missing": missing,
        "need": need,
    }


def page(result, error=None):
    after = result.get("after")
    missing = result.get("missing") or []
    need = result.get("need") or []
    listed = after is not None
    items = ""
    if after:
        items = "".join("<li>%s</li>" % html.escape(name) for name in after)
    elif result.get("after_error"):
        items = "<li>列出失败：%s</li>" % html.escape(result["after_error"])
    elif after is None:
        items = "<li>未配置 WebDAV 账号，已跳过列盘。服务已重启。</li>"
    else:
        items = "<li>没有列出任何盘</li>"

    if error:
        banner, detail, color, bg = "恢复失败", html.escape(error), "#b42318", "#fef3f2"
    elif listed and need and not missing:
        banner = "WebDAV 已恢复"
        detail = "现在共 %s 个盘，客户端刷新即可。" % len(after)
        color, bg = "#067647", "#ecfdf3"
    elif listed and not need and after:
        banner = "WebDAV 服务已重启"
        detail = "当前列出 %s 个盘，客户端刷新即可。" % len(after)
        color, bg = "#067647", "#ecfdf3"
    elif missing:
        banner, detail, color, bg = "还缺盘", "缺少：%s" % "、".join(missing), "#b54708", "#fffaeb"
    else:
        banner = "共享服务已重启"
        detail = "share_service 与 webdav 已重新拉起。可在应用设置中填写账号以核对盘符。"
        color, bg = "#067647", "#ecfdf3"

    return """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>恢复 WebDAV</title>
<style>
body{font-family:"Segoe UI","Microsoft YaHei",sans-serif;background:#f4f6f8;margin:0;color:#1f2a37}
main{max-width:560px;margin:48px auto;background:#fff;border-radius:16px;padding:28px 32px;box-shadow:0 8px 24px rgb(15 23 42 / 8%%)}
h1{margin:0 0 12px;font-size:24px}
.banner{background:%s;color:%s;border-radius:12px;padding:12px 16px;margin:16px 0;font-weight:600}
ul{padding-left:20px;line-height:1.9}
button{appearance:none;border:0;background:#087f8c;color:#fff;font-size:16px;padding:12px 18px;border-radius:10px;cursor:pointer}
button:hover{background:#0a6f7a}
.muted{color:#667085;font-size:13px}
</style>
</head>
<body>
<main>
<h1>恢复 WebDAV</h1>
<div class="banner">%s</div>
<p>%s</p>
<ul>%s</ul>
<form method="post" action="/">
<button type="submit">再恢复一次</button>
</form>
<p class="muted">飞牛误判存储卷卸载导致 WebDAV 丢盘时，点桌面图标即可。</p>
</main>
</body>
</html>
""" % (bg, color, banner, html.escape(detail), items)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def send_html(self, body, code=200):
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def restore_page(self):
        try:
            self.send_html(page(restore()))
        except Exception as exc:
            self.send_html(page({"after": [], "missing": [], "need": []}, error=str(exc)), code=500)

    def do_GET(self):
        if self.path.startswith("/favicon"):
            self.send_response(204)
            self.end_headers()
            return
        self.restore_page()

    def do_POST(self):
        self.restore_page()


if __name__ == "__main__":
    port = load_config()["port"]
    httpd = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print("webdavfix listening", port, flush=True)
    httpd.serve_forever()
