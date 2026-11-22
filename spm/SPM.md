# skillpm · GitHub skill 包管理器

一个**独立的包管理器**（v1.1.0），不随任何包分发：`spm` + `spmlib/` 拷走即用，零第三方依赖。
默认从官方包仓库 `Cool-zimo/spm-packages` 的 `packages/` 目录下载，装到 `skills/`（`SPM_HOME`）。

> 角色分工：**spm = 包管理器**；`github-skills`、`sb3` = 包。一个源里按包名前缀自动挑文件。

## 一句话能力

| 需求 | 命令 |
|---|---|
| 从仓库 / 直链 / 本地 / **PR** 下载并解包 | `spm install <name>@<ver> --from <源>` |
| 自定义下载源 | `spm source add/list/rm/show` |
| **同时用多个版本** | `spm install` 多个版本 + `spm use` / `spm list` |
| 限制版本所在目录 | `spm safe on` + 一版本一目录 + `spm dir` |
| 信任这个版本 | `spm trust / untrust` |
| 限制能执行的命令 | `spm allow <name>@<ver> python3` |
| 隔离版本 | 独立根 / env / `.spm/`；`spm mode vfs\|plain` |
| **虚拟文件系统隔离** | `spm vfs ls/cat/put/root`，写入只落 sandbox |
| 自定义脚本执行 | `spm script add` + `spm run` + `spm exec` |
| 命令别名管理 | `spm alias add/list/rm` + 直接 `spm <别名>` |
| token 文件同步 | `spm token set/sync/status`（不回显值） |

完整说明见 `guides/使用spm.md`。包内 `python3 -m unittest discover -s tests -v` 共 **49 项**：24 项属 `github` v1.3.0、25 项属 `spm`。

## 30 秒

```bash
python3 spm doctor
python3 spm install github-skills@1.2.0 --trust --allow python3 --script "check=python3 github --help"
python3 spm install github-skills --from pr:Cool-zimo/spm-packages#1:packages
python3 spm list
python3 spm alias add v12 "run github-skills@1.2.0 check"
python3 spm v12
python3 spm verify github-skills@1.2.0
```

## 安全模型

- 安全模式默认开：所有写入必须落在 `SPM_HOME` 内（`realpath + commonpath` 判界）
- 解包防 zip-slip：绝对路径 / `..` / 符号链接一律拒绝
- 版本默认**未信任**，只能跑白名单命令；`shell=False`，shell 元字符永远拒绝
- VFS = 版本根（只读）∪ `.spm/sandbox`（可写）；写不污染版本根，`verify` 永远对得上
- token 同步只报 sha256 前 12 位，值全程不显示、不写进任何日志

## 与 github-skills 的关系

- `spm` 复用同一份 `.tokens` / `.token`（向上 4 层查找），装完自动同步到各版本 `.spm/token`
- 默认源 `official` 就是 `Cool-zimo/spm-packages@main:packages`，`github-skills` / `sb3` 都能直接装
- 不依赖 `ghlib.py`：`spmlib/_gh.py` 自带极简 GitHub 客户端，单独拷走也能装公开仓
- 配合 v1.3.0 的 `github pages / --zip / 匿名只读 / sync 合并语义`，开发者可以在隔离环境里改 skill、验 sha、再推 PR

MIT · Python 3.8+ · 零依赖
