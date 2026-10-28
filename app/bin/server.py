#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""List fnOS WebDAV mappings and reload or unlink the ones the user selects."""
import html
import json
import os
import re
import subprocess
import threading
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DEFAULT_PORT = 7598
SHARE_ROOT = "/share/home"
VOL_RE = re.compile(r"^/vol\d+/")
ACTION_LOCK = threading.Lock()


def load_config():
    cfg = {
        "port": int(os.environ.get("WEBDAVFIX_PORT", str(DEFAULT_PORT))),
        "user": os.environ.get("WEBDAVFIX_DAV_USER", ""),
        "password": os.environ.get("WEBDAVFIX_DAV_PASSWORD", ""),
        "need": os.environ.get("WEBDAVFIX_NEED_SHARES", ""),
        "etc": os.environ.get("WEBDAVFIX_ETC", ""),
    }
    path = os.path.join(cfg["etc"], "config.env") if cfg["etc"] else ""
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


def store_path(cfg):
    etc = cfg.get("etc") or ""
    if not etc:
        return ""
    return os.path.join(etc, "maps.json")


def empty_store():
    return {"shares": [], "excluded": []}


def load_store(cfg):
    path = store_path(cfg)
    if not path or not os.path.isfile(path):
        return empty_store()
    try:
        data = json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError):
        return empty_store()
    if not isinstance(data, dict):
        return empty_store()
    data.setdefault("shares", [])
    data.setdefault("excluded", [])
    return data


def save_store(cfg, store):
    path = store_path(cfg)
    if not path:
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(store, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def row_key(uid, parts):
    return uid + "\t" + "\t".join(parts)


def parse_entry(entry):
    if not isinstance(entry, dict):
        return None
    uid = str(entry.get("uid") or "")
    parts = entry.get("parts") or []
    target = entry.get("target") or ""
    if not uid.isdigit() or not isinstance(parts, list):
        return None
    try:
        parts = valid_parts(parts)
    except ValueError:
        return None
    if target and not VOL_RE.match(target):
        target = ""
    return {"uid": uid, "parts": parts, "target": target}


def valid_parts(parts):
    if not isinstance(parts, list) or not parts or len(parts) > 2:
        raise ValueError("映射名称无效")
    cleaned = []
    for part in parts:
        if not isinstance(part, str):
            raise ValueError("映射名称无效")
        if (
            not part
            or part in (".", "..")
            or "/" in part
            or "\\" in part
            or "\x00" in part
            or "\t" in part
            or "\n" in part
            or "\r" in part
        ):
            raise ValueError("映射名称无效")
        cleaned.append(part)
    return cleaned


def webdav_dir(uid):
    if not str(uid).isdigit():
        raise ValueError("用户无效")
    root = os.path.realpath(SHARE_ROOT)
    path = os.path.realpath(os.path.join(SHARE_ROOT, str(uid), "webdav"))
    if path != root and not path.startswith(root + os.sep):
        raise ValueError("映射目录无效")
    return path


def link_path(uid, parts):
    parts = valid_parts(parts)
    base = webdav_dir(uid)
    path = base
    for part in parts:
        path = os.path.join(path, part)
    parent = os.path.dirname(os.path.normpath(path))
    if len(parts) == 1 and parent != base:
        raise ValueError("映射路径无效")
    if len(parts) == 2 and os.path.dirname(parent) != base:
        raise ValueError("映射路径无效")
    return path


def normalize_target(raw):
    if not raw or not raw.startswith("/"):
        return ""
    real = os.path.realpath(raw)
    if not VOL_RE.match(real) or not os.path.isdir(real):
        return ""
    return real


def scan_live():
    found = []
    if not os.path.isdir(SHARE_ROOT):
        return found
    for uid in sorted(os.listdir(SHARE_ROOT)):
        if not uid.isdigit():
            continue
        dav = os.path.join(SHARE_ROOT, uid, "webdav")
        if not os.path.isdir(dav):
            continue
        for name in sorted(os.listdir(dav)):
            path = os.path.join(dav, name)
            if os.path.islink(path):
                found.append(live_item(uid, [name], path))
            elif os.path.isdir(path):
                for child in sorted(os.listdir(path)):
                    child_path = os.path.join(path, child)
                    if os.path.islink(child_path):
                        found.append(live_item(uid, [name, child], child_path))
    return found


def live_item(uid, parts, path):
    raw = os.readlink(path)
    if raw and not os.path.isabs(raw):
        raw = os.path.join(os.path.dirname(path), raw)
    target = normalize_target(raw)
    return {"uid": uid, "parts": valid_parts(parts), "target": target, "linked": True}


def index_entries(entries):
    result = {}
    for entry in entries:
        parsed = parse_entry(entry)
        if parsed:
            result[row_key(parsed["uid"], parsed["parts"])] = parsed
    return result


def merge_store(store, live):
    shares = index_entries(store.get("shares") or [])
    for item in live:
        key = row_key(item["uid"], item["parts"])
        previous = shares.get(key) or {"uid": item["uid"], "parts": item["parts"], "target": ""}
        if item.get("target"):
            previous["target"] = item["target"]
        shares[key] = previous
    store["shares"] = [shares[key] for key in sorted(shares)]
    store["excluded"] = [index_entries(store.get("excluded") or [])[key] for key in sorted(index_entries(store.get("excluded") or []))]
    return store


def build_rows(store, live):
    shares = index_entries(store.get("shares") or [])
    excluded = index_entries(store.get("excluded") or [])
    linked = {row_key(item["uid"], item["parts"]): item for item in live}
    keys = sorted(set(shares) | set(excluded) | set(linked))
    rows = []
    for key in keys:
        base = shares.get(key) or linked.get(key) or excluded.get(key)
        current = linked.get(key)
        target = ""
        if current and current.get("target"):
            target = current["target"]
        elif base:
            target = base.get("target") or ""
        target_ok = bool(target) and os.path.isdir(target)
        is_excluded = key in excluded
        is_linked = current is not None
        if is_excluded and is_linked:
            status = "已排除，映射仍在"
        elif is_excluded:
            status = "已排除"
        elif is_linked and target_ok:
            status = "在线"
        elif is_linked:
            status = "目标不存在"
        elif target_ok:
            status = "缺失"
        else:
            status = "无法重新加载"
        rows.append({
            "uid": base["uid"],
            "parts": base["parts"],
            "target": target,
            "linked": is_linked,
            "excluded": is_excluded,
            "target_ok": target_ok,
            "status": status,
            "token": json.dumps({"uid": base["uid"], "parts": base["parts"]}, ensure_ascii=False, separators=(",", ":")),
        })
    return rows


def display_name(parts):
    return " / ".join(parts)


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


def restart_units(units):
    for unit in units:
        wait_active(unit)
        time.sleep(1)


def ensure_link(uid, parts, target):
    target = normalize_target(target)
    if not target:
        raise RuntimeError("目标目录不存在，不能重新加载")
    path = link_path(uid, parts)
    parent = os.path.dirname(path)
    if os.path.islink(parent):
        raise RuntimeError("上级目录是软链，已拒绝创建")
    if not os.path.isdir(parent):
        if len(parts) != 2 or os.path.lexists(parent):
            raise RuntimeError("上级目录不存在")
        if os.path.dirname(parent) != webdav_dir(uid):
            raise RuntimeError("上级目录无效")
        os.mkdir(parent, 0o755)
    if os.path.islink(path):
        current = normalize_target(os.readlink(path))
        if current == target:
            return "已在"
        os.unlink(path)
    elif os.path.lexists(path):
        raise RuntimeError("路径不是软链，已拒绝覆盖")
    os.symlink(target, path)
    return "已补回"


def remove_link(uid, parts):
    path = link_path(uid, parts)
    if os.path.islink(path):
        os.unlink(path)
        return True
    if os.path.lexists(path):
        raise RuntimeError("不是软链，已拒绝删除")
    return False


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


def selected_rows(rows, tokens):
    by_token = {row["token"]: row for row in rows}
    chosen = []
    seen = set()
    for token in tokens:
        row = by_token.get(token)
        if row and row["token"] not in seen:
            chosen.append(row)
            seen.add(row["token"])
    return chosen


def reload_selected(rows):
    notes = []
    changed = False
    for row in rows:
        label = "%s（用户 %s）" % (display_name(row["parts"]), row["uid"])
        if row["excluded"]:
            notes.append(label + "：已排除，请先取消排除")
            continue
        try:
            state = ensure_link(row["uid"], row["parts"], row["target"])
        except Exception as exc:
            notes.append(label + "：" + str(exc))
            continue
        notes.append(label + "：" + state)
        changed = True
    if changed:
        restart_units(("webdav.service",))
        notes.append("已重启 webdav")
    return notes


def uninstall_selected(cfg, store, rows):
    notes = []
    excluded = index_entries(store.get("excluded") or [])
    changed = False
    for row in rows:
        label = "%s（用户 %s）" % (display_name(row["parts"]), row["uid"])
        try:
            removed = remove_link(row["uid"], row["parts"])
        except Exception as exc:
            notes.append(label + "：" + str(exc))
            continue
        excluded[row_key(row["uid"], row["parts"])] = {
            "uid": row["uid"],
            "parts": row["parts"],
            "target": row["target"],
        }
        notes.append(label + ("：已去掉映射" if removed else "：映射本来就不在"))
        changed = True
    store["excluded"] = [excluded[key] for key in sorted(excluded)]
    save_store(cfg, store)
    if changed:
        restart_units(("webdav.service",))
        notes.append("已重启 webdav。文件仍在原目录。")
    return notes


def unexclude_selected(cfg, store, rows):
    excluded = index_entries(store.get("excluded") or [])
    notes = []
    for row in rows:
        key = row_key(row["uid"], row["parts"])
        label = "%s（用户 %s）" % (display_name(row["parts"]), row["uid"])
        if key in excluded:
            del excluded[key]
            notes.append(label + "：已取消排除")
        else:
            notes.append(label + "：不在排除名单")
    store["excluded"] = [excluded[key] for key in sorted(excluded)]
    save_store(cfg, store)
    return notes


def reload_all(cfg, store):
    restart_units(("share_service.service", "webdav.service"))
    notes = ["已重启 share_service 与 webdav"]
    removed = False
    for entry in list(index_entries(store.get("excluded") or []).values()):
        label = "%s（用户 %s）" % (display_name(entry["parts"]), entry["uid"])
        try:
            if remove_link(entry["uid"], entry["parts"]):
                notes.append(label + "：排除名单中的映射已再次去掉")
                removed = True
        except Exception as exc:
            notes.append(label + "：" + str(exc))
    if removed:
        restart_units(("webdav.service",))
        notes.append("已再次重启 webdav")
    return notes


def snapshot(cfg):
    store = merge_store(load_store(cfg), scan_live())
    save_store(cfg, store)
    return store, build_rows(store, scan_live())


def page(rows, message="", error="", confirm_rows=None, served=None):
    if error:
        banner, color, bg = html.escape(error), "#b42318", "#fef3f2"
    elif message:
        banner, color, bg = html.escape(message), "#067647", "#ecfdf3"
    else:
        banner, color, bg = "勾选映射后再操作。打开本页不会重启服务。", "#175cd3", "#eff8ff"

    body_rows = []
    for row in rows:
        served_text = "未核对"
        if served is not None:
            names = {display_name(row["parts"]), row["parts"][-1]}
            served_text = "已挂出" if names & set(served) else "未挂出"
        body_rows.append(
            "<tr><td><input type=\"checkbox\" name=\"sel\" value=\"%s\"%s></td>"
            "<td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>"
            % (
                html.escape(row["token"], quote=True),
                " checked" if confirm_rows and row["token"] in {item["token"] for item in confirm_rows} else "",
                html.escape(row["uid"]),
                html.escape(display_name(row["parts"])),
                html.escape(row["target"] or "—"),
                html.escape(row["status"]),
                html.escape(served_text),
            )
        )
    if not body_rows:
        body_rows.append("<tr><td colspan=\"6\">没有读到 WebDAV 映射。</td></tr>")

    confirm = ""
    if confirm_rows:
        labels = "、".join(html.escape(display_name(row["parts"])) for row in confirm_rows)
        hidden = "".join(
            "<input type=\"hidden\" name=\"sel\" value=\"%s\">" % html.escape(row["token"], quote=True)
            for row in confirm_rows
        )
        confirm = (
            "<form method=\"post\" action=\"/\">"
            "<p>确认卸载这些映射：%s。只删除软链，不删除文件。</p>"
            "%s<input type=\"hidden\" name=\"confirm\" value=\"1\">"
            "<button type=\"submit\" name=\"action\" value=\"uninstall\">确认卸载</button>"
            "</form>" % (labels, hidden)
        )

    table = "".join(body_rows)
    return """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>恢复 WebDAV</title>
<style>
body{font-family:"Segoe UI","Microsoft YaHei",sans-serif;background:#f4f6f8;margin:0;color:#1f2a37}
main{max-width:980px;margin:32px auto;background:#fff;border-radius:16px;padding:28px 32px;box-shadow:0 8px 24px rgb(15 23 42 / 8%%)}
h1{margin:0 0 12px;font-size:24px}
.banner{background:%s;color:%s;border-radius:12px;padding:12px 16px;margin:16px 0;font-weight:600}
table{width:100%%;border-collapse:collapse}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid #eaecf0;font-size:14px;vertical-align:top}
button{appearance:none;border:0;background:#087f8c;color:#fff;font-size:14px;padding:10px 14px;border-radius:10px;cursor:pointer;margin:12px 8px 0 0}
button.danger{background:#b42318}
button.plain{background:#344054}
button:hover{filter:brightness(0.95)}
.muted{color:#667085;font-size:13px}
</style>
</head>
<body>
<main>
<h1>恢复 WebDAV</h1>
<div class="banner">%s</div>
<form method="post" action="/">
<table>
<thead><tr><th></th><th>用户</th><th>映射</th><th>目标路径</th><th>状态</th><th>服务</th></tr></thead>
<tbody>%s</tbody>
</table>
<button type="submit" name="action" value="refresh" class="plain">刷新</button>
<button type="submit" name="action" value="reload">重新加载选中</button>
<button type="submit" name="action" value="uninstall" class="danger">卸载选中</button>
<button type="submit" name="action" value="unexclude" class="plain">取消排除</button>
<button type="submit" name="action" value="reload_all">全部重新加载</button>
</form>
%s
<p class="muted">卸载只去掉映射软链，磁盘上的文件还在。重新加载、卸载和全部重新加载都会重启 webdav，客户端会短暂断开。已排除的映射不会被全部重新加载加回来。</p>
</main>
</body>
</html>
""" % (bg, color, banner, table, confirm)


def read_form(handler):
    length = int(handler.headers.get("Content-Length") or "0")
    if length < 0 or length > 1024 * 1024:
        raise ValueError("请求过大")
    raw = handler.rfile.read(length).decode("utf-8", "replace")
    form = urllib.parse.parse_qs(raw, keep_blank_values=True)
    return {
        "action": (form.get("action") or ["refresh"])[0],
        "confirm": (form.get("confirm") or [""])[0],
        "sel": form.get("sel") or [],
    }


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

    def render(self, message="", error="", confirm_rows=None, code=200):
        cfg = load_config()
        served = None
        served_error = ""
        try:
            served = dav_names(cfg)
        except Exception as exc:
            served_error = type(exc).__name__
        with ACTION_LOCK:
            store, rows = snapshot(cfg)
        if served_error and not error:
            message = (message + " " if message else "") + "列出服务盘失败：" + served_error
        self.send_html(page(rows, message=message, error=error, confirm_rows=confirm_rows, served=served), code=code)

    def do_GET(self):
        path = urllib.parse.urlsplit(self.path).path
        if path.startswith("/favicon"):
            self.send_response(204)
            self.end_headers()
            return
        if path != "/":
            self.send_html(page([], error="页面不存在"), code=404)
            return
        try:
            self.render()
        except Exception as exc:
            self.send_html(page([], error=str(exc)), code=500)

    def do_POST(self):
        path = urllib.parse.urlsplit(self.path).path
        if path != "/":
            self.send_html(page([], error="页面不存在"), code=404)
            return
        try:
            form = read_form(self)
            cfg = load_config()
            message = ""
            error = ""
            confirm_rows = None
            with ACTION_LOCK:
                store, rows = snapshot(cfg)
                chosen = selected_rows(rows, form["sel"])
                action = form["action"]
                if action == "refresh":
                    message = "列表已刷新"
                elif action in ("reload", "uninstall", "unexclude") and not chosen:
                    error = "请先勾选映射"
                elif action == "reload":
                    message = "；".join(reload_selected(chosen))
                elif action == "uninstall" and form["confirm"] != "1":
                    confirm_rows = chosen
                    message = "请确认卸载。这一步还没有删除映射。"
                elif action == "uninstall":
                    message = "；".join(uninstall_selected(cfg, store, chosen))
                elif action == "unexclude":
                    message = "；".join(unexclude_selected(cfg, store, chosen))
                elif action == "reload_all":
                    message = "；".join(reload_all(cfg, store))
                else:
                    error = "未知操作"
            if error:
                self.render(error=error)
            else:
                self.render(message=message, confirm_rows=confirm_rows)
        except Exception as exc:
            self.send_html(page([], error=str(exc)), code=500)


if __name__ == "__main__":
    port = load_config()["port"]
    httpd = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print("webdavfix listening", port, flush=True)
    httpd.serve_forever()
