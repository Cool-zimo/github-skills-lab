# github-skills-lab

`github-skills` 一条龙演示仓：

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
python -m unittest -q     → Ran 3 tests OK
python3 -m unittest discover -s tests -v   → Ran 24 tests OK（工具包内离线回归）
```

按 karpathy 四条：先写复现测试、只写解决问题的最少代码、不碰无关文件、每步带验证点。

## 交付包

- `downloads/github-skills.v.1.3.0.zip` —— 当前工具包，6 条实测优化已合入，含 24 项离线回归。
  可用 `https://raw.githubusercontent.com/Cool-zimo/github-skills-lab/main/downloads/github-skills.v.1.3.0.zip` 直接下载。
- `downloads/github-skills.v.1.2.0.zip` —— 上一版，保留供对照。
- `downloads/CHANGES-v1.3.0.md` —— 逐条改动、验证点与兼容性说明。

> v1.3.0 起 `sync` **默认合并语义**（带 `base_tree`），线上多出的文件会被保留；
> 要整目录镜像、删掉线上多余文件，必须显式 `--mirror`。本 PR 就是用默认合并语义推的，
> 所以 `dedupe.py` / `test_dedupe.py` / 旧 zip 都保持原样。
