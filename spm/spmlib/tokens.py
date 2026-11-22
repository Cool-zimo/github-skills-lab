"""token 文件同步。

默认 token 源就是 skill 包的 `.tokens`（与 github-skills 共用同一份）。
同步时把内容原样复制到每个版本的 `.spm/token`，全程不打印、不记录 token 值，
状态只报「是否存在 / 行数 / sha256 前 12 位 / mtime」。
"""
import hashlib
import os
import time

from . import _gh as G
from . import config, versions


class TokenError(Exception):
    pass


def find_token(cfg):
    p = cfg.get("token_file")
    if p and os.path.isfile(p):
        return p
    # 兜底：沿用 github-skills 的向上查找
    p = G.token_path(config.PKG_ROOT)
    if p:
        return p
    raise TokenError("找不到 token 文件：%s（用 spm token set <路径> 指定）" % cfg.get("token_file"))


def digest(data):
    return hashlib.sha256(data).hexdigest()[:12]


def _write_quiet(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass  # 某些挂载会忽略 chmod，不影响同步本身


def sync(cfg=None, h=None, names=None):
    """把 token 文件同步到各版本 .spm/token。返回 [(name@ver, 是否新建), ...]。"""
    cfg = cfg or config.load(h)
    src = find_token(cfg)
    with open(src, "rb") as f:
        data = f.read()
    target_rel = cfg.get("token_sync_target") or ".spm/token"
    out = []
    h = h or config.home()
    if not os.path.isdir(h):
        return out
    all_names = names or [d for d in sorted(os.listdir(h))
                          if os.path.isdir(os.path.join(h, d))]
    for name in all_names:
        for v in versions.versions(name, h):
            p = os.path.join(versions.root(name, v, h), target_rel)
            config.assert_inside(versions.root(name, v, h), p, "token 目标")
            if os.path.isfile(p):
                with open(p, "rb") as f:
                    existed = f.read() == data
            else:
                existed = False
            _write_quiet(p, data)
            out.append(("%s@%s" % (name, v), not existed))
    return out


def status(cfg=None, h=None):
    """只看指纹，不回显值。"""
    cfg = cfg or config.load(h)
    try:
        src = find_token(cfg)
        with open(src, "rb") as f:
            data = f.read()
        lines = len([x for x in data.decode("utf-8", "replace").splitlines() if x.strip()])
        base = {"source": src, "exists": True, "lines": lines,
                "sha12": digest(data), "bytes": len(data),
                "mtime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(os.path.getmtime(src)))}
    except TokenError as e:
        base = {"source": cfg.get("token_file"), "exists": False, "error": str(e)}
    targets = []
    h = h or config.home()
    if os.path.isdir(h):
        for name in sorted(os.listdir(h)):
            if not os.path.isdir(os.path.join(h, name)):
                continue
            for v in versions.versions(name, h):
                p = os.path.join(versions.root(name, v, h),
                                 cfg.get("token_sync_target") or ".spm/token")
                if os.path.isfile(p):
                    with open(p, "rb") as f:
                        d = f.read()
                    same = (d == data) if base.get("exists") else None
                    targets.append({"name": "%s@%s" % (name, v),
                                    "sha12": digest(d), "same": same})
                else:
                    targets.append({"name": "%s@%s" % (name, v), "missing": True})
    return {"source": base, "targets": targets}
