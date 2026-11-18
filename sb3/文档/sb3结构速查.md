# sb3 结构速查

## 一句话

`.sb3` **不是代码文本，是 ZIP 包**：`project.json` 存程序（积木图 / AST），图片音频按内容 MD5 命名、平铺在根目录。改后缀为 `.zip` 就能解压。`.sprite3` 结构相同，只是 JSON 叫 `sprite.json`。

MIME：`application/x.scratch.sb3`。

## 包内布局

```
project.json
ff40126d1f65b281b8ae6f1d136e99cd.svg    ← 背景
40ecd55d1bbf3f0fd3f542857f6aae02.svg    ← 造型
83a9787d4cb6f3b7632b4ddfebf74367.wav    ← 声音
```

**高频打包错误**：把整个 build 文件夹压进去，根目录多一层 `build/`。导入能成功，但角色显示成问号。素材必须和 `project.json` 同级。

## project.json 顶层（只有 4 个字段）

| 字段 | 含义 |
|---|---|
| `targets` | 舞台 + 所有角色，顺序即图层顺序 |
| `monitors` | 变量/列表的舞台监视器 |
| `extensions` | 用到的扩展 ID（pen、music、videoSensing…） |
| `meta` | `semver` 3.0.0、`vm`、`agent`、`origin` |

## target（Stage 或 Sprite）

公共字段：
`isStage` `name` `variables` `lists` `broadcasts` `blocks` `comments` `currentCostume` `costumes` `sounds` `layerOrder` `volume`

Sprite 额外：`x` `y` `size` `direction` `visible` `draggable` `rotationStyle`（`all around` / `left-right` / `don't rotate`）

Stage 额外：`tempo` `videoState`（`on`/`off`/`on-flipped`）`videoTransparency` `textToSpeechLanguage`

约束：有且仅有一个 `isStage: true`，且 `name === "Stage"`；每个 target 至少一个 costume，否则导入后回退成问号造型。

`variables` / `lists` / `broadcasts` 是 `ID → 数组` 的映射：
- 变量：`[名称, 值]`，云变量第三项为 `true`
- 列表：`[名称, [元素…]]`
- 广播：`ID → 名称`（字符串）

这些 ID 会在积木的 `fields` / `inputs` 和 `monitors.id` 里被引用，**必须三处对齐**。

## blocks：核心，是图不是文本

`blocks` 是 `ID → 积木对象` 的扁平字典，靠 `next` / `parent` 串成链表。

对象字段：
`opcode`（哪块积木）、`next`、`parent`、`inputs`、`fields`、`shadow`、`topLevel`；顶层积木才有 `x` / `y`；可选 `comment`（注释 ID）、`mutation`（自定义积木）。

示例：

```json
{
  "flag1": {
    "opcode": "event_whenflagclicked", "next": "move1", "parent": null,
    "inputs": {}, "fields": {}, "shadow": false,
    "topLevel": true, "x": 50, "y": 50
  },
  "move1": {
    "opcode": "motion_movesteps", "next": null, "parent": "flag1",
    "inputs": {"STEPS": [1, [4, "10"]]},
    "fields": {}, "shadow": false, "topLevel": false
  }
}
```

### inputs 三态（最容易懵）

第一位不是值，是**阴影状态**：

| 形式 | 含义 |
|---|---|
| `[1, X]` | 有阴影，X 可为 blockId 或内联 primitive |
| `[2, "blockId"]` | 有块、无阴影 |
| `[3, "blockId", "shadowId"]` | 阴影被别的块盖住了，第 3 项存原阴影 |

### 内联 primitive（默认值被压缩成数组）

| 码 | 类型 | 码 | 类型 |
|---|---|---|---|
| 4 | 数字 | 9 | 颜色 `#RRGGBB` |
| 5 | 正数 | 10 | 字符串 |
| 6 | 正整数 | 11 | 广播 |
| 7 | 整数 | 12 | 变量 |
| 8 | 角度 | 13 | 列表 |

所以「移动 10 步」里的 `10` **不是 fields**，是 `inputs.STEPS = [1, [4, "10"]]`。`fields` 用于下拉框这类不能塞 reporter 的位置，格式 `[值, id或null]`。

> **调试时注意**：JSON 里内联 primitive 不占一个 block 条目，但 VM 反序列化会把它们展开成真正的 shadow 积木。本工具包示例 `project.json` 里是 **5 块**，VM 加载后 `blocks._blocks` 是 **9 块**——这不是错误，是压缩表示被还原了。

### 自定义积木另有一套

`procedures_definition` / `procedures_prototype` / `procedures_call` 依赖 `mutation`：`proccode`、`argumentids`、`argumentnames`、`argumentdefaults`、`warp`。手写极易漏。

## 资源对象

`assetId` + `name` + `md5ext` + `dataFormat`

- 造型再加 `rotationCenterX` / `rotationCenterY` / `bitmapResolution`
- 声音再加 `rate` / `sampleCount`
- `md5ext` = `assetId + "." + dataFormat`，通常 `assetId` 就是**文件内容的 MD5**
- SVG 建议带 `xmlns` 与 `viewBox`，缺 viewBox 常被渲染成问号

## 最小骨架

看 `01_生成sb3/project.json`，它是能直接导入的完整最小工程：一个 Stage、一个 Sprite、5 个积木、两段脚本。改 `生成sb3.py` 里的 `blocks` 字典再跑一次，MD5、打包、自检会自动重做。
