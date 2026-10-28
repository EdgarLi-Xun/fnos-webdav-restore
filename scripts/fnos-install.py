#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build and install the FPK on an fnOS device. Run as root."""
import glob
import os
import shutil
import subprocess
import sys
import time

APPNAME = "webdavfix"
SRC = os.environ.get("WEBDAVFIX_SRC", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ENV_FILE = os.environ.get("WEBDAVFIX_INSTALL_ENV", "")


def run(cmd, check=True, cwd=None):
    print(">>", " ".join(cmd), flush=True)
    return subprocess.run(cmd, check=check, cwd=cwd)


def strip_cr(path):
    data = open(path, "rb").read().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    open(path, "wb").write(data)
    os.chmod(path, 0o755)


def which(name):
    found = shutil.which(name)
    if found:
        return found
    for path in (
        "/usr/bin/%s" % name,
        "/usr/local/bin/%s" % name,
        "/usr/trim/bin/%s" % name,
        "/usr/sbin/%s" % name,
    ):
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return None


def cleanup_manual():
    run(["systemctl", "disable", "--now", "webdavfix.service"], check=False)
    for path in ("/etc/systemd/system/webdavfix.service", "/etc/fnos-webdavfix.env"):
        if os.path.isfile(path):
            os.remove(path)
    run(["systemctl", "daemon-reload"], check=False)
    subprocess.run(["pkill", "-f", "/var/apps/webdavfix/server.py"], check=False)
    sql = """
DELETE FROM app_shortcut WHERE app_id IN (SELECT id FROM app WHERE app_name='webdavfix');
DELETE FROM app_open WHERE app_id IN (SELECT id FROM app WHERE app_name='webdavfix');
DELETE FROM app_service WHERE app_id IN (SELECT id FROM app WHERE app_name='webdavfix');
DELETE FROM app WHERE app_name='webdavfix';
"""
    r = subprocess.run(
        ["psql", "-U", "postgres", "-d", "appcenter", "-v", "ON_ERROR_STOP=1", "-c", sql],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    print(r.stdout)
    if os.path.isdir("/var/apps/webdavfix") and not os.path.islink("/var/apps/webdavfix"):
        # Keep FPK target layout if installer created it; remove only leftover flat files.
        leftover = os.path.join("/var/apps/webdavfix", "server.py")
        if os.path.isfile(leftover):
            shutil.rmtree("/var/apps/webdavfix")


print("SRC", SRC, flush=True)
cleanup_manual()

for path in glob.glob(os.path.join(SRC, "cmd", "*")):
    if os.path.isfile(path):
        strip_cr(path)
strip_cr(os.path.join(SRC, "build.sh"))
run(["bash", "build.sh"], cwd=SRC)
fpk = os.path.join(SRC, "webdavfix.fpk")
if not os.path.isfile(fpk):
    raise SystemExit("fpk missing")

cli = which("appcenter-cli")
print("appcenter-cli", cli, flush=True)
if not cli:
    raise SystemExit("appcenter-cli not found")

run([cli, "manual-install", "enable"], check=False)
cmd = [cli, "install-fpk", fpk]
if ENV_FILE and os.path.isfile(ENV_FILE):
    cmd.extend(["--env", ENV_FILE])
run(cmd)
time.sleep(2)
run([cli, "start", APPNAME], check=False)
run([cli, "list"], check=False)
r = subprocess.run(
    ["psql", "-U", "postgres", "-d", "appcenter", "-c",
     "SELECT a.app_name, a.name, a.status, a.path FROM app a WHERE a.app_name='webdavfix';"
     " SELECT k.type, a.name FROM app_shortcut k JOIN app a ON a.id=k.app_id ORDER BY k.id;"],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
)
print(r.stdout)
print("INSTALL_DONE", flush=True)
