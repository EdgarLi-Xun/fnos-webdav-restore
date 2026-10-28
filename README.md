# fnos-webdav-restore

飞牛 fnOS 第三方应用（包名 `webdavfix`）：在桌面放一个 **恢复 WebDAV** 图标。WebDAV 盘突然消失时，打开后勾选要处理的映射。

飞牛会在误判存储卷卸载后清空该卷上的 WebDAV 共享（常见于 Docker BuildKit 写到数据盘临时目录）。映射是 `/share/home/<用户>/webdav/` 下指向真实目录的软链。

## 功能

- 安装后出现在飞牛桌面，在当前桌面窗口中打开
- 打开页面只列出映射，不会自动重启服务
- 勾选后可以重新加载、卸载或取消排除；也可以全部重新加载
- 卸载只删除软链，不删除磁盘上的文件，并记入排除名单
- 账号、密码在安装向导 / 应用设置中填写，不写进仓库

## 要求

- fnOS 1.2.0 及以上
- 系统自带 Python 3
- 需要 root 权限以重启系统共享服务

## 打包

本机或 NAS 上：

```bash
python3 generate_icons.py
./build.sh
```

若已安装官方 `fnpack`：

```bash
fnpack build
```

产物为 `webdavfix.fpk`（gzip tar）。不要把 `.fpk`、密码或 `install.env` 提交到 Git。

## 安装

在飞牛设备上开启手动安装后安装 FPK：

```bash
appcenter-cli manual-install enable
appcenter-cli install-fpk webdavfix.fpk
```

带核对账号时：

```bash
cp install.env.example install.env
# 编辑 install.env
appcenter-cli install-fpk webdavfix.fpk --env install.env
```

也可在应用中心 → 手动安装 中选择 `webdavfix.fpk`。

安装完成后刷新飞牛桌面，点击 **恢复 WebDAV**。

## 配置

| 项 | 说明 |
| --- | --- |
| WebDAV 用户名 / 密码 | 可选。用于列出 `http://127.0.0.1:5005/` 上的共享 |
| 需要核对的盘名 | 逗号分隔，例如 `软件,Photos,来自：百度网盘`。留空则只重启服务并列出当前盘 |

服务端口固定为 `7598`。

## 许可

MIT
