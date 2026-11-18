# 交互播放器

可上传任意 sb3、点绿旗 / 点角色 / 重载、分帧截图。用法见 `文档/播放器接口.md`。

`vendor/` 下的 4 个预构建 UMD 运行时（scratch-storage / scratch-render /
scratch-svg-renderer / scratch-vm，约 9.9 MB）体积较大，**不放进本 PR 的源码树**，
已随完整工具包打进 `downloads/sb3-tools.v1.0.0.zip`，解压后放在本目录即可运行。

本地跑：

```bash
cd 交互播放器
python3 -m http.server 8123
# 浏览器打开 http://127.0.0.1:8123/
node capture.js
```

无头 Chromium 若无 WebGL，index.html 内置 stub renderer + Canvas 2D 绘制，
VM 的坐标 / 方向 / 气泡 / 线程数仍是真实运行时状态。
