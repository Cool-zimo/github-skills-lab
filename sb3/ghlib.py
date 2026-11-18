#!/usr/bin/env python3
"""GitHub REST 薄封装。零第三方依赖，只做本机实测过的那几件事。

账号约定（多账号，不固定）：
  .tokens 每行一个 PAT；行号即账号编号。
  当前账号写在 .active（一行：login 或行号）；没有 .active 时默认第 1 行。
  单次覆盖：--as <login|行号> / `github as <账号> <命令>` / 直呼账号名。
  写操作前解析身份并校验；指定了账号就必须精确匹配，绝不降级到别的行。
"""
import base64
import hashlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.github.com"
VERSION = "1.3.0"
BASE_HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "github-skills/" + VERSION,
}


class GhError(Exception):
    pass


# ---------------------------------------------------------------- 账号

def _token_path(root):
    """GH_TOKENS_FILE 优先；否则从包根向上最多 4 层找 .tokens / .token。"""
    env = os.environ.get("GH_TOKENS_FILE")
    if env and os.path.isfile(env):
        return env
    p = os.path.abspath(root)
    for _ in range(5):
        for name in (".tokens", ".token"):
            path = os.path.join(p, name)
            if os.path.isfile(path):
                return path
        parent = os.path.dirname(p)
        if parent == p:
            break
        p = parent
    return None


def load_token(root, line=1):
    """返回 (token, 来源路径)。值永不打印。"""
    path = _token_path(root)
    if not path:
        raise GhError("找不到 .tokens / .token（向上找了 4 层，也可用 GH_TOKENS_FILE 指定）")
    rows = [r.strip() for r in open(path, encoding="utf-8").read().splitlines() if r.strip()]
    if line == 0 or line > len(rows):
        raise GhError("%s 只有 %d 行，取不到第 %d 行" % (path, len(rows), line))
    return rows[line - 1], path


def token_lines(root):
    """返回 [(行号, token, 来源路径)]，用于账号探测。值永不打印。"""
    path = _token_path(root)
    if not path:
        return []
    rows = [r.strip() for r in open(path, encoding="utf-8").read().splitlines() if r.strip()]
    return [(i + 1, r, path) for i, r in enumerate(rows)]


def read_active(root):
    """读 .active，返回 spec 字符串或 None。"""
    p = os.path.join(root, ".active")
    if os.path.isfile(p):
        v = open(p, encoding="utf-8").read().strip()
        if v:
            return v
    return None


def write_active(root, spec):
    """设当前账号。写的是 login 或行号，不写 token。"""
    p = os.path.join(root, ".active")
    if spec is None:
        if os.path.isfile(p):
            os.remove(p)
    else:
        with open(p, "w", encoding="utf-8") as f:
            f.write(str(spec))
    return p


def probe(token):
    """调 /user，返回 (HTTP状态, 数据)。失效账号不抛异常。"""
    return req("GET", "/user", token)


def accounts(root):
    """探测所有账号：[(行号, login, id, type, scopes, 状态)]。不显示 token。"""
    out = []
    for line, tok, path in token_lines(root):
        st, me = probe(tok)
        if st == 200:
            out.append((line, me.get("login"), me.get("id"), me.get("type"),
                        me.get("scopes", []), "ok"))
        else:
            out.append((line, "-", "-", "-", [], "HTTP %s 失效/无权限" % st))
    return out


def resolve(root, spec=None, allow_anonymous=False):
    """解析出一个账号。返回 dict：token / line / login / id / source / spec。

    spec 为 None → .active → 第 1 行；为 int 或数字串 → 行号；
    为 login 字符串 → 遍历各行精确匹配，找不到直接报错，不降级。
    allow_anonymous=True 且完全找不到 .tokens、也没设 .active 时，
    返回一个只读匿名身份（token=None），供 tree/status/verify 等只读命令用。
    """
    if allow_anonymous and spec is None and read_active(root) is None and _token_path(root) is None:
        return {"token": None, "line": 0, "login": "(anonymous)", "id": None,
                "scopes": [], "source": "(no .tokens)", "spec": "anonymous"}
    if spec is None:
        spec = read_active(root)
    if spec is None:
        spec = 1

    by_login = None
    if isinstance(spec, int) or str(spec).isdigit():
        line = int(spec)
    else:
        by_login = str(spec)
        line = None
        for n, tok, _ in token_lines(root):
            st, me = probe(tok)
            if st == 200 and me.get("login") == by_login:
                line = n
                break
        if line is None:
            known = ", ".join(str(a[1]) for a in accounts(root) if a[5] == "ok") or "(无有效账号)"
            raise GhError("账号 %s 不在 .tokens 里（有效账号：%s）—— 不降级" % (by_login, known))

    tok, path = load_token(root, line)
    st, me = req("GET", "/user", tok)
    if st != 200:
        raise GhError("第 %d 行 /user → HTTP %s %s" % (line, st, me.get("message", "")))
    login = me.get("login")
    if by_login and login != by_login:
        raise GhError("第 %d 行实际是 %s，不是 %s —— 拒绝" % (line, login, by_login))
    expect = os.environ.get("GH_EXPECT_LOGIN")
    if expect and login != expect:
        raise GhError("环境变量 GH_EXPECT_LOGIN=%s，实际 %s —— 拒绝" % (expect, login))
    return {"token": tok, "line": line, "login": login, "id": me.get("id"),
            "scopes": me.get("scopes", []), "source": path, "spec": spec}


def precheck_push(ident, full):
    """写操作前查目标仓库权限。无 push 权限直接拒绝并提示换账号。"""
    st, d = req("GET", "/repos/" + full, ident["token"])
    if st != 200:
        raise GhError("%s 读取 %s → HTTP %s（仓库不存在或该账号无访问权）" %
                      (ident["login"], full, st))
    perm = d.get("permissions") or {}
    if not perm.get("push"):
        raise GhError("%s 对 %s 无 push 权限（admin=%s pull=%s）—— 换账号：github as <账号> ... 或 github use <账号>" %
                      (ident["login"], full, perm.get("admin"), perm.get("pull")))
    return perm


# ---------------------------------------------------------------- HTTP

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
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=60) as f:
            return f.status, json.loads(f.read() or b"{}")
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw or b"{}")
        except ValueError:
            return e.code, {"message": raw.decode("utf-8", "replace")[:300]}
    except Exception as e:
        return -1, {"message": str(e)}


def need(method, path, token, body=None, params=None, what=""):
    st, d = req(method, path, token, body, params)
    if not 200 <= st < 300:
        raise GhError("%s：HTTP %s %s" % (what or path, st, d.get("message", "")))
    return d


def whoami(token):
    return need("GET", "/user", token, what="校验身份")


def rate_limit(token):
    """GET /rate_limit，返回 core 段。匿名也能调，用于 doctor 诊断 403。"""
    st, d = req("GET", "/rate_limit", token)
    if st != 200:
        raise GhError("读取 /rate_limit → HTTP %s %s" % (st, d.get("message", "")))
    return (d.get("resources") or {}).get("core") or {}


def pages_enable(token, full, branch="main", path="/", dry_run=False):
    """POST /repos/{o/r}/pages 开 Pages。409 视为已存在，不算失败。"""
    if dry_run:
        return {"dry_run": True, "source": {"branch": branch, "path": path}}
    st, d = req("POST", "/repos/" + full + "/pages", token,
                body={"source": {"branch": branch, "path": path}})
    if st == 409:
        return {"already_exists": True}
    if not 200 <= st < 300:
        raise GhError("开启 Pages：HTTP %s %s" % (st, d.get("message", "")))
    return d


def zipball(token, full, ref="main"):
    """一次拿整仓 zip。先走 API（自动跟随 302 到 codeload，私有仓带 token），
    失败再直连 codeload。返回 bytes。"""
    r = urllib.parse.quote(ref, safe="")
    url = API + "/repos/%s/zipball/%s" % (full, r)
    headers = dict(BASE_HEADERS)
    if token:
        headers["Authorization"] = "Bearer " + token
    for u in (url, "https://codeload.github.com/%s/zip/refs/heads/%s" % (full, r)):
        try:
            with urllib.request.urlopen(urllib.request.Request(u, headers=headers), timeout=90) as f:
                return f.read()
        except Exception:
            continue
    raise GhError("下载 zipball 失败：%s@%s（API 与 codeload 都试过）" % (full, ref))


def pull_repo_zip(token, full, dest, ref="main"):
    """整仓一次拉取：zipball 落盘 + tree 逐字节校验。返回 (文件数, 字节数, sha表, 校验状态)。

    相比 pull_repo 的「每个 blob 一次 /contents」，这里只有 1 次下载 + 1 次 tree。
    tree 被截断时仍落盘，但明确返回 status='unverified'，绝不给假绿灯。
    """
    import io
    import zipfile
    raw = zipball(token, full, ref)
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        names = [n for n in z.namelist() if not n.endswith("/")]
        if not names:
            raise GhError("zipball 为空：%s@%s" % (full, ref))
        prefix = names[0].split("/")[0] + "/"
        total, n = 0, 0
        for name in names:
            if not name.startswith(prefix) or name == prefix:
                continue
            rel = name[len(prefix):]
            out = os.path.join(dest, rel)
            parent = os.path.dirname(out)
            if parent:
                os.makedirs(parent, exist_ok=True)
            data = z.read(name)
            with open(out, "wb") as f:
                f.write(data)
            total += len(data)
            n += 1
    shas, status = {}, "verified"
    st, d = req("GET", "/repos/%s/git/trees/%s" % (full, urllib.parse.quote(ref, safe="")),
                token, params={"recursive": "1"})
    if st == 200 and not d.get("truncated"):
        shas = {t["path"]: t["sha"] for t in d.get("tree", []) if t["type"] == "blob"}
    else:
        status = "unverified"
    return n, total, shas, status


def repo(token, full):
    return need("GET", "/repos/" + full, token, what="读取仓库")


def tree(token, full, ref="main"):
    d = need("GET", "/repos/%s/git/trees/%s" % (full, urllib.parse.quote(ref, safe="")),
             token, params={"recursive": "1"}, what="读取文件树")
    if d.get("truncated"):
        raise GhError("文件树被截断（truncated=true），不适合做镜像校验")
    return d.get("tree", [])


def contents(token, full, path, ref="main"):
    p = urllib.parse.quote(path, safe="/")
    return need("GET", "/repos/%s/contents/%s" % (full, p), token,
                params={"ref": ref}, what="读取 " + path)


def blob_sha(data):
    """git blob sha —— 与 API tree 的 sha 可直接比对，用于逐字节校验。"""
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\x00" + data).hexdigest()


def pull_repo(token, full, dest, ref="main"):
    """git clone 被 403 的环境用：tree + contents base64 落盘。返回 (文件数, 字节数, sha 表)。"""
    items = [t for t in tree(token, full, ref) if t["type"] == "blob"]
    shas = {}
    total = 0
    for t in items:
        path = t["path"]
        d = contents(token, full, path, ref)
        raw = base64.b64decode(d.get("content", "") + "=" * (-len(d.get("content", "")) % 4))
        out = os.path.join(dest, path)
        parent = os.path.dirname(out)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(out, "wb") as f:
            f.write(raw)
        shas[path] = t["sha"]
        total += len(raw)
    return len(items), total, shas


SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", "node_modules", ".venv"}
SKIP_FILES = {".DS_Store", ".ghproj"}


def is_sync_path(rel):
    parts = rel.split("/")
    last = parts[-1]
    return not (any(p in SKIP_DIRS for p in parts[:-1]) or last in SKIP_FILES
                or last.endswith((".pyc", ".tmp")))


def walk_files(dest):
    """本地工作目录里需要同步的文件（相对路径）。sync 与 verify 共用同一套规则。"""
    out = []
    for base, dirs, files in os.walk(dest):
        dirs[:] = [x for x in dirs if x not in SKIP_DIRS]
        for fn in files:
            rel = os.path.relpath(os.path.join(base, fn), dest).replace(os.sep, "/")
            if is_sync_path(rel):
                out.append(rel)
    return sorted(out)


def verify_mirror(dest, shas, ignore_extra=()):
    """本地文件 git blob sha vs 线上 tree。返回 (通过数, 总数, 失败列表)。

    ignore_extra：合并语义下「线上有、本地没有」的预期保留文件，跳过它们，
    其余文件仍逐个做 blob sha 比对。逐字节校验逻辑本身不变。
    """
    bad = []
    local = set(walk_files(dest))
    shas = {k: v for k, v in shas.items() if is_sync_path(k)}
    ignore_extra = set(ignore_extra)
    for rel in sorted(shas):
        if rel in ignore_extra:
            continue
        p = os.path.join(dest, rel)
        if not os.path.isfile(p):
            bad.append(rel)
            continue
        with open(p, "rb") as fh:
            if blob_sha(fh.read()) != shas[rel]:
                bad.append(rel)
    extra = ["+多出:" + x for x in sorted(local - set(shas)) if x != ".gitkeep"]
    counted = {k: v for k, v in shas.items() if k not in ignore_extra}
    return len(counted) - len(bad), len(counted), bad + extra


def put_file(token, full, path, local_path, message, branch="main"):
    """推单个文件，自动带 sha 避免 409/422。返回 commit sha。"""
    data = open(local_path, "rb").read()
    body = {"message": message, "content": base64.b64encode(data).decode(), "branch": branch}
    p = urllib.parse.quote(path, safe="/")
    st, cur = req("GET", "/repos/%s/contents/%s" % (full, p), token, params={"ref": branch})
    if st == 200:
        body["sha"] = cur["sha"]
    elif st != 404:
        raise GhError("预取 sha 失败：HTTP %s %s" % (st, cur.get("message", "")))
    d = need("PUT", "/repos/%s/contents/%s" % (full, p), token, body=body, what="推送 " + path)
    return d["commit"]["sha"]


def sync_tree(token, full, dest, message, branch="main", dry_run=False, mirror=False):
    """把本地目录推成一次 commit。

    走 Git Data API，不依赖 git clone。未变化的文件直接复用线上 blob sha，
    只对新增/改动文件 POST blob；ref 更新 force=false，基线变了就拒绝。

    v1.3.0：默认改为**合并语义**（POST /git/trees 带 base_tree，线上多出的文件保留）。
    只有 mirror=True 才不带 base_tree = 全量替换 = 删除线上多余文件。
    这是把 v1.2.0 最危险的行为从默认改成显式选项。
    """
    files = walk_files(dest)
    if not files:
        raise GhError("没有可同步的文件：%s" % dest)

    old, old_tree_sha = {}, None
    st, d = req("GET", "/repos/%s/git/trees/%s" % (full, urllib.parse.quote(branch, safe="")),
                token, params={"recursive": "1"})
    if st == 200 and not d.get("truncated"):
        old = {t["path"]: t["sha"] for t in d.get("tree", []) if t["type"] == "blob"}
        old_tree_sha = d.get("sha")
    elif st != 200:
        raise GhError("读取线上 tree 失败：HTTP %s %s" % (st, d.get("message", "")))

    st, ref = req("GET", "/repos/%s/git/ref/heads/%s" % (full, branch), token)
    if st == 200:
        base = ref["object"]["sha"]
    elif st == 404:
        base = None
    else:
        raise GhError("读取 ref 失败：HTTP %s %s" % (st, ref.get("message", "")))

    entries = []
    changed, reused = [], []
    for rel in files:
        data = open(os.path.join(dest, rel.replace("/", os.sep)), "rb").read()
        sha = blob_sha(data)
        if old.get(rel) == sha:
            blob = sha
            reused.append(rel)
        else:
            blob = None if dry_run else need(
                "POST", "/repos/%s/git/blobs" % full, token,
                body={"content": base64.b64encode(data).decode(), "encoding": "base64"},
                what="上传 blob " + rel)["sha"]
            changed.append(rel)
        entries.append({"path": rel, "mode": "100644", "type": "blob", "sha": blob or sha})

    extra = sorted(set(old) - set(files))
    removed = extra if mirror else []
    kept = [] if mirror else extra
    report = {"files": files, "changed": changed, "reused": reused,
              "removed": removed, "kept": kept, "mirror": mirror,
              "base": base, "commit": None, "noop": False}
    if dry_run:
        return report
    if not changed and not removed:
        report["noop"] = True
        return report

    tree_body = {"tree": entries}
    # 合并语义：带 base_tree，未被 entries 覆盖的线上文件由服务端保留。
    # 镜像语义：不带 base_tree = 全量替换 = 删除线上多余文件。
    if not mirror and old_tree_sha:
        tree_body["base_tree"] = old_tree_sha
    tree_sha = need("POST", "/repos/%s/git/trees" % full, token,
                    body=tree_body, what="创建 tree")["sha"]
    commit = need("POST", "/repos/%s/git/commits" % full, token,
                  body={"message": message, "tree": tree_sha,
                        "parents": [base] if base else []}, what="创建 commit")["sha"]
    if base:
        need("PATCH", "/repos/%s/git/refs/heads/%s" % (full, branch), token,
             body={"sha": commit, "force": False}, what="快进 ref")
    else:
        need("POST", "/repos/%s/git/refs" % full, token,
             body={"ref": "refs/heads/" + branch, "sha": commit}, what="创建 ref")
    report["commit"] = commit
    return report


def fast_forward(token, full, branch, sha, expect_base=None):
    """快进分支。force=false；基线不符就拒绝，不覆盖他人提交。"""
    ref = need("GET", "/repos/%s/git/ref/heads/%s" % (full, branch), token, what="读取 ref")
    old = ref["object"]["sha"]
    if expect_base and not old.startswith(expect_base):
        raise GhError("基线已变：%s，期望 %s* —— 停止" % (old, expect_base))
    d = need("PATCH", "/repos/%s/git/refs/heads/%s" % (full, branch), token,
             body={"sha": sha, "force": False}, what="快进")
    return old, d["object"]["sha"]


def compare(token, full, base, head):
    return need("GET", "/repos/%s/compare/%s...%s" % (full, base, head), token, what="比对分支")


def create_repo(token, name, private=False, description="", auto_init=True,
                owner=None, login=None):
    """owner 为空或等于当前 login → POST /user/repos；
    指定组织 → POST /orgs/{owner}/repos（先校验组织可访问）；
    指定的是另一个普通用户名 → 明确报错，不静默建到当前账号名下。"""
    body = {"name": name, "private": private, "description": description,
            "auto_init": auto_init}
    if not owner or (login and owner == login):
        return need("POST", "/user/repos", token, body=body, what="建仓")
    st, org = req("GET", "/orgs/" + owner, token)
    if st != 200:
        raise GhError("不能在 %s 名下建仓：不是可访问的组织（HTTP %s）。"
                      "若是另一个用户，请改用 --as <账号> 切换 token 行。" % (owner, st))
    return need("POST", "/orgs/%s/repos" % owner, token, body=body,
                what="在组织 %s 建仓" % owner)


def pages(token, full):
    return req("GET", "/repos/" + full + "/pages", token)


def latest_build(token, full):
    return req("GET", "/repos/" + full + "/pages/builds/latest", token)


def poll_pages(token, full, tries=8, sleep=8, log=print):
    import time
    last = "unknown"
    for i in range(tries):
        st, d = latest_build(token, full)
        last = d.get("status", "unknown")
        err = (d.get("error") or {}).get("message")
        log("  [%d] build=%s commit=%s err=%s" % (i, last, str(d.get("commit"))[:12], err))
        if last in ("built", "errored"):
            return last
        time.sleep(sleep)
    return last


def pulls(token, full, state="open"):
    return need("GET", "/repos/" + full + "/pulls", token,
                params={"state": state, "per_page": "20"}, what="读取 PR")


def collaborators(token, full):
    return need("GET", "/repos/" + full + "/collaborators", token, what="读取协作者")
