# spm-packages

**spm 的官方包仓库。** 这里只放「包」，`spm` 本身是包管理器、独立存在。

```
spm                        包管理器（本仓库 spm/ 目录，独立源码树）
 ├── github-skills          包 → packages/github-skills.v.1.3.2.zip
 └── sb3                    包 → packages/sb3.v.1.0.0.zip
```

## 开箱即用

`spm` 的默认源就指向这个仓库的 `packages/` 目录，装包不用写 URL：

```bash
python3 spm doctor
python3 spm source list                          # official ← 默认
python3 spm install github-skills                 # 按包名前缀自动挑 zip
python3 spm install sb3
python3 spm list
python3 spm use github-skills@1.3.2
python3 spm exec github-skills -- python3 github --help
```

`packages/registry.json` 是人可读的包清单；`install` 不需要它——
源不写 `pattern` 时，spm 用**包名前缀**从同一个目录里挑对应文件，
所以一个源能放任意多个包。

## 换下载源

三种粒度，随用随切：

```bash
# 1. 加一个源并设为默认
python3 spm source add mirror github:me/mirror@main:packages --default
python3 spm source use official            # 换回来
python3 spm source list / show / rm

# 2. 单次用某个已命名源
python3 spm install github-skills --source mirror

# 3. 单次用任意 spec（github / url / path / pr）
python3 spm install github-skills --from github:me/fork@dev:packages
python3 spm install github-skills --from path:/local/packages
python3 spm install github-skills --from pr:Cool-zimo/spm-packages#3
```

源里若写了 `pattern`，仍按 pattern 挑（兼容老配置）；没写就按包名前缀。

## 目录

| 路径 | 是什么 |
|---|---|
| `packages/` | **正式包目录**，spm 默认从这里下载 |
| `packages/registry.json` | 包清单（名字 / 版本 / 文件 / 说明） |
| `spm/` | 包管理器源码（`spm` + `spmlib/` + 40 项离线回归） |
| `spm/SPM.md` | 管理器完整文档 |
| `downloads/` | 改名前的历史发布包，保留供对照，**不再作为默认源** |
| `sb3/` | sb3 包的源码副本（PR #2 合入内容） |
| `dedupe.py` / `test_dedupe.py` | 一条龙演示时写的示例代码 |

## 版本历史

- `github-skills.v.1.3.2.zip` — 拆出 spm，纯包；32 项回归
- `github-skills.v.1.3.1.zip` — 修大文件静默写空包、`pr --merge`；61 项回归
- `github-skills.v.1.3.0.zip` — 合并语义 `sync`、`pull --zip`、匿名只读、`pages`
- `github-skills.v.1.2.0.zip` — 多账号管理 + 一条龙
- `sb3.v.1.0.0.zip` — sb3 命令组（原 `sb3-tools.v1.0.0.zip`）

## 改名说明

本仓库原名 `Cool-zimo/github-skills-lab`。改成 `spm-packages` 后，
**旧的 `raw.githubusercontent.com/.../github-skills-lab/...` 直链失效**，
请用下面新链接；仓库网页 URL 会自动跳转。

## 下载

```
https://raw.githubusercontent.com/Cool-zimo/spm-packages/main/packages/github-skills.v.1.3.2.zip
https://raw.githubusercontent.com/Cool-zimo/spm-packages/main/packages/sb3.v.1.0.0.zip
https://raw.githubusercontent.com/Cool-zimo/spm-packages/main/packages/registry.json
```
