"""配置与路径。零第三方依赖。

spm 默认把版本装到 **skill 包自己的 skills/ 目录**里（"默认装到 skill 上"）：
    <pkg_root>/skills/<name>/<version>/
可用 SPM_HOME 环境变量改到别处。
"""
import json
import os
import tempfile

PKG_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_HOME = os.path.join(PKG_ROOT, "skills")
DEFAULT_TOKEN_FILE = os.path.join(os.path.dirname(PKG_ROOT), ".tokens")

DEFAULT_CONFIG = {
    "version": 1,
    "safe_mode": True,
    "default_source": "lab",
    "token_file": DEFAULT_TOKEN_FILE,
    "token_sync_target": ".spm/token",
    "sources": {
        # 默认源：演示仓里托管的工具包 zip，开箱即可装 1.2.0 / 1.3.0 两个版本
        "lab": {
            "type": "github",
            "repo": "Cool-zimo/github-skills-lab",
            "ref": "main",
            "path": "downloads",
            "pattern": "github-skills.v.*.zip",
        }
    },
    "aliases": {},
    "scripts": {},
}


def home():
    return os.path.abspath(os.environ.get("SPM_HOME") or DEFAULT_HOME)


def config_path(h=None):
    return os.path.join(h or home(), "config.json")


def load(h=None):
    h = h or home()
    os.makedirs(h, exist_ok=True)
    p = config_path(h)
    if not os.path.isfile(p):
        cfg = json.loads(json.dumps(DEFAULT_CONFIG))
        save(cfg, h)
        cfg["_home"] = h
        return cfg
    with open(p, encoding="utf-8") as f:
        cfg = json.load(f)
    # 补齐新增字段，老配置也能用
    changed = False
    for k, v in DEFAULT_CONFIG.items():
        if k not in cfg:
            cfg[k] = json.loads(json.dumps(v))
            changed = True
    if changed:
        save(cfg, h)
    # 记住这份配置来自哪个 home，save() 不带 h 时写回原处，避免跨 home 污染
    cfg["_home"] = h
    return cfg


def save(cfg, h=None):
    h = h or cfg.get("_home") or home()
    os.makedirs(h, exist_ok=True)
    p = config_path(h)
    data = {k: v for k, v in cfg.items() if not k.startswith("_")}
    fd, tmp = tempfile.mkstemp(dir=h, prefix=".config.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp, p)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def inside(root, path):
    """安全模式的核心：任何路径都必须落在 root 内（含符号链接解析后）。"""
    root = os.path.realpath(root)
    path = os.path.realpath(path)
    return os.path.commonpath([root, path]) == root


def assert_inside(root, path, what="路径"):
    if not inside(root, path):
        raise PermissionError("安全模式：%s 越界 → %s（允许根：%s）" % (what, path, root))
    return path


def safe_on(cfg):
    return bool(cfg.get("safe_mode", True))
