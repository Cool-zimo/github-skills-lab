# github-skills v1.3.1

> 合并 lab 的 PR #1 / #2 之后发的修正版。只修真 bug + 补一个命令，不改任何既有行为。
> `python3 -W error::ResourceWarning -m unittest discover -s tests` → **61 项全绿**，离线、零 token、零告警。

## 修了什么

### 1. `pull` 逐文件路径把大文件写成 0 字节

`/repos/{o/r}/contents/{path}` 对 **>1 MB** 文件返回 `encoding: "none"` + `content: ""`，只给 `sha` / `git_url`。
v1.3.0 的 `pull_repo()` 直接 `b64decode("")`，于是静默落一个空文件。

lab PR #2 的 `downloads/sb3-tools.v1.0.0.zip` 正好 5,087,362 B，实测复现：
`pull` 报 `27/28 ❌`（`verify` 用 git blob sha 挡住了假绿灯，没骗人）。

现在：`encoding != base64` 且 `size > 0` → 改走 `GET /git/blobs/{sha}`，取回后**用 `blob_sha()` 对 tree 的 sha 复核**才落盘。

### 2. 同一个坑在 `spm install --file` 里独立复现

causepotato 在 PR #2 下 11-18 报过：`spmlib/sources.py` 的 `github_raw()` 装大二进制包输出「下载 0 字节 / 已装 1 文件 / 0 字节」，静默装空包。

现在同样改走 blob API，并加两道硬失败：
- 声明 `size > 0` 却没有 `sha` → 报错
- 取回长度与 `size` 不符 / 取回 0 字节 → 报错，**绝不静默**

### 3. 自己引入又自己修掉的两个回归

- 0 字节文件（`.gitkeep`、`__init__.py`）被大文件分支误吞 → 加 `size == 0` 短路
- 严格模式 `-W error::ResourceWarning` 下 3 处 `open(...).read()` 未关句柄 → 改 `with`

### 4. 新命令：`github pr <repo> --merge N`

之前合并 PR 只能手写 API，一条龙断在最后一节。现在：

```bash
github pr Cool-zimo/github-skills-lab --state all          # 列
github pr Cool-zimo/github-skills-lab --merge 1 --dry-run  # 只看不动
github pr Cool-zimo/github-skills-lab --merge 1 -m "merge: ..."
```

写前查身份 / push 权限 / PR 是否 open / `mergeable is True` / `--method merge|squash|rebase`。
**`mergeable=None` 会拦下**——合完 #1 后 GitHub 重算 #2 时真实遇到过，放过去就是 405。

本版两个 PR 就是用这个命令合的：#1 → `06a29c11af5c`，#2 → `916b52890413`。

## 合并顺序（重要）

`sb3/github-sb3.patch` 的基线是 **v1.3.0 的 `github`**，打到 v1.2.0 是 `2/4 hunks FAILED`。
所以先合 #1（v1.3.0 + spm），再合 #2（只新增 `sb3/` 与一个新 zip，零文件冲突）。
合完 main 48 文件 / 5,493,619 B，原有 4 个文件 sha 未变。

## 兼容性

- 行为变更：无。`sync` 默认仍是合并语义，`--mirror` 才删；`--dry-run` 清单、blob sha 逐字节校验、`precheck_push()` 全部保留。
- `pr --state` 旧用法不变，`--merge` 是可选参数。
- 仍是零第三方依赖、Python 3.8+、MIT。

## 验证点

```
61/61 离线回归（49 旧 + 12 新，-W error::ResourceWarning）
pull #1 分支  24/24 ✅（含 0 字节 .gitkeep）
pull #2 分支  28/28 ✅（含 5,087,362 B zip）
patch --dry-run 打到 v1.3.0 GitHub  4/4 hunks 通过
pr --merge --dry-run  两个 PR 均 clean，零写入
main  tree  48 文件，两个 PR = closed/merged
```

## 下载

```
https://raw.githubusercontent.com/Cool-zimo/github-skills-lab/main/downloads/github-skills.v.1.3.1.zip
```
