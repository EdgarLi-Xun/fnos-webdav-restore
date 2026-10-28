# -*- coding: utf-8 -*-
import os
import shutil
import subprocess
import time

src = "/tmp/webdavfix-main"
dst = "/var/apps/webdavfix/cmd/main"
data = open(src, "rb").read().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
open(dst, "wb").write(data)
os.chmod(dst, 0o755)
print("patched", dst, len(data), flush=True)

cli = "/usr/local/bin/appcenter-cli"
subprocess.run([cli, "stop", "webdavfix"], check=False)
time.sleep(1)
r = subprocess.run([cli, "start", "webdavfix"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
print("start rc", r.returncode)
print(r.stdout)
time.sleep(1)
subprocess.run([cli, "list"], check=False)
print("=== curl ===", flush=True)
r = subprocess.run(
    ["curl", "-sS", "-m", "60", "-o", "/tmp/webdavfix.html", "-w", "HTTP %{http_code} time %{time_total}\n", "http://127.0.0.1:7598/"],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
)
print(r.stdout)
print(open("/tmp/webdavfix.html", encoding="utf-8", errors="replace").read()[:1200])
print("=== sql ===", flush=True)
r = subprocess.run(
    ["psql", "-U", "postgres", "-d", "appcenter", "-c",
     "SELECT app_name, name, status FROM app WHERE app_name='webdavfix';"
     " SELECT k.type, a.name FROM app_shortcut k JOIN app a ON a.id=k.app_id ORDER BY k.id;"],
    stdout=subprocess.PIPE, text=True,
)
print(r.stdout)
