"""下载与解包。

- zip / tar.gz / 单文件都支持
- 防 zip-slip：绝对路径、..、符号链接一律拒绝
- 落盘后写 manifest（每个文件 sha256 + size），可随时 verify
"""
import hashlib
import io
import os
import re
import tarfile
import urllib.parse
import zipfile

from . import _gh as G
from . import config, sources


class FetchError(Exception):
    pass


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def _http(url, token, timeout=90):
    """直链下载；ghlib.req 只认 API，所以 url 源单独走 urllib。"""
    headers = dict(G.BASE_HEADERS)
    if token and ("api.github.com" in url or "github.com" in url):
        headers["Authorization"] = "Bearer " + token
    req = G.urllib.request.Request(url, headers=headers)
    with G.urllib.request.urlopen(req, timeout=timeout) as f:
        return f.read()


def download(src, token, rel=None):
    """按源取回 bytes。rel 用于 github 源指定 path 下的具体文件名。"""
    t = src["type"]
    if t == "path":
        p = src["path"]
        if rel:
            p = os.path.join(p, rel)
        if os.path.isdir(p):
            return _pack_dir(p)
        if not os.path.isfile(p):
            raise FetchError("本地源不存在：%s" % p)
        with open(p, "rb") as f:
            return f.read()
    if t == "url":
        data = _http(src["url"], token)
        if src.get("sha256") and sha256(data) != src["sha256"]:
            raise FetchError("sha256 校验失败（期望 %s）" % src["sha256"][:12])
        return data
    if t == "github":
        if rel:
            return sources.github_raw(src, rel, token)
        # 没给具体文件 → 整仓 zipball
        return G.zipball(token, src["repo"], src["ref"])
    raise FetchError("不支持的源类型：%s" % t)


def _pack_dir(p):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for base, dirs, files in os.walk(p):
            dirs[:] = [d for d in dirs if d not in (".git", "__pycache__")]
            for fn in sorted(files):
                fp = os.path.join(base, fn)
                z.write(fp, os.path.relpath(fp, p).replace(os.sep, "/"))
    return buf.getvalue()


def _safe_rel(name):
    """拒绝绝对路径、..、盘符、符号链接式路径。"""
    if not name or name.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", name):
        raise FetchError("解包拒绝绝对路径：%r" % name)
    parts = name.replace("\\", "/").split("/")
    if any(x in ("..", "") for x in parts):
        raise FetchError("解包拒绝越界路径：%r" % name)
    return "/".join(parts)


def unpack(data, dest, strip_top=True):
    """解包到 dest，返回 manifest。兼容 zip / tar.gz / 单文件文本。"""
    os.makedirs(dest, exist_ok=True)
    root = os.path.realpath(dest)
    written = {}

    def put(rel, payload):
        rel = _safe_rel(rel)
        out = os.path.join(root, rel)
        if os.path.commonpath([root, os.path.realpath(os.path.dirname(out))]) != root:
            raise FetchError("解包越界：%s" % rel)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "wb") as f:
            f.write(payload)
        written[rel] = {"sha256": sha256(payload), "size": len(payload)}

    is_zip = data[:2] == b"PK"
    is_tar = data[:2] == b"\x1f\x8b"
    if is_zip:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            infos = [i for i in z.infolist() if not i.is_dir()]
            if not infos:
                raise FetchError("zip 里没有文件")
            # GitHub zipball 有一层 owner-repo-sha/ 顶层目录，统一剥掉
            tops = {i.filename.split("/")[0] for i in infos if "/" in i.filename}
            strip = (tops.pop() + "/") if (strip_top and len(tops) == 1) else ""
            for i in infos:
                if ((i.external_attr >> 16) & 0o170000) == 0o120000:
                    raise FetchError("解包拒绝符号链接：%s" % i.filename)
                name = i.filename
                if strip and name.startswith(strip):
                    name = name[len(strip):]
                if name:
                    put(name, z.read(i))
    elif is_tar:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as t:
            for m in t.getmembers():
                if not m.isfile():
                    continue  # 目录 / 链接都不落盘
                name = m.name
                if strip_top and "/" in name:
                    name = name.split("/", 1)[1]
                if name:
                    put(name, t.extractfile(m).read())
    else:
        # 单个文本文件（SKILL.md / 单个 .py 之类）
        name = "skill.md" if data[:1] in (b"#", b"-") else "payload.bin"
        put(name, data)
    return written


def verify(dest, manifest):
    """逐文件 sha256 校验。返回 (通过数, 总数, 失败列表)。"""
    bad = []
    root = os.path.realpath(dest)
    for rel, info in sorted(manifest.items()):
        p = os.path.join(root, rel)
        if not os.path.isfile(p):
            bad.append(rel + " (缺失)")
            continue
        with open(p, "rb") as f:
            if sha256(f.read()) != info["sha256"]:
                bad.append(rel)
    extra = []
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in (".spm", "__pycache__", ".git")]
        for fn in files:
            if fn.endswith(".pyc"):
                continue
            rel = os.path.relpath(os.path.join(base, fn), root).replace(os.sep, "/")
            if rel not in manifest:
                extra.append("+" + rel)
    return len(manifest) - len(bad), len(manifest), bad + extra


def guess_version(filename):
    m = re.search(r"v?(\d+\.\d+\.\d+(?:[-+][\w.]+)?)", filename or "")
    return m.group(1) if m else None
