#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sb3 结构调试器：把 .sb3 当 ZIP 解开，逐项校验并输出中文报告。

用法：
    python3 校验sb3.py 最小示例.sb3
    python3 校验sb3.py 其它项目.sb3 --json     # 机器可读输出

退出码：0 = 全部通过；1 = 存在错误；2 = 文件本身打不开。
"""
import hashlib
import json
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree

PRIMITIVE_TYPES = {
    4: "数字", 5: "正数", 6: "正整数", 7: "整数", 8: "角度",
    9: "颜色", 10: "字符串", 11: "广播", 12: "变量", 13: "列表",
}
INPUT_SHADOW = {1: "有阴影", 2: "无阴影", 3: "阴影被覆盖"}
TARGET_REQUIRED = (
    "isStage", "name", "variables", "lists", "broadcasts", "blocks",
    "comments", "currentCostume", "costumes", "sounds", "layerOrder", "volume",
)


def check(sb3_path):
    errors, warnings, info = [], [], []
    path = Path(sb3_path)
    if not path.is_file():
        return ["文件不存在: %s" % path], [], [], 2

    try:
        z = zipfile.ZipFile(path)
    except Exception as e:
        return ["不是合法 ZIP（sb3 本质是 ZIP）: %s" % e], [], [], 2

    names = z.namelist()
    info.append("ZIP 条目 %d 个" % len(names))
    bad = z.testzip()
    if bad:
        errors.append("ZIP 内文件损坏: %s" % bad)

    # 1) 根目录结构
    if "project.json" not in names:
        errors.append("根目录缺 project.json（最常见打包错误：把整个文件夹压进去了）")
        return errors, warnings, info, 1
    nested = [n for n in names if "/" in n]
    if nested:
        errors.append("ZIP 根目录出现子目录，素材必须平铺: %s" % nested[:3])

    # 2) JSON 编码与解析
    raw = z.read("project.json")
    if raw.startswith(b"\xef\xbb\xbf"):
        errors.append("project.json 带 UTF-8 BOM，部分工具会乱码")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        errors.append("project.json 不是 UTF-8: %s" % e)
        return errors, warnings, info, 1
    info.append("project.json %d 字节，UTF-8 无 BOM" % len(raw))
    try:
        project = json.loads(text)
    except json.JSONDecodeError as e:
        errors.append("project.json 不是合法 JSON: %s" % e)
        return errors, warnings, info, 1

    # 3) 顶层字段
    for key in ("targets", "monitors", "extensions", "meta"):
        if key not in project:
            errors.append("顶层缺字段 %s" % key)
    meta = project.get("meta", {})
    info.append("meta.semver=%s  vm=%s" % (meta.get("semver"), meta.get("vm")))

    targets = project.get("targets") or []
    if not targets:
        errors.append("targets 为空，Scratch 至少需要舞台")
        return errors, warnings, info, 1
    stages = [t for t in targets if t.get("isStage")]
    if len(stages) != 1:
        errors.append("应有且仅有 1 个舞台，实际 %d 个" % len(stages))
    elif stages[0].get("name") != "Stage":
        errors.append("舞台 name 必须是 'Stage'，实际 %r" % stages[0].get("name"))
    info.append("targets %d 个（舞台 1 + 角色 %d）" % (len(targets), len(targets) - len(stages)))

    # 4) 每个 target
    all_var_ids = {}
    for t in targets:
        tname = t.get("name") or "<无名>"
        for k in TARGET_REQUIRED:
            if k not in t:
                errors.append("[%s] 缺字段 %s" % (tname, k))
        if not t.get("costumes"):
            errors.append("[%s] costumes 为空，导入后会显示问号造型" % tname)
        if t.get("currentCostume", 0) >= max(1, len(t.get("costumes") or [])):
            errors.append("[%s] currentCostume 越界" % tname)
        for kind in ("variables", "lists", "broadcasts"):
            for vid, val in (t.get(kind) or {}).items():
                if not isinstance(val, list) or not val:
                    errors.append("[%s] %s[%s] 不是数组" % (tname, kind, vid))
                all_var_ids[vid] = tname
        for c in t.get("costumes") or []:
            check_asset(z, names, c, tname, "costume", errors, warnings)
        for s in t.get("sounds") or []:
            check_asset(z, names, s, tname, "sound", errors, warnings)

    # 5) blocks 图结构
    total_blocks = 0
    for t in targets:
        tname = t.get("name") or "<无名>"
        blocks = t.get("blocks") or {}
        total_blocks += len(blocks)
        for bid, b in blocks.items():
            if not isinstance(b, dict):
                # 压缩表示（primitive）不会出现在 blocks 顶层，出现即异常
                errors.append("[%s] blocks[%s] 不是对象" % (tname, bid))
                continue
            if not b.get("opcode"):
                errors.append("[%s] 积木 %s 缺 opcode" % (tname, bid))
            if b.get("next"):
                nxt = b["next"]
                if nxt not in blocks:
                    errors.append("[%s] %s.next 指向不存在的 %s" % (tname, bid, nxt))
                elif blocks[nxt].get("parent") != bid:
                    errors.append("[%s] %s.next=%s 但对方 parent=%r（链断裂）"
                                  % (tname, bid, nxt, blocks[nxt].get("parent")))
            if b.get("parent") and b["parent"] not in blocks:
                errors.append("[%s] %s.parent 指向不存在的 %s" % (tname, bid, b["parent"]))
            for iname, inp in (b.get("inputs") or {}).items():
                if not isinstance(inp, list) or not inp:
                    errors.append("[%s] %s.inputs.%s 不是数组" % (tname, bid, iname))
                    continue
                if inp[0] not in INPUT_SHADOW:
                    errors.append("[%s] %s.inputs.%s 首位=%r，应为 1/2/3"
                                  % (tname, bid, iname, inp[0]))
                if inp[0] == 3 and len(inp) < 3:
                    errors.append("[%s] %s.inputs.%s 声明被覆盖阴影却缺第 3 项" % (tname, bid, iname))
                val = inp[1] if len(inp) > 1 else None
                if isinstance(val, list):
                    code = val[0] if val else None
                    if code not in PRIMITIVE_TYPES:
                        errors.append("[%s] %s.inputs.%s 内联原始值类型码 %r 非法（应为 4~13）"
                                      % (tname, bid, iname, code))
                elif isinstance(val, str) and val not in blocks:
                    errors.append("[%s] %s.inputs.%s 引用不存在的积木 %s" % (tname, bid, iname, val))
                if len(inp) > 2 and isinstance(inp[2], str) and inp[2] not in blocks:
                    warnings.append("[%s] %s.inputs.%s 阴影块 %s 不在 blocks 中" % (tname, bid, iname, inp[2]))
            for fname, field in (b.get("fields") or {}).items():
                if not isinstance(field, list) or not field:
                    errors.append("[%s] %s.fields.%s 不是数组" % (tname, bid, fname))
            # 变量引用一致性
            for fname, field in (b.get("fields") or {}).items():
                if isinstance(field, list) and len(field) > 1 and isinstance(field[1], str):
                    if field[1] not in all_var_ids and fname in ("VARIABLE", "LIST", "BROADCAST_OPTION"):
                        warnings.append("[%s] %s.fields.%s 引用了未声明的 ID %s"
                                        % (tname, bid, fname, field[1]))
    info.append("积木 %d 块，next/parent 链与 inputs 编码已校验" % total_blocks)

    # 6) monitors / extensions
    for m in project.get("monitors") or []:
        mid = m.get("id")
        if mid and mid not in all_var_ids:
            warnings.append("monitor %r 的 id 未在任何 target 中声明" % mid)
    exts = set(project.get("extensions") or [])
    info.append("extensions: %s" % (", ".join(sorted(exts)) or "无"))
    used_prefix = set()
    for t in targets:
        for b in (t.get("blocks") or {}).values():
            if isinstance(b, dict) and "_" in (b.get("opcode") or ""):
                prefix = b["opcode"].split("_")[0]
                if prefix not in ("motion", "looks", "sound", "event", "control",
                                  "sensing", "operator", "data", "procedures", "argument"):
                    used_prefix.add(prefix)
    for p in used_prefix - exts:
        warnings.append("积木前缀 %r 疑似扩展，但 extensions 未声明" % p)

    z.close()
    return errors, warnings, info, 1 if errors else 0


def check_asset(z, names, asset, tname, kind, errors, warnings):
    label = "%s/%s" % (tname, asset.get("name", "?"))
    for key in ("assetId", "name", "md5ext", "dataFormat"):
        if key not in asset:
            errors.append("[%s] %s 缺 %s" % (label, kind, key))
    md5ext = asset.get("md5ext")
    if not md5ext:
        return
    if md5ext not in names:
        errors.append("[%s] md5ext 引用的文件不存在: %s" % (label, md5ext))
        return
    data = z.read(md5ext)
    digest = hashlib.md5(data).hexdigest()
    if asset.get("assetId") != digest:
        errors.append("[%s] assetId=%s 与内容 MD5=%s 不符"
                      % (label, asset.get("assetId"), digest))
    ext = md5ext.rsplit(".", 1)[-1].lower()
    if asset.get("dataFormat", "").lower() not in (ext, "jpg" if ext == "jpeg" else ext):
        errors.append("[%s] dataFormat=%s 与后缀 .%s 不一致"
                      % (label, asset.get("dataFormat"), ext))
    if kind == "costume":
        for key in ("rotationCenterX", "rotationCenterY", "bitmapResolution"):
            if key not in asset:
                warnings.append("[%s] 造型缺 %s" % (label, key))
        if ext == "svg":
            try:
                root = ElementTree.fromstring(data)
                if not root.tag.endswith("svg"):
                    errors.append("[%s] SVG 根元素不是 svg" % label)
                if "viewBox" not in root.attrib:
                    errors.append("[%s] SVG 缺 viewBox，Scratch 可能渲染为问号" % label)
            except ElementTree.ParseError as e:
                errors.append("[%s] SVG 无法解析: %s" % (label, e))


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    as_json = "--json" in sys.argv
    if not args:
        print("用法: python3 校验sb3.py <文件.sb3> [--json]")
        return 2
    errors, warnings, info, code = check(args[0])
    if as_json:
        print(json.dumps({"errors": errors, "warnings": warnings,
                          "info": info, "ok": code == 0}, ensure_ascii=False, indent=2))
    else:
        print("=== 校验: %s ===" % args[0])
        for line in info:
            print("  · " + line)
        for w in warnings:
            print("  ! 警告: " + w)
        for e in errors:
            print("  × 错误: " + e)
        print("=== 结果: %s（错误 %d / 警告 %d）==="
              % ("通过" if code == 0 else "未通过", len(errors), len(warnings)))
    return code


if __name__ == "__main__":
    sys.exit(main())
