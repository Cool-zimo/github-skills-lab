"""版本管理：一版本一目录，互不共享。

    <home>/<name>/<version>/          版本根（只读视图的来源）
    <home>/<name>/<version>/.spm/     元数据 + VFS 写层 + token 副本
    <home>/<name>/active              当前版本指针（纯文本）
"""
import datetime
import json
import os
import re

from . import config

SAFE_NAME = re.compile(r"^[\w.\-]{1,64}$")
SAFE_VER = re.compile(r"^[\w.\-+]{1,64}$")


class VersionError(Exception):
    pass


def check(name, version):
    if not SAFE_NAME.match(name or ""):
        raise VersionError("名字不合法（只允许字母数字 . _ -）：%r" % name)
    if version is not None and not SAFE_VER.match(version):
        raise VersionError("版本号不合法：%r" % version)


def split(spec):
    """name@version → (name, version)；带 @ 必须给版本。"""
    if "@" in spec:
        name, version = spec.rsplit("@", 1)
        check(name, version)
        return name, version
    check(spec, None)
    return spec, None


def name_dir(name, h=None):
    check(name, None)
    return os.path.join(h or config.home(), name)


def versions(name, h=None):
    d = name_dir(name, h)
    if not os.path.isdir(d):
        return []
    out = []
    for x in sorted(os.listdir(d)):
        if SAFE_VER.match(x) and os.path.isdir(os.path.join(d, x)):
            out.append(x)
    return out


def active(name, h=None):
    p = os.path.join(name_dir(name, h), "active")
    if not os.path.isfile(p):
        return None
    with open(p, encoding="utf-8") as f:
        v = f.read().strip()
    return v if v in versions(name, h) else None


def set_active(name, version, h=None):
    check(name, version)
    if version not in versions(name, h):
        raise VersionError("版本不存在：%s@%s" % (name, version))
    d = name_dir(name, h)
    os.makedirs(d, exist_ok=True)
    tmp = os.path.join(d, ".active.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(version + "\n")
    os.replace(tmp, os.path.join(d, "active"))


def resolve(name, version=None, h=None):
    """显式版本 > active > 报错。"""
    vs = versions(name, h)
    if not vs:
        raise VersionError("没有安装任何版本：%s（先 spm install）" % name)
    v = version or active(name, h)
    if not v:
        raise VersionError("%s 未设当前版本，用 spm use %s@<版本> 或显式指定" % (name, name))
    if v not in vs:
        raise VersionError("版本不存在：%s@%s（已装：%s）" % (name, v, ", ".join(vs)))
    return v


def root(name, version, h=None):
    check(name, version)
    p = os.path.join(name_dir(name, h), version)
    config.assert_inside(h or config.home(), p, "版本目录")
    return p


def meta_dir(name, version, h=None):
    return os.path.join(root(name, version, h), ".spm")


def meta_path(name, version, h=None):
    return os.path.join(meta_dir(name, version, h), "meta.json")


def read_meta(name, version, h=None):
    p = meta_path(name, version, h)
    if not os.path.isfile(p):
        return {}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def write_meta(name, version, meta, h=None):
    d = meta_dir(name, version, h)
    os.makedirs(d, exist_ok=True)
    tmp = os.path.join(d, ".meta.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, meta_path(name, version, h))


def create(name, version, src, manifest, h=None, trust=False, vfs=True,
           allow=None, scripts=None, pr=None):
    """登记一个新版本。已存在则拒绝（避免悄悄覆盖）。"""
    check(name, version)
    r = root(name, version, h)
    if os.path.isdir(r) and os.path.isfile(meta_path(name, version, h)):
        raise VersionError("版本已存在：%s@%s（先 uninstall，或换个版本号）" % (name, version))
    meta = {
        "name": name,
        "version": version,
        "source": src,
        "installed_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "trusted": bool(trust),
        "vfs": bool(vfs),
        "allow_commands": list(allow or []),
        "scripts": dict(scripts or {}),
        "manifest": manifest,
        "files": len(manifest),
        "bytes": sum(x["size"] for x in manifest.values()),
    }
    if pr:
        meta["pr"] = pr
    write_meta(name, version, meta, h)
    os.makedirs(os.path.join(meta_dir(name, version, h), "sandbox"), exist_ok=True)
    if active(name, h) is None:
        set_active(name, version, h)
    return meta


def uninstall(name, version, h=None, safe=None):
    import shutil
    v = resolve(name, version, h)
    r = root(name, v, h)
    if safe is None:
        safe = config.safe_on(config.load(h))
    if safe:
        config.assert_inside(os.path.join(h or config.home(), name), r, "删除目标")
    was_active = active(name, h)
    shutil.rmtree(r)
    if was_active == v:
        p = os.path.join(name_dir(name, h), "active")
        if os.path.isfile(p):
            os.unlink(p)
        rest = versions(name, h)
        if rest:
            set_active(name, rest[-1], h)
    return v


def trust(name, version, value, h=None):
    v = resolve(name, version, h)
    m = read_meta(name, v, h)
    m["trusted"] = bool(value)
    write_meta(name, v, m, h)
    return v, m["trusted"]


def mode(name, version, value, h=None):
    v = resolve(name, version, h)
    m = read_meta(name, v, h)
    m["vfs"] = bool(value)
    write_meta(name, v, m, h)
    return v, m["vfs"]


def allow(name, version, cmds, h=None, replace=True):
    v = resolve(name, version, h)
    m = read_meta(name, v, h)
    old = m.get("allow_commands") or []
    m["allow_commands"] = sorted(set(cmds if replace else old + list(cmds)))
    write_meta(name, v, m, h)
    return v, m["allow_commands"]
