# -*- coding: utf-8 -*-
import os
import subprocess

print("=== tree /var/apps/webdavfix ===", flush=True)
for root, dirs, files in os.walk("/var/apps/webdavfix"):
    for name in files:
        path = os.path.join(root, name)
        print(path, os.path.getsize(path) if os.path.isfile(path) else "", oct(os.stat(path).st_mode))

print("=== logs ===", flush=True)
for path in (
    "/var/log/apps/webdavfix.log",
    "/var/apps/webdavfix/var/webdavfix.log",
    "/var/apps/webdavfix/etc/config.env",
):
    print("FILE", path, "exists", os.path.isfile(path))
    if os.path.isfile(path):
        data = open(path, encoding="utf-8", errors="replace").read()
        if "PASSWORD" in path.upper() or path.endswith("config.env"):
            print("  keys:", [line.split("=", 1)[0] for line in data.splitlines() if "=" in line])
        else:
            print(data[-3000:])

print("=== env sample from cmd/main ===", flush=True)
print(open("/var/apps/webdavfix/cmd/main", encoding="utf-8", errors="replace").read()[:2000] if os.path.isfile("/var/apps/webdavfix/cmd/main") else "no cmd/main")

print("=== find main ===", flush=True)
for root, dirs, files in os.walk("/var/apps/webdavfix"):
    if "main" in files or "server.py" in files:
        print("dir", root, "files", files)

print("=== journal ===", flush=True)
r = subprocess.run(["journalctl", "-u", "webdavfix", "-n", "40", "--no-pager"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
print(r.stdout[-3000:])
r = subprocess.run(["ls", "-la", "/var/log/apps"], stdout=subprocess.PIPE, text=True)
print(r.stdout)
print("=== ss 7598 ===", flush=True)
r = subprocess.run(["ss", "-lntp"], stdout=subprocess.PIPE, text=True)
for line in r.stdout.splitlines():
    if "7598" in line or "webdavfix" in line:
        print(line)
