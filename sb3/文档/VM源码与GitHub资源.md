# VM 源码与 GitHub 资源

## 04_VM源码/tw-scratch-vm 是什么

`TurboWarp/scratch-vm` 源码快照，仓库地址 `https://github.com/TurboWarp/scratch-vm`，`package.json` 报 `scratch-vm@2.1.46`，许可证 **MPL-2.0**；其上游官方 VM 部分沿用 BSD-3-Clause。README 原文：

> Modified Scratch VM with a JIT compiler and more features. This is a drop-in replacement for LLK/scratch-vm.

打包时剔除了内置音色 mp3、source map、test/docs 与大素材以控制体积；`src/` 下 **140 个 js 全部保留**，另有 `package.json` / `README.md` / `LICENSE` / `webpack.config.js`。

## 源码目录怎么读

| 路径 | 作用 |
|---|---|
| `src/virtual-machine.js` | 入口：`loadProject` / `deserializeProject` / `greenFlag` / `start` |
| `src/serialization/sb3.js` | **sb3 ↔ 运行时**的序列化/反序列化，primitive 与 inputs 压缩编码都在这里 |
| `src/serialization/deserialize-assets.js` | 把 ZIP 里的素材注册进 storage |
| `src/engine/runtime.js` | 线程调度、targets、扩展、编译器选项 |
| `src/engine/threads.js` | 协作式协程：yield / 等待 / 每帧步进 |
| `src/engine/blocks.js` | 运行时 AST（和 project.json 的扁平结构不同） |
| `src/blocks/scratch3_*.js` | 每类积木的具体实现，建议从 `scratch3_motion.js` 看起 |
| `src/compiler/irgen.js` | TurboWarp 编译器：积木树 → IR |
| `src/compiler/jsgen.js` | IR → 优化后的 `function*` JavaScript |
| `src/io/mouse.js` | 鼠标拾取与点击帽子块（`_pickTarget` 调 `renderer.pick`） |
| `src/sprites/rendered-target.js` | `setXY`、造型、气泡状态；`getFencedPositionOfDrawable` 在这里被调用 |
| `src/playground/benchmark.js` | **最值得读**：619~751 行是完整 VM + 渲染器 + 音频的初始化样板 |
| `src/extension-support/` | 扩展加载、worker、权限 |

## TurboWarp 为什么快

官方 VM 是解释执行：每帧遍历积木树，逐块查 ID、查 opcode 对应函数、查 input、自己维护循环/条件栈，还要支持随时挂起与运行中改积木。

TurboWarp 在线程启动时把脚本编译成 JS `function*`，用 `yield` 保留「可暂停/每帧刷新」语义，省掉逐块查表开销。官方称 10~100 倍提速；2025-09 的新编译器进一步做类型分析，去掉冗余的 `(+x || 0)` 转换。代价是**运行中改积木不能立即生效**，编辑器里可关编译器。

示例（官方文档）：

```js
// 编译前：forever → move (my variable) steps
// 编译后：
const myVariable = stage.variables["`jEk@4|i...my variable"];
return function* () {
  while (true) {
    runtime.ext_scratch3_motion._moveSteps((+myVariable.value || 0), target);
    yield;
  }
};
```

## 从零写 VM 的难点

1. **协作式调度**：等待、循环每帧、warp、克隆、广播后等待，全靠可挂起的线程状态机
2. **Scratch 怪语义**：弱类型、NaN 归零、大小写不敏感比较、克隆体独立变量、30 FPS 步进、围栏限制
3. **渲染与资源**：SVG 处理、WebGL skin、颜色碰撞、画笔层、音频引擎
4. **扩展系统**：20+ 官方扩展 + 自定义扩展的权限与沙箱
5. **许可证**：官方 3.0 源码（除 `scratch-blocks`）自 2024-11 起改为 **AGPL-3.0**，此前是 BSD-3-Clause

## GitHub 资源清单

**官方主线**
- `https://github.com/scratchfoundation/scratch-editor` — monorepo，含 `packages/scratch-vm`、`scratch-render`、`scratch-gui`、`scratch-paint`、`scratch-storage`
- `https://github.com/scratchfoundation/scratch-vm` — 旧独立仓库（有 playground、`npm start` 可单独跑 VM）
- `https://github.com/scratchfoundation/scratch-parser` — sb2/sb3 校验，不执行，适合给生成器做预检

**TurboWarp 系**
- `https://github.com/TurboWarp/scratch-vm` ⭐ — JIT 编译器，drop-in 替换，MPL-2.0
- `https://github.com/TurboWarp/scratch-gui` / `scratch-render` / `scratch-paint` — 配套层
- `https://github.com/TurboWarp/packager` — sb3 → HTML / zip / Win·mac·Linux 可执行，MPL-2.0
- `https://github.com/TurboWarp/desktop` — 离线编辑器，GPL-3.0
- `https://github.com/TurboWarp/extensions` — 扩展库，MIT
- `https://github.com/TurboWarp/docs` — 文档，CC-BY-4.0
- 文档：`https://docs.turbowarp.org/how`（编译器原理）、`https://docs.turbowarp.org/new-compiler`、`https://docs.turbowarp.org/development/getting-started`

**独立实现（读源码学架构）**
- `https://github.com/forkphorus/forkphorus` — TS，sb3/sb2/sb1 → JS 编译器，CPS 风格
- `https://github.com/leopard-js/leopard` + `sb-edit` — MIT，sb3 ↔ 可读人类 JS
- `https://github.com/aspizu/goboscript` — Rust，文本语言 → `.sb3`，带反编译器
- `https://github.com/Mrmayman/rash` — Rust + Cranelift JIT 编译到原生码，实验性
- `aspizu/rustphorus`（Rust VM，作者自述很粗糙）、`pnsk-lab/xyo-rust`（Rust + LLVM IR 原生运行时 MVP）、`ScratchForge`（Python 生成 sb3 并用 headless scratch-vm 验证）

## 想在本地跑真正的 TurboWarp JIT

本工作区装 npm 依赖时被网络与 peer 依赖（GitHub 源 `scratch-render-fonts`）卡住，且无头浏览器没有 WebGL，所以交付的播放器走的是预构建 UMD + stub renderer。在有完整环境的机器上：

```bash
git clone https://github.com/TurboWarp/scratch-vm
cd scratch-vm
npm ci                 # 若 GitHub 源卡住，可把 scratch-parser 换 npm 版、移除 fonts peer
npm start              # webpack-dev-server，8073 端口
# 打开 http://localhost:8073/playground/
```

要定制自己的播放器，`04_VM源码/tw-scratch-vm/webpack.player.js` 与同目录 `player/index.js` 已是一份可用的 webpack 打包配置（entry 指向 `player/index.js`，require 本地 `src/`）；`03_交互播放器/` 里放了一份副本便于对照。再补上 `scratch-render` + `scratch-svg-renderer` 即可换成官方 WebGL 渲染。主要改动点通常是 `src/blocks/scratch3_*.js`（加积木）或 `src/compiler/`（改编译行为）。
