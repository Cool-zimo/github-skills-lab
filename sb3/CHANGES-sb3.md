# CHANGES · sb3 adapter v1.0.0

基于 `github-skills` v1.3.0（PR #1 的 head）做**纯增量**适配。

## 新增能力

| 命令 | 行为 | 需要 token |
|---|---|---|
| `github sb3 make [out]` | 生成最小可导入 sb3（舞台 + Sprite1 + 5 积木 / 2 脚本） | 否 |
| `github sb3 check <f> [--json]` | 结构校验；`--json` 给 CI 用，退出码 0/1/2 | 否 |
| `github sb3 tree <f>` | 包内清单、每个 target 的积木/造型/帽子块概览 | 否 |
| `github sb3 unpack <f> [dir]` | 解包，拒绝非空目录与 zip-slip | 否 |
| `github sb3 pack <dir> -o <f>` | 打包，自动重算 `assetId`/`md5ext`、平铺、自检 | 否 |
| `github sb3 guide` | 内置结构速查，离线 | 否 |

## 兼容性

- **零行为变更**：所有既有命令与参数原样，`sb3` 只是新增子命令。
- 不解析账号、不调 GitHub API、不写远端；匿名只读环境可用。
- 零第三方依赖，Python 3.8+，MIT（与 github-skills 一致）。
- `import sb3lib` 用 try/except 包住：没放 `sb3lib.py` 时其它命令不受影响。
- `COMMANDS` 集合登记了 `sb3`，避免 `lift_as()` 把首参误判成账号名。

## 与 PR #1 的关系

本 PR **只新增文件**，不碰 `README.md` / `dedupe.py` / `test_dedupe.py` / `downloads/*.zip`。
两个 PR 可以同时存在、依次合并，不需要 rebase，也不会互相覆盖。

`downloads/` 里新增的是 `sb3-tools.v1.0.0.zip`，与 PR #1 的 `github-skills.v.1.3.0.zip`
文件名不同，不冲突。

## 验证点

1. `python3 github sb3 make /tmp/a.sb3` → 自检通过
2. `python3 github sb3 check /tmp/a.sb3 --json` → `{"ok": true, "errors": []}`
3. `unpack → pack → check` 回环 → 仍通过，且输出「重算 …」
4. 7 种故意损坏的 sb3 → 全部被 `check` 拒绝，错误信息可定位
5. `python3 -W error::ResourceWarning -m unittest discover -s tests -v` → **16/16 OK**
6. v1.3.0 原有 49 项回归 → **49/49 OK**
7. 移开 `.tokens` → `sb3 check` 仍通过

## 已知限定

- `check` 只保证**格式合法**，不保证逻辑正确（例如循环里没等待会卡帧），必须真跑验证。
- 交互播放器在无 WebGL 的无头浏览器里用 stub renderer + Canvas 2D 绘制，
  VM 的坐标/方向/气泡/线程数是真实运行时状态；WebGL 特效、画笔、颜色碰撞不在覆盖范围。
- 自定义积木（`procedures_*` 的 `mutation`）只做基础字段存在性检查，未逐项校验
  `proccode` / `argumentids` / `argumentdefaults` 的一致性。
