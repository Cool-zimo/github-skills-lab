"""极简 GitHub 客户端（自包含，零第三方依赖）。

spm 可以单独解压使用，不依赖 github-skills 的 ghlib.py；
但默认仍与它共用同一份 .tokens / .token 文件（向上 4 层查找）。
"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.github.com"
BASE_HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "skillpm/1.0",
}


def req(method, path, token, body=None, params=None):
    url = API + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    headers = dict(BASE_HEADERS)
    if token:
        headers["Authorization"] = "Bearer " + token
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    r = urllib.request.Request(url, headers=headers, data=data, method=method)
    try:
        with urllib.request.urlopen(r, timeout=60) as f:
            raw = f.read()
            return f.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw) if raw else {}
        except ValueError:
            return e.code, {"message": raw.decode("utf-8", "replace")[:200]}


def zipball(token, full, ref="main"):
    r = urllib.parse.quote(ref, safe="")
    headers = dict(BASE_HEADERS)
    if token:
        headers["Authorization"] = "Bearer " + token
    urls = [API + "/repos/%s/zipball/%s" % (full, r),
            "https://codeload.github.com/%s/zip/refs/heads/%s" % (full, r)]
    last = None
    for u in urls:
        try:
            with urllib.request.urlopen(
                    urllib.request.Request(u, headers=headers), timeout=90) as f:
                return f.read()
        except Exception as e:
            last = e
    raise RuntimeError("下载 zipball 失败 %s@%s：%s" % (full, ref, last))


def token_path(root):
    """向上找 4 层：.tokens / .token，与 github-skills 的查找规则一致。"""
    p = os.path.abspath(root)
    for _ in range(5):
        for name in (".tokens", ".token"):
            f = os.path.join(p, name)
            if os.path.isfile(f):
                return f
        parent = os.path.dirname(p)
        if parent == p:
            break
        p = parent
    env = os.environ.get("GH_TOKENS_FILE") or os.environ.get("SPM_TOKEN_FILE")
    return env if env and os.path.isfile(env) else None


def load_token(root):
    p = token_path(root)
    if not p:
        return None
    lines = [x.strip() for x in open(p, encoding="utf-8").read().splitlines() if x.strip()]
    return lines[0] if lines else None
