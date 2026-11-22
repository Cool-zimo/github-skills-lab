#!/usr/bin/env python3
"""spm 1.1.0 离线回归：默认从官方包仓库下载、一个源放多个包、可换源。

零第三方依赖、不联网、不碰真实 token。
    python3 -m unittest discover -s tests -v
"""
import importlib.machinery
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from spmlib import config, sources  # noqa: E402

CLI_PATH = os.path.join(ROOT, "spm")
_loader = importlib.machinery.SourceFileLoader("spm_cli_test", CLI_PATH)
_spec = importlib.util.spec_from_loader("spm_cli_test", _loader)
CLI = importlib.util.module_from_spec(_spec)
_loader.exec_module(CLI)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="spm-reg-")
        self.home = os.path.join(self.tmp, "home")
        self.env = dict(os.environ, SPM_HOME=self.home)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestDefaultSource(Base):
    def test_01_default_source_is_package_repo(self):
        cfg = config.load(self.home)
        self.assertEqual(cfg["default_source"], "official")
        s = cfg["sources"]["official"]
        self.assertEqual(s["repo"], "Cool-zimo/spm-packages")
        self.assertEqual(s["path"], "packages")
        self.assertNotIn("pattern", s)      # 靠包名前缀区分，不写死某一种包

    def test_02_old_lab_config_is_migrated(self):
        """仓库改名后，老 home 的 config 不能指向 404 的旧仓。"""
        os.makedirs(self.home)
        old = {
            "version": 1, "safe_mode": True, "default_source": "lab",
            "token_file": "unused", "token_sync_target": ".spm/token",
            "sources": {"lab": {"type": "github", "repo": "Cool-zimo/github-skills-lab",
                                "ref": "main", "path": "downloads",
                                "pattern": "github-skills.v.*.zip"}},
            "aliases": {}, "scripts": {},
        }
        with open(config.config_path(self.home), "w", encoding="utf-8") as f:
            json.dump(old, f)
        cfg = config.load(self.home)
        self.assertEqual(cfg["default_source"], "official")
        self.assertEqual(cfg["sources"]["official"]["repo"], "Cool-zimo/spm-packages")
        # 写回磁盘，下次 load 不重复迁移
        again = json.load(open(config.config_path(self.home), encoding="utf-8"))
        self.assertEqual(again["default_source"], "official")

    def test_03_custom_source_is_not_overwritten(self):
        """用户自己换的源不被迁移逻辑动到。"""
        os.makedirs(self.home)
        old = dict(config.DEFAULT_CONFIG)
        old["default_source"] = "mine"
        old["sources"] = {"mine": {"type": "path", "path": "/tmp/pkgs"}}
        with open(config.config_path(self.home), "w", encoding="utf-8") as f:
            json.dump(old, f)
        cfg = config.load(self.home)
        self.assertEqual(cfg["default_source"], "mine")
        self.assertEqual(cfg["sources"]["mine"]["type"], "path")


class TestPickByPackageName(Base):
    FILES = [
        {"name": "github-skills.v.1.3.2.zip", "path": "packages/github-skills.v.1.3.2.zip",
         "sha": "a", "size": 100, "download_url": ""},
        {"name": "sb3.v.1.0.0.zip", "path": "packages/sb3.v.1.0.0.zip",
         "sha": "b", "size": 200, "download_url": ""},
        {"name": "registry.json", "path": "packages/registry.json",
         "sha": "c", "size": 50, "download_url": ""},
    ]
    SRC = {"type": "github", "repo": "Cool-zimo/spm-packages",
           "ref": "main", "path": "packages"}

    def test_04_pick_github_skills(self):
        with mock.patch.object(sources, "list_github_files", return_value=self.FILES):
            self.assertEqual(CLI._pick_file(self.SRC, "github-skills", None, None, "fake"),
                             "github-skills.v.1.3.2.zip")

    def test_05_pick_sb3(self):
        with mock.patch.object(sources, "list_github_files", return_value=self.FILES):
            self.assertEqual(CLI._pick_file(self.SRC, "sb3", None, None, "fake"),
                             "sb3.v.1.0.0.zip")

    def test_06_version_filter(self):
        with mock.patch.object(sources, "list_github_files", return_value=self.FILES):
            self.assertEqual(CLI._pick_file(self.SRC, "github-skills", "1.3.2", None, "fake"),
                             "github-skills.v.1.3.2.zip")
            with self.assertRaises(Exception):
                CLI._pick_file(self.SRC, "github-skills", "9.9.9", None, "fake")

    def test_07_explicit_pattern_still_wins(self):
        src = dict(self.SRC, pattern="sb3.*.zip")
        with mock.patch.object(sources, "list_github_files", return_value=self.FILES):
            self.assertEqual(CLI._pick_file(src, "github-skills", None, None, "fake"),
                             "sb3.v.1.0.0.zip")

    def test_08_explicit_file_bypasses_prefix(self):
        with mock.patch.object(sources, "list_github_files", return_value=self.FILES):
            self.assertEqual(CLI._pick_file(self.SRC, "sb3", None,
                                            "github-skills.v.1.3.2.zip", "fake"),
                             "github-skills.v.1.3.2.zip")


class TestSwitchSource(Base):
    def test_09_source_use_changes_default(self):
        cfg = config.load(self.home)
        cfg["sources"]["mirror"] = {"type": "path", "path": "/tmp/mirror"}
        config.save(cfg, self.home)
        args = type("A", (), dict(action="use", name="mirror"))()
        with mock.patch.object(CLI, "load", return_value=config.load(self.home)), \
             mock.patch("sys.stdout", new_callable=io.StringIO) as out:
            self.assertEqual(CLI.cmd_source(args), 0)
        self.assertIn("默认源", out.getvalue())
        self.assertEqual(config.load(self.home)["default_source"], "mirror")

    def test_10_source_use_unknown_is_rejected(self):
        args = type("A", (), dict(action="use", name="nope"))()
        with mock.patch("sys.stdout", new_callable=io.StringIO), \
             mock.patch("sys.stderr", new_callable=io.StringIO):
            self.assertEqual(CLI.cmd_source(args), 1)

    def test_11_help_lists_use(self):
        out = io.StringIO()
        with mock.patch("sys.stdout", out):
            try:
                CLI.build_parser().parse_args(["source", "--help"])
            except SystemExit:
                pass
        self.assertIn("use", out.getvalue())


class TestAsVersion(Base):
    def test_12_explicit_as_version_beats_filename_guess(self):
        """path/url 源文件名带版本号时，--as-version 不能被自动探测盖掉。"""
        import subprocess
        import zipfile
        pkgdir = os.path.join(self.tmp, "mirror")
        os.makedirs(pkgdir)
        zp = os.path.join(pkgdir, "demo.v.1.0.0.zip")
        with zipfile.ZipFile(zp, "w") as z:
            z.writestr("demo/SKILL.md", "# demo\n")
            z.writestr("demo/tool.py", "print('ok')\n")
        env = dict(os.environ, SPM_HOME=self.home)
        r = subprocess.run(
            [sys.executable, CLI_PATH, "install", "demo",
             "--from", "path:" + zp, "--as-version", "9.9.9"],
            env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("demo@9.9.9", r.stdout)
        self.assertTrue(os.path.isfile(os.path.join(self.home, "demo", "9.9.9", "SKILL.md")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
