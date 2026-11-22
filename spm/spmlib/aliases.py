"""命令别名。别名展开发生在 CLI 解析之前，所以 `spm gs` 等价于 `spm alias 展开后的命令`。"""
import re

from . import config

SAFE_ALIAS = re.compile(r"^[\w.\-]{1,48}$")


class AliasError(Exception):
    pass


def add(cfg, alias, target):
    if not SAFE_ALIAS.match(alias or ""):
        raise AliasError("别名不合法（字母数字 . _ -，≤48）：%r" % alias)
    if not target.strip():
        raise AliasError("别名目标不能为空")
    cfg.setdefault("aliases", {})[alias] = target.strip()
    config.save(cfg)
    return cfg["aliases"][alias]


def remove(cfg, alias):
    if alias not in (cfg.get("aliases") or {}):
        raise AliasError("没有别名：%s" % alias)
    del cfg["aliases"][alias]
    config.save(cfg)


def resolve(cfg, alias, args):
    """返回展开后的 argv 列表；没命中返回 None。"""
    target = (cfg.get("aliases") or {}).get(alias)
    if not target:
        return None
    import shlex
    return shlex.split(target) + list(args)


def list_all(cfg):
    return sorted((cfg.get("aliases") or {}).items())
