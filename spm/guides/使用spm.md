# 使用 spm · GitHub skill 包管理器

> 零第三方依赖、Python 3.8+。`spm` 是独立包管理器（不再随任何包分发），拷走 `spm` + `spmlib/` 就能用，
> **不需要 github-skills 也能跑**（`spmlib/_gh.py` 自带极简 GitHub 客户端）。

## 0. 默认装到 skill 上

```
github-skills/
├── github                  ← v1.3.0 CLI
├── ghlib.py
├── spm                     ← 包管理器（本文件的主角）
├── spmlib/                 ← 包管理器的库
├── skills/                 ← ★ SPM_HOME：版本默认装在这里
│   └── <name>/<version>/   ← 一版本一目录
└── guides/使用spm.md
```

`SPM_HOME` 环境变量可改到别处；不写就是包内 `skills/`。默认源 `official` 指向 `Cool-zimo/spm-packages@main:packages`。
源不写 `pattern` 时按**包名前缀**挑文件，所以一个目录能同时放 `github-skills` 和 `sb3` 两个包。

```bash
python3 spm doctor                 # 自检：SPM_HOME / 安全模式 / token / 已装版本
python3 spm install github-skills@1.2.0
python3 spm install github-skills@1.3.0 --from pr:Cool-zimo/spm-packages#1:packages
python3 spm list
```

---

## 1. 下载源

```bash
spm source list
spm source add lab github:Cool-zimo/spm-packages@main:packages --default
spm source add fork github:me/my-fork@dev:packages
spm source add mirror url:https://example.com/github-skills.v.1.3.0.zip#sha256=abcd...
spm source add local path:/home/me/my-skill
spm source add review pr:Cool-zimo/spm-packages#1:packages
spm source show review
spm source rm mirror
```

四种源：

| 前缀 | 含义 |
|---|---|
| `github:owner/repo[@ref][:path]` | 仓库内文件 / 整仓 zipball |
| `url:https://...#sha256=...` | 任意直链，可带 sha256 校验 |
| `path:/dir` 或 `path:/pkg.zip` | 本地目录 / 本地包 |
| `pr:owner/repo#N[:path]` | **PR 的 head 仓库 + 分支**，自动解析，fork 删了会明确报错 |

`install --pr N` 也可以临时把任意源换成 PR head：

```bash
spm install my-skill@review --from github:Cool-zimo/spm-packages@main:packages --pr 1
```

---

## 2. 多版本并存

```bash
spm install github-skills@1.2.0 --trust --allow python3 --script "check=python3 github --help"
spm install github-skills@1.3.0 --from github:Cool-zimo/spm-packages@main:packages
spm list                       # * 标当前版本
spm use github-skills@1.2.0    # 切当前版本
spm dir github-skills@1.3.0    # 打印版本目录（给脚本用）
spm show github-skills@1.3.0   # 元数据：源 / 信任 / VFS / 白名单 / scripts / manifest
spm verify github-skills@1.2.0 # 逐文件 sha256，改过一个字节就报红
spm uninstall github-skills@1.2.0
```

- 一版本一目录，**版本之间不共享任何文件**；卸载当前版本会自动切到剩下的最新版本
- 已存在的版本拒绝重复安装（不会悄悄覆盖）
- 解包防 zip-slip：绝对路径 / `..` / 符号链接一律拒绝；GitHub zipball 自动剥掉那层 `owner-repo-sha/`
- 落盘后写 manifest（每个文件 sha256 + size），随时 `verify`

---

## 3. 限制目录、命令，隔离版本

### 安全模式

```bash
spm safe on      # 默认开：所有写入都必须落在 SPM_HOME 内
spm safe off     # 仅本地调试用
```

安全模式下 `assert_inside()` 用 `realpath + commonpath` 判界，连符号链接绕出去也拦得住。

### 信任版本

```bash
spm trust github-skills@1.2.0
spm untrust github-skills@1.2.0
```

默认**不信任**。安全模式 + 未信任 = 只能跑白名单里的命令。信任后白名单不再拦，但**shell 元字符永远拒绝**（`;` `|` `&` `$` `>` `` ` `` 换行），且永远 `subprocess.run(shell=False)`。

### 能执行的命令

```bash
spm allow github-skills@1.2.0 python3 node          # 追加
spm allow github-skills@1.2.0 python3 --replace     # 替换
spm allow github-skills@1.2.0 --clear               # 全禁
```

白名单按命令名精确匹配（`os.path.basename`）。版本元数据里单独存 `allow_commands`，各版本互不影响。

### 版本隔离

每个版本有自己的根目录、`env`、`.spm/` 元数据、`.spm/sandbox` 写层、`.spm/token`。
`spm exec` 注入 `SPM_HOME / SPM_NAME / SPM_VERSION / SPM_VFS / SPM_READ_ROOT / SPM_VFS_ROOT`。

---

## 4. 虚拟文件系统（VFS 模式）

```bash
spm mode github-skills@1.2.0 vfs      # 默认
spm mode github-skills@1.2.0 plain    # 关掉，直接用版本根当 cwd
spm vfs root github-skills@1.2.0      # 打印只读层 / 可写层
spm vfs ls   github-skills@1.2.0
spm vfs cat  github-skills@1.2.0 SKILL.md
spm vfs put  github-skills@1.2.0 note.txt "写点东西"
```

视图 = **版本根（只读） ∪ `.spm/sandbox`（可写，copy-on-write）**：

- 读：先查写层，再查版本根
- 写：只落 sandbox，**绝不污染版本根**（`verify` 因此永远对得上）
- `resolve()` 拒绝 `..` / 绝对路径 / 逃出两个根
- `spm exec` 在 vfs 模式下 cwd 锁进 sandbox，但命令里的相对文件名会被改写成只读层的物理路径 —— 所以 `python3 tool.py` 读得到版本文件，写却只落 sandbox

这就是「给版本开虚拟文件系统隔离起来，方便开发者开发」：随便跑、随便写，版本根始终干净。

---

## 5. 自定义脚本执行

```bash
# 全局脚本
spm script add check "python3 github --help"
spm script add test  "python3 -m unittest discover -s tests -q"
spm script list
spm script rm check

# 版本内脚本（安装时写入元数据）
spm install my-skill@1.0 --script "check=python3 tool.py" --allow python3

# 运行：显式版本 > 当前版本；后面可跟参数
spm run github-skills@1.2.0 check
spm run github-skills test -- -v
```

脚本支持 `{python}` / `{root}` / `{sandbox}` 占位符。运行同样走白名单 + VFS + `shell=False`。
脚本查找顺序：版本内 `scripts` → 全局 `scripts`。

直接执行命令：

```bash
spm exec github-skills@1.2.0 -- python3 github doctor
```

---

## 6. 命令别名

```bash
spm alias add gs   "exec github-skills -- python3 github status"
spm alias add v12  "run github-skills@1.2.0 check"
spm alias add v13  "run github-skills@1.3.0 check"
spm alias list
spm alias rm gs

spm gs          # 等价于展开后的整条命令
spm v12         # 一条命令切版本跑脚本
```

别名在 argparse 解析**之前**展开，所以可以包住任意子命令和参数；别名不能覆盖内置命令名。

---

## 7. token 文件同步

默认 token 源就是 skill 包的 `.tokens`（与 `github-skills` 共用同一份，向上 4 层查找 `.tokens` / `.token`）。

```bash
spm token set /path/to/.tokens   # 改源文件
spm token sync                   # 分发到每个版本的 .spm/token
spm token status                 # 只看指纹，不回显值
```

- 安装完版本会**自动同步一次**
- 状态只报：是否存在、行数、字节数、`sha256` 前 12 位、mtime，以及每个目标是否一致
- 全程**不打印、不记录 token 值**；目标文件尝试 `chmod 600`（某些挂载忽略也不影响）
- 匿名也能装公开仓：找不到 token 文件时只是跳过同步，不报错

---

## 8. 一条完整示例

```bash
python3 spm doctor
python3 spm source list

# 装两个版本，一个从正式仓、一个从 PR
python3 spm install github-skills@1.2.0 --trust --allow python3 \
    --script "check=python3 github --help"
python3 spm install github-skills@1.3.0 \
    --from pr:Cool-zimo/spm-packages#1:packages

python3 spm list
python3 spm alias add v12 "run github-skills@1.2.0 check"
python3 spm alias add v13 "run github-skills@1.3.0 check"
python3 spm v12
python3 spm v13

python3 spm vfs put github-skills@1.2.0 scratch.txt "开发中..."
python3 spm verify github-skills@1.2.0      # 版本根仍是干净的
python3 spm token status
```

## 9. 回归测试

```bash
python3 -m unittest discover -s tests -v    # 25 项全绿，全离线、不碰真实 token
```
