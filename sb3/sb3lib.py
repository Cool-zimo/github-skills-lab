#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sb3lib —— github-skills 的 sb3 适配层。

零第三方依赖，只用 Python 标准库。全部是**本地命令**：不调用 GitHub API、
不需要 token、不写远端。挂在 `github sb3 <子命令>` 下。

.sb3 本质是 ZIP：project.json 存积木图，素材按内容 MD5 命名平铺在根目录。
本模块提供 check / tree / unpack / pack / make 五个能力。
"""
import hashlib
import json
import os
import zipfile
from xml.etree import ElementTree

VERSION = "1.0.0"

PRIMITIVE_TYPES = {
    4: "数字", 5: "正数", 6: "正整数", 7: "整数", 8: "角度",
    9: "颜色", 10: "字符串", 11: "广播", 12: "变量", 13: "列表",
}
INPUT_SHADOW = {1: "有阴影", 2: "无阴影", 3: "阴影被覆盖"}
TARGET_REQUIRED = (
    "isStage", "name", "variables", "lists", "broadcasts", "blocks",
    "comments", "currentCostume", "costumes", "sounds", "layerOrder", "volume",
)


class Sb3Error(Exception):
    pass


# ---------------------------------------------------------------- 校验

def check(path):
    """返回 (errors, warnings, info, code)。code: 0 通过 / 1 有错 / 2 打不开。"""
    errors, warnings, info = [], [], []
    if not os.path.isfile(path):
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
    if "project.json" not in names:
        errors.append("根目录缺 project.json（最常见打包错误：把整个文件夹压进去了）")
        z.close()
        return errors, warnings, info, 1
    nested = [n for n in names if "/" in n]
    if nested:
        errors.append("ZIP 根目录出现子目录，素材必须平铺: %s" % nested[:3])

    raw = z.read("project.json")
    if raw.startswith(b"\xef\xbb\xbf"):
        errors.append("project.json 带 UTF-8 BOM，部分工具会乱码")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        errors.append("project.json 不是 UTF-8: %s" % e)
        z.close()
        return errors, warnings, info, 1
    info.append("project.json %d 字节，UTF-8 %s" %
                (len(raw), "无 BOM" if not raw.startswith(b"\xef\xbb\xbf") else "带 BOM"))
    try:
        project = json.loads(text)
    except json.JSONDecodeError as e:
        errors.append("project.json 不是合法 JSON: %s" % e)
        z.close()
        return errors, warnings, info, 1

    for key in ("targets", "monitors", "extensions", "meta"):
        if key not in project:
            errors.append("顶层缺字段 %s" % key)
    meta = project.get("meta", {})
    info.append("meta.semver=%s  vm=%s" % (meta.get("semver"), meta.get("vm")))

    targets = project.get("targets") or []
    if not targets:
        errors.append("targets 为空，Scratch 至少需要舞台")
        z.close()
        return errors, warnings, info, 1
    stages = [t for t in targets if t.get("isStage")]
    if len(stages) != 1:
        errors.append("应有且仅有 1 个舞台，实际 %d 个" % len(stages))
    elif stages[0].get("name") != "Stage":
        errors.append("舞台 name 必须是 'Stage'，实际 %r" % stages[0].get("name"))
    info.append("targets %d 个（舞台 1 + 角色 %d）" %
                (len(targets), len(targets) - len(stages)))

    all_ids = {}
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
                all_ids[vid] = tname
        for c in t.get("costumes") or []:
            _check_asset(z, names, c, tname, "costume", errors, warnings)
        for s in t.get("sounds") or []:
            _check_asset(z, names, s, tname, "sound", errors, warnings)

    total = 0
    for t in targets:
        tname = t.get("name") or "<无名>"
        blocks = t.get("blocks") or {}
        total += len(blocks)
        for bid, b in blocks.items():
            if not isinstance(b, dict):
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
                    errors.append("[%s] %s.inputs.%s 声明被覆盖阴影却缺第 3 项"
                                  % (tname, bid, iname))
                val = inp[1] if len(inp) > 1 else None
                if isinstance(val, list):
                    code = val[0] if val else None
                    if code not in PRIMITIVE_TYPES:
                        errors.append("[%s] %s.inputs.%s 内联类型码 %r 非法（应为 4~13）"
                                      % (tname, bid, iname, code))
                elif isinstance(val, str) and val not in blocks:
                    errors.append("[%s] %s.inputs.%s 引用不存在的积木 %s"
                                  % (tname, bid, iname, val))
                if len(inp) > 2 and isinstance(inp[2], str) and inp[2] not in blocks:
                    warnings.append("[%s] %s.inputs.%s 阴影块 %s 不在 blocks 中"
                                    % (tname, bid, iname, inp[2]))
            for fname, field in (b.get("fields") or {}).items():
                if not isinstance(field, list) or not field:
                    errors.append("[%s] %s.fields.%s 不是数组" % (tname, bid, fname))
    info.append("积木 %d 块，next/parent 链与 inputs 编码已校验" % total)

    for m in project.get("monitors") or []:
        mid = m.get("id")
        if mid and mid not in all_ids:
            warnings.append("monitor %r 的 id 未在任何 target 中声明" % mid)
    exts = set(project.get("extensions") or [])
    info.append("extensions: %s" % (", ".join(sorted(exts)) or "无"))
    z.close()
    return errors, warnings, info, 1 if errors else 0


def _check_asset(z, names, asset, tname, kind, errors, warnings):
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
    fmt = str(asset.get("dataFormat", "")).lower()
    if fmt not in (ext, "jpg" if ext == "jpeg" else ext, "jpeg" if ext == "jpg" else ext):
        errors.append("[%s] dataFormat=%s 与后缀 .%s 不一致" % (label, fmt, ext))
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


# ---------------------------------------------------------------- 概览

def tree(path):
    """返回可打印的概览行列表。"""
    z = zipfile.ZipFile(path)
    project = json.loads(z.read("project.json").decode("utf-8"))
    lines = ["%s  (%d 个 ZIP 条目)" % (os.path.basename(path), len(z.namelist()))]
    for t in project.get("targets", []):
        icon = "舞台" if t.get("isStage") else "角色"
        blocks = t.get("blocks") or {}
        hats = [b.get("opcode") for b in blocks.values()
                if isinstance(b, dict) and b.get("topLevel")]
        lines.append("  [%s] %-20s 积木 %-3d 造型 %-2d 脚本 %d  %s" %
                     (icon, t.get("name", "?"), len(blocks),
                      len(t.get("costumes") or []), len(hats),
                      ", ".join(str(h) for h in hats[:3])))
    assets = [n for n in z.namelist() if n != "project.json"]
    lines.append("  素材 %d 个：%s" % (len(assets), ", ".join(assets[:5]) +
                                    (" …" if len(assets) > 5 else "")))
    z.close()
    return lines


# ---------------------------------------------------------------- 解包 / 打包

def unpack(path, dest):
    """把 sb3 解成可编辑目录。返回写入的文件数。"""
    if os.path.isdir(dest) and os.listdir(dest):
        raise Sb3Error("目标目录非空：%s" % dest)
    os.makedirs(dest, exist_ok=True)
    z = zipfile.ZipFile(path)
    n = 0
    for name in z.namelist():
        if name.endswith("/"):
            continue
        # 防 zip-slip
        target = os.path.abspath(os.path.join(dest, name))
        if not target.startswith(os.path.abspath(dest) + os.sep):
            raise Sb3Error("拒绝越界路径：%s" % name)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "wb") as f:
            f.write(z.read(name))
        n += 1
    z.close()
    return n


def pack(src, out):
    """把目录打包成 sb3：自动重算素材 MD5、平铺、自检。返回报告字符串列表。"""
    pj = os.path.join(src, "project.json")
    if not os.path.isfile(pj):
        raise Sb3Error("目录缺 project.json：%s" % src)
    with open(pj, "rb") as f:
        raw = f.read()
    if raw.startswith(b"\xef\xbb\xbf"):
        raise Sb3Error("project.json 带 BOM，请先去掉")
    project = json.loads(raw.decode("utf-8"))
    renamed = {}
    lines = []
    for t in project.get("targets", []):
        for kind in ("costumes", "sounds"):
            for a in t.get(kind) or []:
                old = a.get("md5ext")
                if not old or not os.path.isfile(os.path.join(src, old)):
                    continue
                with open(os.path.join(src, old), "rb") as f:
                    data = f.read()
                digest = hashlib.md5(data).hexdigest()
                ext = str(a.get("dataFormat") or old.rsplit(".", 1)[-1]).lower()
                new = digest + "." + ext
                a["assetId"] = digest
                a["md5ext"] = new
                renamed[old] = (new, data)
                if old != new:
                    lines.append("  重算 %s → %s" % (old, new))
    data_json = json.dumps(project, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("project.json", data_json)
        for _, (new, data) in renamed.items():
            z.writestr(new, data)
    errors, warnings, info, code = check(out)
    lines.insert(0, "打包 %s → %d 个 ZIP 条目" % (out, 1 + len(renamed)))
    lines += ["  " + x for x in info]
    lines += ["  ⚠ " + w for w in warnings]
    lines += ["  ❌ " + e for e in errors]
    lines.append("  自检：%s" % ("通过" if code == 0 else "未通过"))
    return lines, code


# ---------------------------------------------------------------- 生成最小工程

BACKDROP_SVG = (
    b'<svg xmlns="http://www.w3.org/2000/svg" version="1.1" width="480" height="360" '
    b'viewBox="0 0 480 360"><rect width="480" height="360" fill="#f2f6ff"/>'
    b'<circle cx="240" cy="180" r="120" fill="#e3ecff"/></svg>'
)
COSTUME_SVG = (
    b'<svg xmlns="http://www.w3.org/2000/svg" version="1.1" width="96" height="96" '
    b'viewBox="0 0 96 96"><circle cx="48" cy="48" r="44" fill="#4a90e2"/>'
    b'<circle cx="34" cy="38" r="6" fill="#fff"/><circle cx="62" cy="38" r="6" fill="#fff"/>'
    b'<path d="M30 62 Q48 80 66 62" stroke="#fff" stroke-width="5" fill="none" '
    b'stroke-linecap="round"/></svg>'
)


def make(out):
    """生成一个能直接导入的最小 sb3（舞台 + 角色 + 两段脚本）。"""
    assets = {"backdrop.svg": BACKDROP_SVG, "costume.svg": COSTUME_SVG}
    ids = {name: hashlib.md5(data).hexdigest() for name, data in assets.items()}
    project = {
        "targets": [
            {
                "isStage": True, "name": "Stage", "variables": {}, "lists": {},
                "broadcasts": {}, "blocks": {}, "comments": {}, "currentCostume": 0,
                "costumes": [{"assetId": ids["backdrop.svg"], "name": "backdrop1",
                              "md5ext": ids["backdrop.svg"] + ".svg", "dataFormat": "svg",
                              "bitmapResolution": 1, "rotationCenterX": 240,
                              "rotationCenterY": 180}],
                "sounds": [], "volume": 100, "layerOrder": 0,
                "tempo": 60, "videoTransparency": 50, "videoState": "on",
                "textToSpeechLanguage": "zh-cn",
            },
            {
                "isStage": False, "name": "Sprite1", "variables": {}, "lists": {},
                "broadcasts": {}, "comments": {}, "currentCostume": 0,
                "costumes": [{"assetId": ids["costume.svg"], "name": "costume1",
                              "md5ext": ids["costume.svg"] + ".svg", "dataFormat": "svg",
                              "bitmapResolution": 1, "rotationCenterX": 48,
                              "rotationCenterY": 48}],
                "sounds": [], "volume": 100, "layerOrder": 1,
                "x": 0, "y": 0, "size": 100, "direction": 90, "visible": True,
                "draggable": False, "rotationStyle": "all around",
                "blocks": {
                    "flag1": {"opcode": "event_whenflagclicked", "next": "move1",
                              "parent": None, "inputs": {}, "fields": {}, "shadow": False,
                              "topLevel": True, "x": 50, "y": 50},
                    "move1": {"opcode": "motion_movesteps", "next": "say1",
                              "parent": "flag1", "inputs": {"STEPS": [1, [4, "10"]]},
                              "fields": {}, "shadow": False, "topLevel": False},
                    "say1": {"opcode": "looks_sayforsecs", "next": None,
                             "parent": "move1",
                             "inputs": {"MESSAGE": [1, [10, "你好，Scratch！"]],
                                        "SECS": [1, [4, "2"]]},
                             "fields": {}, "shadow": False, "topLevel": False},
                    "click1": {"opcode": "event_whenthisspriteclicked", "next": "turn1",
                               "parent": None, "inputs": {}, "fields": {}, "shadow": False,
                               "topLevel": True, "x": 50, "y": 180},
                    "turn1": {"opcode": "motion_turnright", "next": None,
                              "parent": "click1", "inputs": {"DEGREES": [1, [4, "15"]]},
                              "fields": {}, "shadow": False, "topLevel": False},
                },
            },
        ],
        "monitors": [], "extensions": [],
        "meta": {"semver": "3.0.0", "vm": "0.2.0", "agent": "github-skills sb3 " + VERSION},
    }
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("project.json",
                   json.dumps(project, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        for name, data in assets.items():
            z.writestr(ids[name] + ".svg", data)
    errors, warnings, info, code = check(out)
    lines = ["生成 %s" % out] + ["  " + x for x in info] + \
            ["  ❌ " + e for e in errors] + \
            ["  自检：%s" % ("通过" if code == 0 else "未通过")]
    return lines, code
