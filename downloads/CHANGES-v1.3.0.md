# github-skills v1.3.0 · PR 改动说明

> 来源：一次完整实测（建仓 → 写页面 → sync → verify → 开 Pages，以及抓 6 个文档仓的 50 篇 md）后整理的 6 条优化意见。
> 本 PR **只新增 2 个文件、修改 1 个文件**：`downloads/github-skills.v.1.3.0.zip`（新）、
> `downloads/CHANGES-v1.3.0.md`（本文件）、`README.md`（更新）。
> `dedupe.py` / `test_dedupe.py` / `downloads/github-skills.v.1.2.0.zip` **一个字节都没删改** ——
> 推送时本地故意不放这三个文件，靠 v1.3.0 的默认合并语义由线上原样保留，正好验证优化点 2。

---

# github-skills v1.3.0

> 基于一次完整实测：「建仓 → 写页面 → sync → verify → 开 Pages」+ 抓 6 个文档仓库的 50 篇 md。
> 逐条对应实测反馈的 6 条优化意见，每条都有离线回归测试复现 v1.2.0 的问题。
> `python3 -m unittest discover -s tests -v` → **24 项全绿**，全部离线、不需要 token。
>
> 真机端到端：`github pull Cool-zimo/COOL-DOC --zip` 一次拉 134 文件 / 783,514 字节，逐字节 **134/134 ✅**（v1.2.0 逐文件方式在同一批 50 篇 md 上连续两次 502）；`github doctor` 打印 `4947 / 5000`；匿名模式下 doctor 显示 `0 / 60`，正好复现「撞 403 限流却看不出来」的场景。

## 改动清单

### 1. 补齐开 Pages，一条龙不再断在最后一步

- `ghlib.py` 新增 `pages_enable()`：`POST /repos/{o/r}/pages`，409 视为已存在。
- CLI 新增 `github pages [o/r] [--enable] [--wait] [--dry-run]`：查状态 / 开 Pages / 等构建。
- `github new repo <名> --pages`：建仓 + 拉取 + 开 Pages + 轮询构建一步到位。
- `SKILL.md` 标准工作流第 8 步改为 `github pages --enable --wait`。

验证点：`test_17`（dry-run 零写入、POST /pages 路径正确）；真实跑过一次 `pages_enable` 返回 201 并轮询到 `built`。

### 2. `sync` 默认从「镜像」改成「合并」（最重要）

- `sync_tree()` 新增 `mirror=False`。默认 `POST /git/trees` 带 `base_tree`，线上多出的文件由服务端保留。
- 只有 `--mirror` 才不带 `base_tree`（全量替换，会删线上多余文件）；dry-run 用 `⚠️` 显式列出将删除清单。
- 报告新增 `kept` 字段；noop 判定相应调整。
- 末尾自动校验通过 `ignore_extra=set(kept)` 跳过预期保留文件，**其余文件仍逐个算 git blob sha**，不假红也不放宽。
- `verify` 默认容忍线上多出文件，`--strict` 才严格比对。

验证点：`test_04/05` 复现「本地只放 index.html、线上有 README」→ 默认 `removed=[]`、`kept=['README.md']`、tree body 含 `base_tree`；`test_06` 确认 `--mirror` 仍可删且不带 `base_tree`；`test_08/09/10` 确认白名单不会掩盖真实不一致。

### 3. `pull --zip`：大仓一次拉全

- `ghlib.py` 新增 `zipball()` / `pull_repo_zip()`：API zipball（自动跟随 302 到 codeload，私有仓带 token），失败回退 codeload 直连。
- 落盘后仍拉一次 tree 做逐字节校验；`truncated=true` 时文件照常落盘但状态明确为 `unverified`，绝不给假绿灯。
- `github pull --zip` / `github clone --zip`。

验证点：`test_11` 断言除 zipball 外只调 1 次 API、无 `/contents/` 调用、3/3 逐字节一致；`test_12` 断言截断时返回 `unverified` 且 shas 为空。

### 4. 匿名只读 + 限流可见

- `req()`：token 为空时不加 `Authorization`。
- `resolve(..., allow_anonymous=True)`：找不到 `.tokens` 且无 `.active` 时返回只读身份。
- `tree / status / verify / pr / collab / pages / doctor / pull / clone` 允许匿名；写命令由 `guard()` 明确拒绝。
- `doctor` 新增 `/rate_limit` 输出（remaining / limit / reset）。
- `ghlib.py` 新增 `rate_limit()`。

验证点：`test_13/14/15/16`：匿名解析、请求头无 Authorization、匿名可读配额、guard 拒绝写。

### 5. `new --owner / --pages`

- `create_repo(..., owner, login)`：命中当前 login 走 `/user/repos`，命中组织走 `/orgs/{org}/repos` 并先校验，别的普通用户名明确报错并提示 `--as`。
- 目标仓库名用 `★ 将建仓 ... ★` 醒目标出。

验证点：`test_18/19`：组织端点正确、当前账号仍用 `/user/repos`、外来用户名报错含 `--as`。

### 6. 每天多敲的那几下

| 项 | 现在 |
|---|---|
| `guide` 写死 4 个 choices | `github guide --list` + `guides/` 下任意相对路径，带 `os.path.commonpath` 越界防护 |
| `status` 在包根报「没给仓库名」 | `projects/` 下恰好一个带 `.ghproj` 的项目时自动选中 |
| 默认分支一律 `main` | `.ghproj` 改存一行 JSON（`repo` / `branch` / `commit`），兼容 v1.2.0 纯文本；`--ref` / `--branch` 优先读它 |
| `new` 拿到的 `default_branch` 只用一次 | 写入 `.ghproj`，后续 `sync` / `verify` / `push` / `ff` 都跟着走 |
| `sync` 显式 `--repo` 时写两次 `.ghproj` | 分支先算好，第一次写就带 branch，成功后补 commit |

验证点：`test_20/21/22/23`：任意路径与 `--list`、路径穿越被拒、JSON 与旧纯文本双向兼容、分支优先级。

## 明确没动（保守设计，本轮全用上了）

- `--dry-run` 的 `~改动 / -将删除 / 复用` 清单
- git blob sha 逐字节校验（`sha1("blob "+len+"\0"+bytes)`）
- 未变文件复用线上 blob sha、noop 不产生空提交
- `force=false` 纯快进、写前 `precheck_push()` 权限校验
- `SKIP_DIRS` 让 `sync` 与 `verify` 共用同一套排除规则

`test_02/03/07` 专门锁住这几条：blob_sha 用独立公式复算、排除规则不变、无改动仍不产生提交。

## 兼容性

- **行为变更**：`sync` 默认不再删除线上文件。需要旧镜像行为请显式 `--mirror`。
- 其余命令、参数、输出格式向后兼容；v1.2.0 的 `.ghproj` 纯文本仍可读。
- 仍是零第三方依赖、Python 3.8+、MIT。

## 文件变化

```
CHANGELOG.md            新增
tests/test_v130.py      新增（24 项离线回归）
ghlib.py                新增 5 个函数 / 改 3 个函数
github                  新增 1 个子命令 / 改 12 处
SKILL.md README.md AGENTS.md guides/*.md   同步更新
```
