# github-skills-lab

`github-skills` 一条龙演示仓，外加内置包管理器 `spm` 的源码与交付包。

```
github new repo github-skills-lab            # 建仓 + 拉到 projects/
# 写 test_dedupe.py → 复现失败 → 写 dedupe.py → 跑通
github sync . -m "feat: unique_sorted + tests" --dry-run   # 先看清单
github sync . -m "feat: unique_sorted + tests"             # 整目录一次推上去
github verify .                                            # 本地 vs 线上逐字节
github pages --enable --wait                               # 一条龙最后一步：开 Pages + 等构建
```

## 验证点

```
python -m unittest -q                          → Ran 3 tests OK
python3 -m unittest discover -s tests -v      → Ran 61 tests OK（工具包内：36 + spm 25）
```

按 karpathy 四条：先写复现测试、只写解决问题的最少代码、不碰无关文件、每步带验证点。

## 交付包

- `downloads/github-skills.v.1.3.1.zip` —— **当前工具包**：修掉 >1 MB 大文件静默写空包，新增 `github pr --merge`。
  可用 `https://raw.githubusercontent.com/Cool-zimo/github-skills-lab/main/downloads/github-skills.v.1.3.1.zip` 直接下载；
  逐条改动见 `downloads/CHANGES-v1.3.1.md`（61 项离线回归全绿）。
- `downloads/github-skills.v.1.3.0.zip` —— 上一版工具包，含 6 条实测优化 + **内置包管理器 `spm`**。
  可用 `https://raw.githubusercontent.com/Cool-zimo/github-skills-lab/main/downloads/github-skills.v.1.3.0.zip` 直接下载。
- `downloads/github-skills.v.1.2.0.zip` —— 上一版，保留供对照。
- `downloads/CHANGES-v1.3.0.md` —— 逐条改动、验证点与兼容性说明。
- `downloads/SPM.md` —— 包管理器速览；`spm/` —— 与 zip 内一致的源码，方便直接审阅。

## 内置包管理器 spm（默认装到 skill 上）

`spm` 随 zip 分发，解压即用；`SPM_HOME` 默认就是包内 `skills/`，也可单独拷走 `spm` + `spmlib/` 使用。

```bash
python3 spm doctor
python3 spm install github-skills@1.2.0 --trust --allow python3 --script "check=python3 github --help"
python3 spm install github-skills@1.3.0 --from pr:Cool-zimo/github-skills-lab#1:downloads
python3 spm list
python3 spm alias add v12 "run github-skills@1.2.0 check"
python3 spm v12
```

支持：仓库 / 直链 / 本地 / **PR** 四种下载源、多版本并存、安全模式与版本目录限制、
`trust` 信任、`allow` 命令白名单、独立版本根与 env、**VFS 虚拟文件系统隔离**
（写只落 sandbox，不污染版本根）、自定义脚本 `run` / `exec`、命令别名管理、
token 文件同步（值不回显）。完整说明见 `downloads/SPM.md` 与 `spm/guides/使用spm.md`。

> v1.3.0 起 `sync` **默认合并语义**（带 `base_tree`），线上多出的文件会被保留；
> 要整目录镜像、删掉线上多余文件，必须显式 `--mirror`。本 PR 仍是用默认合并语义推的，
> 所以 `dedupe.py` / `test_dedupe.py` / 旧 zip 都保持原样。
