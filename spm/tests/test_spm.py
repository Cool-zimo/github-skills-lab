#!/usr/bin/env python3
"""skillpm 离线回归。零第三方依赖、不联网、不碰真实 token。

    python3 -m unittest discover -s tests -v
"""
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from spmlib import _gh, aliases, config, fetch, sandbox, sources, tokens, versions  # noqa: E402

SPM = os.path.join(ROOT, "spm")


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="spm-test-")
        self.home = os.path.join(self.tmp, "home")
        os.makedirs(self.home)
        self.env = dict(os.environ, SPM_HOME=self.home)
        # 假 token，杜绝碰到真实凭据
        self.token_file = os.path.join(self.tmp, "fake.tokens")
        with open(self.token_file, "w", encoding="utf-8") as f:
            f.write("ghp_FAKE_TOKEN_FOR_TESTS_ONLY\n")
        cfg = config.load(self.home)
        cfg["token_file"] = self.token_file
        config.save(cfg, self.home)
        # 本地源：一个最小 skill
        self.src = os.path.join(self.tmp, "srcdir")
        os.makedirs(self.src)
        with open(os.path.join(self.src, "SKILL.md"), "w", encoding="utf-8") as f:
            f.write("# demo skill\n")
        with open(os.path.join(self.src, "tool.py"), "w", encoding="utf-8") as f:
            f.write("print('hello from skill')\n")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def cli(self, *args, expect=0):
        r = subprocess.run([sys.executable, SPM] + list(args), env=self.env,
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, expect,
                         "cmd=%s\nstdout=%s\nstderr=%s" % (args, r.stdout, r.stderr))
        return r.stdout + r.stderr

    def install(self, version="1.2.0", extra=()):
        return self.cli("install", "demo@" + version, "--from", "path:" + self.src,
                        *extra)


class TestSourceAndUnpack(Base):

    def test_01_parse_four_sources(self):
        self.assertEqual(sources.parse("github:Cool-zimo/github-skills-lab@main:downloads")["type"], "github")
        self.assertEqual(sources.parse("url:https://x.com/a.zip#sha256=abc")["sha256"], "abc")
        self.assertEqual(sources.parse("path:" + self.src)["path"], self.src)
        self.assertEqual(sources.parse("pr:Cool-zimo/github-skills-lab#1")["number"], 1)
        self.assertEqual(sources.parse("pr:Cool-zimo/github-skills-lab#1:downloads")["path"], "downloads")
        with self.assertRaises(sources.SourceError):
            sources.parse("weird://nope")

    def test_02_pr_resolves_to_head_repo(self):
        orig = _gh.req
        calls = []
        def fake(method, path, token, body=None, params=None):
            calls.append(path)
            return 200, {"head": {"repo": {"full_name": "Feng-zimo/github-skills-lab"},
                                  "ref": "feat-v1.3.0", "sha": "abc123"}}
        _gh.req = fake
        try:
            s = sources.resolve_pr({"type": "pr", "repo": "Cool-zimo/github-skills-lab",
                                    "number": 1, "path": "downloads"}, None)
            self.assertEqual(s["repo"], "Feng-zimo/github-skills-lab")
            self.assertEqual(s["ref"], "feat-v1.3.0")
            self.assertEqual(s["pr"], 1)
            self.assertEqual(s["path"], "downloads")
            self.assertIn("/pulls/1", calls[0])
        finally:
            _gh.req = orig

    def test_03_unpack_zip_and_verify(self):
        data = fetch.download(sources.parse("path:" + self.src), None)
        dest = os.path.join(self.tmp, "unpacked")
        m = fetch.unpack(data, dest)
        self.assertEqual(set(m), {"SKILL.md", "tool.py"})
        ok, total, bad = fetch.verify(dest, m)
        self.assertEqual((ok, total, bad), (2, 2, []))

    def test_04_zip_slip_rejected(self):
        import io as _io
        buf = _io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("../../escaped.txt", b"bad")
        with self.assertRaises(fetch.FetchError):
            fetch.unpack(buf.getvalue(), os.path.join(self.tmp, "slip"))

    def test_05_zipball_strips_one_top_dir(self):
        import io as _io
        buf = _io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("owner-repo-sha/README.md", b"hi")
        dest = os.path.join(self.tmp, "zb")
        m = fetch.unpack(buf.getvalue(), dest)
        self.assertEqual(list(m), ["README.md"])

    def test_06_guess_version(self):
        self.assertEqual(fetch.guess_version("github-skills.v.1.3.0.zip"), "1.3.0")
        self.assertIsNone(fetch.guess_version("README.md"))


class TestVersions(Base):

    def test_07_install_two_versions_and_active(self):
        self.install("1.2.0")
        self.install("1.3.0")
        self.assertEqual(versions.versions("demo", self.home), ["1.2.0", "1.3.0"])
        self.assertEqual(versions.active("demo", self.home), "1.2.0")  # 首个自动 active
        versions.set_active("demo", "1.3.0", self.home)
        self.assertEqual(versions.resolve("demo", None, self.home), "1.3.0")
        self.assertEqual(versions.resolve("demo", "1.2.0", self.home), "1.2.0")

    def test_08_versions_are_isolated(self):
        self.install("1.2.0")
        self.install("1.3.0")
        a = versions.root("demo", "1.2.0", self.home)
        b = versions.root("demo", "1.3.0", self.home)
        self.assertNotEqual(a, b)
        with open(os.path.join(a, "ONLY_OLD.txt"), "w") as f:
            f.write("x")
        self.assertFalse(os.path.exists(os.path.join(b, "ONLY_OLD.txt")))

    def test_09_duplicate_install_rejected(self):
        self.install("1.2.0")
        r = subprocess.run([sys.executable, SPM, "install", "demo@1.2.0",
                            "--from", "path:" + self.src], env=self.env,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("已存在", r.stdout + r.stderr)

    def test_10_uninstall_switches_active(self):
        self.install("1.2.0"); self.install("1.3.0")
        versions.set_active("demo", "1.2.0", self.home)
        versions.uninstall("demo", "1.2.0", self.home)
        self.assertEqual(versions.active("demo", self.home), "1.3.0")

    def test_11_safe_mode_blocks_escape(self):
        with self.assertRaises(PermissionError):
            config.assert_inside(self.home, os.path.join(self.tmp, "outside"), "越界路径")
        self.assertTrue(config.inside(self.home, os.path.join(self.home, "demo", "1.2.0")))

    def test_12_bad_names_rejected(self):
        with self.assertRaises(versions.VersionError):
            versions.split("../evil@1.0")
        with self.assertRaises(versions.VersionError):
            versions.split("demo@../../x")


class TestPolicyAndVFS(Base):

    def test_13_untrusted_version_blocks_command(self):
        self.install("1.2.0")
        cfg = config.load(self.home)
        meta = versions.read_meta("demo", "1.2.0", self.home)
        with self.assertRaises(sandbox.SandboxError) as cm:
            sandbox.check_policy(meta, "python3 tool.py", cfg)
        self.assertIn("白名单", str(cm.exception))

    def test_14_allowlist_and_trust(self):
        self.install("1.2.0", extra=("--allow", "python3"))
        cfg = config.load(self.home)
        meta = versions.read_meta("demo", "1.2.0", self.home)
        self.assertEqual(sandbox.check_policy(meta, "python3 tool.py", cfg)[1], "python3")
        with self.assertRaises(sandbox.SandboxError):
            sandbox.check_policy(meta, "rm -rf /", cfg)
        versions.trust("demo", "1.2.0", True, self.home)
        meta2 = versions.read_meta("demo", "1.2.0", self.home)
        sandbox.check_policy(meta2, "node -e 1", cfg)  # trust 后不再受白名单限制

    def test_15_shell_meta_always_rejected(self):
        with self.assertRaises(sandbox.SandboxError):
            sandbox.parse_command("python3 a.py; rm -rf /")
        with self.assertRaises(sandbox.SandboxError):
            sandbox.parse_command("")

    def test_16_vfs_write_does_not_touch_version_root(self):
        self.install("1.2.0")
        f = sandbox.VirtualFS("demo", "1.2.0", self.home)
        self.assertEqual(f.read("SKILL.md"), b"# demo skill\n")
        p = f.write("new.txt", b"written")
        self.assertTrue(os.path.isfile(p))
        self.assertFalse(os.path.exists(os.path.join(f.read_root, "new.txt")))
        self.assertEqual(f.read("new.txt"), b"written")
        self.assertIn("new.txt", f.ls())

    def test_17_vfs_blocks_traversal(self):
        self.install("1.2.0")
        f = sandbox.VirtualFS("demo", "1.2.0", self.home)
        for bad in ("../escape", "/etc/passwd", "a/../../b"):
            with self.assertRaises(sandbox.SandboxError):
                f.resolve(bad)

    def test_18_exec_runs_in_sandbox(self):
        self.install("1.2.0", extra=("--allow", "python3"))
        rc, so, se = sandbox.run("demo", "1.2.0", "python3 tool.py", self.home)
        self.assertEqual(rc, 0)
        self.assertIn("hello from skill", so)

    def test_19_custom_script_global_and_version(self):
        self.install("1.2.0", extra=("--allow", "python3", "--script", "check=python3 tool.py"))
        rc, so, se = sandbox.run_script("demo", "1.2.0", "check", h=self.home)
        self.assertEqual(rc, 0)
        self.assertIn("hello from skill", so)
        cfg = config.load(self.home)
        cfg["scripts"]["hello"] = "python3 tool.py"
        config.save(cfg, self.home)
        rc2, so2, _ = sandbox.run_script("demo", "1.2.0", "hello", h=self.home)
        self.assertEqual(rc2, 0)

    def test_20_mode_plain_disables_vfs(self):
        self.install("1.2.0", extra=("--allow", "python3"))
        versions.mode("demo", "1.2.0", False, self.home)
        meta = versions.read_meta("demo", "1.2.0", self.home)
        self.assertFalse(meta["vfs"])


class TestAliasTokenCLI(Base):

    def test_21_alias_crud_and_expand(self):
        cfg = config.load(self.home)
        aliases.add(cfg, "gs", "exec demo -- python3 tool.py")
        self.assertEqual(aliases.resolve(cfg, "gs", ["--x"])[0], "exec")
        self.assertEqual(aliases.list_all(cfg), [("gs", "exec demo -- python3 tool.py")])
        aliases.remove(cfg, "gs")
        self.assertIsNone(aliases.resolve(cfg, "gs", []))
        with self.assertRaises(aliases.AliasError):
            aliases.add(cfg, "bad alias!", "x")

    def test_22_cli_alias_expansion(self):
        self.install("1.2.0", extra=("--allow", "python3"))
        self.cli("alias", "add", "hi", "run", "demo@1.2.0", "check")
        self.cli("script", "add", "check", "--", "python3", "tool.py")
        txt = self.cli("hi")
        self.assertIn("hello from skill", txt)
        self.assertIn("↪ 别名", txt)

    def test_23_token_sync_never_prints_value(self):
        self.install("1.2.0"); self.install("1.3.0")
        txt = self.cli("token", "sync")
        self.assertNotIn("ghp_FAKE", txt)
        self.assertIn("2 个版本", txt)
        p = os.path.join(versions.root("demo", "1.2.0", self.home), ".spm", "token")
        with open(p, encoding="utf-8") as f:
            self.assertEqual(f.read().strip(), "ghp_FAKE_TOKEN_FOR_TESTS_ONLY")
        st = tokens.status(config.load(self.home), self.home)
        self.assertTrue(st["source"]["exists"])
        self.assertEqual(len(st["targets"]), 2)
        self.assertTrue(all(t.get("same") for t in st["targets"]))
        txt2 = self.cli("token", "status")
        self.assertNotIn("ghp_FAKE", txt2)
        self.assertIn("sha12=", txt2)

    def test_24_verify_detects_tamper(self):
        self.install("1.2.0")
        txt = self.cli("verify", "demo@1.2.0")
        self.assertIn("2/2 一致", txt)
        with open(os.path.join(versions.root("demo", "1.2.0", self.home), "SKILL.md"), "w") as f:
            f.write("tampered")
        r = subprocess.run([sys.executable, SPM, "verify", "demo@1.2.0"],
                           env=self.env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("❌", r.stdout + r.stderr)

    def test_25_cli_full_workflow(self):
        txt = self.cli("doctor")
        self.assertIn("skillpm v1.1.0", txt)
        self.cli("source", "add", "local", "path:" + self.src)
        self.assertIn("local", self.cli("source", "list"))
        self.install("1.2.0")
        self.install("1.3.0")
        self.assertIn("1.2.0", self.cli("list"))
        self.assertIn("1.3.0", self.cli("list"))
        self.cli("use", "demo@1.3.0")
        self.assertIn("1.3.0", self.cli("dir", "demo"))
        self.cli("trust", "demo@1.2.0", "on")
        self.cli("untrust", "demo@1.2.0")
        m = versions.read_meta("demo", "1.2.0", self.home)
        self.assertFalse(m["trusted"])
        self.cli("safe", "on")
        self.cli("mode", "demo@1.3.0", "plain")
        self.cli("allow", "demo@1.3.0", "python3")
        self.cli("vfs", "root", "demo@1.2.0")
        self.cli("vfs", "ls", "demo@1.2.0")
        self.cli("vfs", "put", "demo@1.2.0", "note.txt", "hello-vfs")
        self.assertEqual(self.cli("vfs", "cat", "demo@1.2.0", "note.txt").strip(), "hello-vfs")
        self.cli("uninstall", "demo@1.3.0")
        self.assertEqual(versions.versions("demo", self.home), ["1.2.0"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
