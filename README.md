# github-skills-lab

`github-skills` 一条龙演示仓：

```
github new repo github-skills-lab     # 建仓 + 拉到 projects/
# 写 test_dedupe.py → 复现失败 → 写 dedupe.py → 跑通
github sync . -m "feat: unique_sorted + tests"   # 整目录一次推上去
github verify .                                   # 本地 vs 线上逐字节
```

## 验证点

```
python -m unittest -q     → Ran 3 tests OK
```

按 karpathy 四条：先写复现测试、只写解决问题的最少代码、不碰无关文件、每步带验证点。

## 交付包

`downloads/github-skills.v.1.2.0.zip` —— 本仓库同时托管这次一条龙用到的完整工具包，
可用 `https://raw.githubusercontent.com/Cool-zimo/github-skills-lab/main/downloads/github-skills.v.1.2.0.zip` 直接下载。
