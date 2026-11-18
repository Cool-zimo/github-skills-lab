# sb3 adapter for github-skills

把「做 sb3 / 调 sb3 / 交互 sb3 / 截图」这条工具链接进 `github-skills`，作为 **`github sb3` 本地命令组**。

> 本 PR **只新增文件**，不修改 `README.md` / `dedupe.py` / `test_dedupe.py` / `downloads/*.zip` 等任何已有文件，
> 因此与仍 open 的 PR #1 **零冲突**。这正好是 v1.3.0 「`sync` 默认合并语义」想支持的并行贡献场景：
> 两个人各加各的文件，互不覆盖，也不需要 `--mirror`。

## 为什么是本地命令

`sb3` 的五个能力全在**本地文件**上跑：不解析账号、不调 GitHub API、不需要 token、不写远端。
和 `guide` / `doctor` 一样，匿名只读环境也能用；也不会碰到 `sync` / `push` 的写语义。

## 命令

```bash
python3 github sb3 make   [out.sb3]          # 生成可导入的最小示例工程
python3 github sb3 check  <file.sb3> [--json] # 结构校验，退出码 0/1/2
python3 github sb3 tree   <file.sb3>          # 包内清单 + targets/blocks 概览
python3 github sb3 unpack <file.sb3> [dir]    # 解包成可编辑目录（防 zip-slip）
python3 github sb3 pack   <dir> -o <out.sb3>  # 打包：自动重算素材 MD5 + 平铺 + 自检
python3 github sb3 guide                     # 打印内置 sb3 结构速查（离线）
```

`check` 覆盖上一轮实测中翻车率最高的几项：ZIP 根目录平铺、UTF-8 无 BOM、
`assetId == 内容 MD5`、`dataFormat` 与后缀一致、SVG 有 `viewBox`、
`next`/`parent` 双向一致、inputs 阴影首位 1/2/3、内联 primitive 类型码 4~13、
`fields` 是数组、舞台唯一且名为 `Stage`、`monitors.id` 已声明。

## 挂接方式

| 文件 | 作用 |
|---|---|
| `sb3lib.py` | 核心适配层，零第三方依赖，只用标准库 |
| `github` | 打过补丁的 v1.3.0 CLI（可直接替换包内同名文件） |
| `github-sb3.patch` | 对原版 `github` 的 unified diff，便于审阅改了哪几处 |
| `ghlib.py` | v1.3.0 的 API 封装副本，只为让本目录自包含、CLI 能 import |
| `tests/test_sb3.py` | 16 项离线回归 |
| `生成sb3.py` / `校验sb3.py` | 独立可跑的等价脚本（不依赖 CLI） |
| `交互播放器/` | 上传 sb3 / 绿旗 / 点击 / 重载 / 截图 |
| `文档/` | 结构速查、调试手册、播放器接口、VM 源码与 GitHub 资源 |
| `examples/最小示例.sb3` | 可直接导入编辑器的成品 |

补丁只动 `github` 四处：

1. `import sb3lib`（try/except，缺文件时其它命令照常用）
2. `COMMANDS` 登记 `"sb3"` —— **必须**，否则 `lift_as()` 会把首个参数误判成账号名
3. 新增 `cmd_sb3()` 与内置 `SB3_GUIDE`
4. `build_parser()` 注册 `sb3` 子命令组

完整可运行包（含 `vendor/` 的 4 个 UMD 运行时与截图）在 `downloads/sb3-tools.v1.0.0.zip`。

## 实测

| 验证 | 结果 |
|---|---|
| `github sb3 make → check → tree` | 5 块积木 / 2 段脚本，校验 **0 错 0 警告** |
| `unpack → pack → check` 回环 | 素材 MD5 自动重算，回环后仍通过 |
| 故意造 7 种坏 sb3 | 断链、parent 不符、素材缺失、assetId 错、根目录嵌套、类型码 99、BOM —— **全部被拒** |
| `python3 -W error::ResourceWarning -m unittest discover -s tests -v` | **16/16 OK** |
| 原有 49 项回归（v1.3.0） | **49/49 OK**，未回归 |
| 移开 `.tokens` 后 `sb3 check` | 仍通过，确认不依赖 token |

沿用 PR #1 的 Karpathy 思路：每条能力先写一个「故意错」的版本确认会被拒绝，再确认正确版本通过。

## 一个容易误判的点

`check` 报告「积木 5 块」，但 Scratch VM 加载后 `blocks._blocks` 是 **9 块**。
JSON 里的内联 primitive（`[4, "10"]`）不是独立 block 条目，反序列化时会被展开成 shadow 积木。
两个数字都对，只是**序列化前**与**运行时**两个视角。

## 不在本 PR 里

- `scratch-render` / TurboWarp VM 源码本体（体积大且属上游仓库，文档里给了地址与导读）
- 任何 GitHub 写操作：本 PR 的改动全是本地命令 + 新增文件
- `README.md`：留给 PR #1，避免冲突
