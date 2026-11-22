"""下载源解析。

支持四种源：
    github:owner/repo[@ref][:path]        仓库里的文件/目录（走 GitHub API）
    url:https://example.com/pkg.zip       任意直链（可带 #sha256=...）
    path:/local/dir 或 /local/pkg.zip    本地目录 / 包
    pr:owner/repo#N                      PR 的 head 分支（自动换源）
以及 install --pr N --from <源>。
"""
import os
import re
import urllib.parse

from . import _gh as G


class SourceError(Exception):
    pass


def parse(spec):
    """把一行 spec 解析成 dict；不联网。"""
    spec = spec.strip()
    if spec.startswith("pr:"):
        m = re.match(r"^pr:([^#]+)#(\d+)(?::(.*))?$", spec)
        if not m:
            raise SourceError("PR 源格式：pr:owner/repo#123[:子目录]")
        return {"type": "pr", "repo": m.group(1), "number": int(m.group(2)),
                "path": (m.group(3) or "").strip("/")}
    if spec.startswith("url:"):
        raw = spec[4:]
        url, _, frag = raw.partition("#")
        sha = None
        if frag.startswith("sha256="):
            sha = frag[7:]
        if not url.startswith(("http://", "https://")):
            raise SourceError("url 源必须是 http(s) 直链")
        return {"type": "url", "url": url, "sha256": sha}
    if spec.startswith("path:") or os.path.isabs(spec) or os.path.exists(spec):
        p = spec[5:] if spec.startswith("path:") else spec
        return {"type": "path", "path": os.path.abspath(p)}
    if spec.startswith("github:"):
        rest = spec[7:]
    elif re.match(r"^[\w.\-]+/[\w.\-]+", spec):
        rest = spec
    else:
        raise SourceError("无法识别的源：%s" % spec)
    # owner/repo[@ref][:path]
    m = re.match(r"^([\w.\-]+/[\w.\-]+)(?:@([^:]+))?(?::(.*))?$", rest)
    if not m:
        raise SourceError("github 源格式：github:owner/repo[@ref][:path]")
    return {"type": "github", "repo": m.group(1), "ref": m.group(2) or "main",
            "path": (m.group(3) or "").strip("/")}


def describe(src):
    t = src.get("type")
    if t == "github":
        return "github:%s@%s/%s" % (src["repo"], src["ref"], src.get("path") or "")
    if t == "url":
        return "url:%s" % src["url"]
    if t == "path":
        return "path:%s" % src["path"]
    if t == "pr":
        return "pr:%s#%s" % (src["repo"], src["number"])
    return "?"


def resolve_pr(src, token):
    """pr: → 换成 github:head_repo@head_ref，保留 path。不写盘。"""
    number = src["number"]
    st, d = G.req("GET", "/repos/%s/pulls/%d" % (src["repo"], number), token)
    if st != 200:
        raise SourceError("读 PR #%d → HTTP %s %s" % (number, st, d.get("message", "")))
    head = d.get("head") or {}
    repo = (head.get("repo") or {}).get("full_name")
    ref = head.get("ref")
    if not repo or not ref:
        raise SourceError("PR #%d 的 head 仓库/分支不可用（可能已删 fork）" % number)
    out = {"type": "github", "repo": repo, "ref": ref,
           "path": src.get("path", ""), "pr": number,
           "pr_head_sha": head.get("sha")}
    return out


def get_source(cfg, name=None, spec=None, token=None):
    """取源：显式 spec > 命名源 > 默认源。pr 源会自动解析成 github 源。"""
    if spec:
        src = parse(spec)
    else:
        name = name or cfg.get("default_source")
        raw = (cfg.get("sources") or {}).get(name)
        if not raw:
            raise SourceError("没有名为 %r 的源（用 spm source list 看）" % name)
        src = dict(raw)
        src["_name"] = name
    if src.get("type") == "pr":
        src = resolve_pr(src, token)
    return src


def list_github_files(src, token):
    """列出 github 源 path 下的可下载文件（用于版本探测 / 选包）。"""
    st, d = G.req("GET", "/repos/%s/contents/%s" % (
        src["repo"], urllib.parse.quote(src.get("path") or "", safe="/")),
        token, params={"ref": src["ref"]})
    if st != 200 or not isinstance(d, list):
        raise SourceError("列目录 → HTTP %s %s" % (st, d.get("message", "")))
    return [{"name": x["name"], "path": x["path"], "sha": x.get("sha"),
             "size": x.get("size", 0), "download_url": x.get("download_url")}
            for x in d if x.get("type") == "file"]


def github_raw(src, rel, token):
    """读 github 源里的单个文件（raw）。"""
    full = "/".join(x for x in (src.get("path") or "", rel) if x)
    st, d = G.req("GET", "/repos/%s/contents/%s" % (
        src["repo"], urllib.parse.quote(full, safe="/")),
        token, params={"ref": src["ref"]})
    if st != 200:
        raise SourceError("下载 %s → HTTP %s %s" % (full, st, d.get("message", "")))
    import base64
    return base64.b64decode(d.get("content") or "")
