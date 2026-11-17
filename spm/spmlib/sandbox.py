"""隔离执行：虚拟文件系统 + 命令白名单 + 自定义脚本。

VFS 视图 = 版本根（只读） ∪ .spm/sandbox（可写，copy-on-write）
    - 读：先 sandbox，再版本根
    - 写：只落 sandbox，绝不污染版本根
    - resolve() 拒绝任何越出这两个根的路径
    - exec 时 cwd 锁进 sandbox，并注入 SPM_* 环境变量
"""
import os
import shlex
import subprocess

from . import config, versions

SHELL_META = set(";|&$><`\n\r")


class SandboxError(Exception):
    pass


class VirtualFS(object):
    def __init__(self, name, version, h=None):
        self.name, self.version = name, version
        self.h = h
        self.read_root = os.path.realpath(versions.root(name, version, h))
        self.write_root = os.path.realpath(
            os.path.join(versions.meta_dir(name, version, h), "sandbox"))
        os.makedirs(self.write_root, exist_ok=True)

    def resolve(self, vpath, for_write=False):
        """虚拟路径 → 物理路径。越界一律拒绝。"""
        if os.path.isabs(vpath):
            raise SandboxError("VFS 只接受相对路径：%s" % vpath)
        rel = os.path.normpath(vpath.replace("\\", "/"))
        if rel in (".", "") or rel.startswith("..") or os.path.isabs(rel):
            raise SandboxError("VFS 路径越界：%s" % vpath)
        candidate = os.path.realpath(os.path.join(self.write_root, rel))
        if os.path.commonpath([self.write_root, candidate]) != self.write_root:
            raise SandboxError("VFS 路径越界：%s" % vpath)
        if for_write:
            return candidate
        # 读：写层优先，其次版本根
        if os.path.isfile(candidate):
            return candidate
        ro = os.path.realpath(os.path.join(self.read_root, rel))
        if os.path.commonpath([self.read_root, ro]) != self.read_root:
            raise SandboxError("VFS 路径越界：%s" % vpath)
        return ro

    def read(self, vpath):
        p = self.resolve(vpath)
        with open(p, "rb") as f:
            return f.read()

    def write(self, vpath, data):
        p = self.resolve(vpath, for_write=True)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(data)
        return p

    def ls(self, vpath="."):
        out = set()
        for base in (self.read_root, self.write_root):
            p = os.path.realpath(os.path.join(base, vpath))
            if os.path.commonpath([base, p]) != base or not os.path.isdir(p):
                continue
            for root, dirs, files in os.walk(p):
                dirs[:] = [d for d in dirs if d != ".spm"]
                for fn in files:
                    out.add(os.path.relpath(os.path.join(root, fn), base).replace(os.sep, "/"))
        return sorted(out)

    def env(self):
        return {
            "SPM_HOME": config.home(),
            "SPM_NAME": self.name,
            "SPM_VERSION": self.version,
            "SPM_VFS_ROOT": self.write_root,
            "SPM_READ_ROOT": self.read_root,
            "SPM_VFS": "1",
        }


def parse_command(line):
    """拆命令；拒绝 shell 元字符与空命令。返回 (argv, 命令名)。"""
    if any(c in SHELL_META for c in line):
        raise SandboxError("命令含 shell 元字符，拒绝执行：%s" % line)
    argv = shlex.split(line)
    if not argv:
        raise SandboxError("空命令")
    return argv, os.path.basename(argv[0])


def check_policy(meta, line, cfg):
    """白名单门禁：safe_mode 下 untrusted 版本必须命中 allow_commands。"""
    argv, cmd = parse_command(line)
    whitelist = set(meta.get("allow_commands") or [])
    trusted = bool(meta.get("trusted"))
    if config.safe_on(cfg) and not trusted and cmd not in whitelist:
        raise SandboxError(
            "命令 %r 不在 %s@%s 的白名单里（安全模式 + 未信任）。"
            "用 spm allow %s@%s %s，或 spm trust %s@%s" %
            (cmd, meta.get("name"), meta.get("version"),
             meta.get("name"), meta.get("version"), cmd,
             meta.get("name"), meta.get("version")))
    return argv, cmd


def _looks_like_path(a):
    return ("/" in a) or bool(os.path.splitext(a)[1])


def rewrite_argv(argv, vfs):
    """VFS 模式下把命令里的相对文件名改写成可访问的物理路径。

    只读层的文件能被 python3 之类读到，但 cwd 仍锁在写层 sandbox，
    所以「读得到版本文件、写只落 sandbox」两件事同时成立。
    """
    if not vfs:
        return argv
    out = []
    for a in argv:
        if a.startswith("-"):
            out.append(a)
            continue
        try:
            p = vfs.resolve(a)
        except SandboxError:
            # 普通字符串参数（如 python3 -c "print(1)"）不该被当成路径，
            # 但长得像路径却越界的参数必须拒绝。
            if _looks_like_path(a):
                raise SandboxError("命令参数不是安全的 VFS 路径：%s" % a)
            out.append(a)
            continue
        out.append(p if os.path.isfile(p) else a)
    return out


def build_cmd(meta, line, vfs=None):
    """脚本里的 {spm}/{python}/{root} 占位符展开。"""
    return (line.replace("{python}", "python3")
                .replace("{root}", vfs.read_root if vfs else "")
                .replace("{sandbox}", vfs.write_root if vfs else ""))


def run(name, version, line, h=None, timeout=60, extra_env=None):
    """在版本隔离环境里跑一条命令。返回 (rc, stdout, stderr)。"""
    cfg = config.load(h)
    v = versions.resolve(name, version, h)
    meta = versions.read_meta(name, v, h)
    vfs = VirtualFS(name, v, h) if meta.get("vfs", True) else None
    expanded = build_cmd(meta, line, vfs)
    argv, cmd = check_policy(meta, expanded, cfg)
    argv = rewrite_argv(argv, vfs)
    env = dict(os.environ)
    # 关键：别让 python 在只读的版本根里写 __pycache__/*.pyc，
    # 否则 VFS 的「写只落 sandbox」会被解释器自己破坏。
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.update(vfs.env() if vfs else {
        "SPM_HOME": config.home(), "SPM_NAME": name, "SPM_VERSION": v, "SPM_VFS": "0"})
    if extra_env:
        env.update(extra_env)
    cwd = vfs.write_root if vfs else versions.root(name, v, h)
    p = subprocess.run(argv, cwd=cwd, env=env, shell=False,
                       capture_output=True, text=True, timeout=timeout)
    return p.returncode, p.stdout, p.stderr


def script_line(cfg, meta, key):
    """自定义脚本：版本内 scripts > 全局 scripts。"""
    key = key or "default"
    line = (meta.get("scripts") or {}).get(key) or (cfg.get("scripts") or {}).get(key)
    if not line:
        raise SandboxError("没有脚本 %r（用 spm script add %s %r ... 定义）" % (key, key, "CMD"))
    return line


def run_script(name, version, key, args=None, h=None, timeout=60):
    cfg = config.load(h)
    v = versions.resolve(name, version, h)
    meta = versions.read_meta(name, v, h)
    line = script_line(cfg, meta, key)
    if args:
        line += " " + " ".join(shlex.quote(a) for a in args)
    return run(name, v, line, h=h, timeout=timeout)
