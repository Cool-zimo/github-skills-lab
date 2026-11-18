#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成一个可被官方 Scratch 3 编辑器直接导入的最小 .sb3 工程。

要点：
1. .sb3 == ZIP，project.json 与素材必须平铺在 ZIP 根目录；
2. 素材文件名 = assetId + "." + dataFormat，assetId 取素材内容的 MD5；
3. project.json 以 UTF-8 无 BOM 写入；
4. blocks 是图：next / parent 必须双向对齐。
"""
import hashlib
import json
import zipfile
from pathlib import Path
from xml.etree import ElementTree

OUT = Path(__file__).parent
SB3 = OUT / "最小示例.sb3"

# ---------- 素材：一个背景 + 一个角色造型（Scratch 要求 SVG 带 xmlns / viewBox） ----------
BACKDROP_SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="480" height="360" viewBox="0 0 480 360">
  <rect width="480" height="360" fill="#F6F8FC"/>
  <circle cx="80" cy="70" r="34" fill="#FFD5A6"/>
  <path d="M0 300 Q120 250 240 300 T480 292 L480 360 L0 360 Z" fill="#CDE8C4"/>
</svg>
""".encode("utf-8")

COSTUME_SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="96" height="96" viewBox="0 0 96 96">
  <rect x="8" y="8" width="80" height="80" rx="18" fill="#4C97FF" stroke="#3373CC" stroke-width="4"/>
  <circle cx="35" cy="40" r="7" fill="#FFFFFF"/>
  <circle cx="61" cy="40" r="7" fill="#FFFFFF"/>
  <path d="M32 62 Q48 76 64 62" fill="none" stroke="#FFFFFF" stroke-width="5" stroke-linecap="round"/>
</svg>
""".encode("utf-8")


def asset(blob: bytes, ext: str, name: str, cx: float, cy: float) -> tuple[str, dict]:
    """返回 (zip 内文件名, costume/sound 对象)。"""
    asset_id = hashlib.md5(blob).hexdigest()
    md5ext = f"{asset_id}.{ext}"
    meta = {
        "assetId": asset_id,
        "name": name,
        "md5ext": md5ext,
        "dataFormat": ext,
        "rotationCenterX": cx,
        "rotationCenterY": cy,
        "bitmapResolution": 1,
    }
    return md5ext, meta


bg_file, bg_meta = asset(BACKDROP_SVG, "svg", "backdrop1", 240, 180)
sp_file, sp_meta = asset(COSTUME_SVG, "svg", "costume1", 48, 48)
ASSETS = {bg_file: BACKDROP_SVG, sp_file: COSTUME_SVG}

# ---------- 积木：绿旗 -> 移动10步 -> 说"你好"2秒；点击角色 -> 右转15度 ----------
# inputs 第一位：1=阴影(默认 reporters)，2=无阴影，3=阴影被覆盖
# 内联原始值类型码：4 数字 / 10 字符串
blocks = {
    "flagHan": {
        "opcode": "event_whenflagclicked", "next": "move10", "parent": None,
        "inputs": {}, "fields": {}, "shadow": False, "topLevel": True, "x": 60, "y": 60,
    },
    "move10": {
        "opcode": "motion_movesteps", "next": "sayHi", "parent": "flagHan",
        "inputs": {"STEPS": [1, [4, "10"]]},
        "fields": {}, "shadow": False, "topLevel": False,
    },
    "sayHi": {
        "opcode": "looks_sayforsecs", "next": None, "parent": "move10",
        "inputs": {"MESSAGE": [1, [10, "你好，Scratch！"]], "SECS": [1, [4, "2"]]},
        "fields": {}, "shadow": False, "topLevel": False,
    },
    "clickMe": {
        "opcode": "event_whenthisspriteclicked", "next": "turn15", "parent": None,
        "inputs": {}, "fields": {}, "shadow": False, "topLevel": True, "x": 60, "y": 240,
    },
    "turn15": {
        "opcode": "motion_turnright", "next": None, "parent": "clickMe",
        "inputs": {"DEGREES": [1, [4, "15"]]},
        "fields": {}, "shadow": False, "topLevel": False,
    },
}

stage = {
    "isStage": True, "name": "Stage",
    "variables": {}, "lists": {}, "broadcasts": {},
    "blocks": {}, "comments": {},
    "currentCostume": 0, "costumes": [bg_meta], "sounds": [],
    "volume": 100, "layerOrder": 0,
    "tempo": 60, "videoTransparency": 50, "videoState": "on",
}

sprite = {
    "isStage": False, "name": "Sprite1",
    "variables": {}, "lists": {}, "broadcasts": {},
    "blocks": blocks, "comments": {},
    "currentCostume": 0, "costumes": [sp_meta], "sounds": [],
    "volume": 100, "layerOrder": 1,
    "x": 0, "y": 0, "size": 100, "direction": 90,
    "visible": True, "draggable": False, "rotationStyle": "all around",
}

project = {
    "targets": [stage, sprite],
    "monitors": [],
    "extensions": [],
    "meta": {"semver": "3.0.0", "vm": "0.2.0", "agent": "Yuanbao sb3 builder"},
}

project_json = json.dumps(project, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
(OUT / "project.json").write_bytes(project_json)

# ---------- 打包：arcname 就是文件名，不套任何子目录 ----------
with zipfile.ZipFile(SB3, "w", zipfile.ZIP_DEFLATED) as z:
    z.writestr("project.json", project_json)
    for fname, blob in ASSETS.items():
        z.writestr(fname, blob)

# ---------- 自检 ----------
for fname, blob in ASSETS.items():
    if fname.endswith(".svg"):
        root = ElementTree.fromstring(blob)
        assert root.tag.endswith("svg"), f"SVG 根元素非法: {fname}"
        assert "viewBox" in root.attrib, f"SVG 缺 viewBox: {fname}"

with zipfile.ZipFile(SB3) as z:
    names = z.namelist()
    assert "project.json" in names, "根目录缺 project.json"
    assert not any("/" in n for n in names), "ZIP 里多套了一层目录"
    data = json.loads(z.read("project.json").decode("utf-8"))
    for t in data["targets"]:
        assert t["costumes"], f"{t['name']} 没有造型"
        for c in t["costumes"]:
            assert c["md5ext"] in names, f"素材缺失: {c['md5ext']}"
            assert z.read(c["md5ext"]) and hashlib.md5(z.read(c["md5ext"])).hexdigest() == c["assetId"], \
                f"assetId 与内容不符: {c['md5ext']}"
    for t in data["targets"]:
        for bid, b in t["blocks"].items():
            if b["next"]:
                assert b["next"] in t["blocks"], f"{bid} 的 next 指向不存在的块"
                assert t["blocks"][b["next"]]["parent"] == bid, f"{bid} 与 next 的 parent 不一致"
            if b["parent"]:
                assert b["parent"] in t["blocks"], f"{bid} 的 parent 指向不存在的块"

print("OK ->", SB3)
print("ZIP 内容:", names)
print("积木数:", sum(len(t["blocks"]) for t in data["targets"]))
