#!/usr/bin/env python3
"""spm 独立回归：github 源取单文件（>1MB / 空文件 / 长度不符）。零第三方依赖、不联网。

    python3 -m unittest discover -s tests -v
"""
import base64
import hashlib
import os
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from spmlib import sources  # noqa: E402


def blob_sha(data):
    h = hashlib.sha1()
    h.update(("blob %d\0" % len(data)).encode())
    h.update(data)
    return h.hexdigest()


class TestSpmGithubRaw(unittest.TestCase):
    def setUp(self):
        self.big = b"PK\x03\x04" + b"x" * 2000
        self.src = {"type": "github", "repo": "o/r", "path": "downloads", "ref": "main"}

    def _resp(self, **kw):
        base = {"encoding": "none", "content": "", "size": len(self.big),
                "sha": blob_sha(self.big)}
        base.update(kw)
        return base

    def test_05_big_file_goes_through_blob_api(self):
        def fake_req(method, path, token, body=None, params=None):
            if "/git/blobs/" in path:
                return 200, {"content": base64.b64encode(self.big).decode(),
                             "encoding": "base64"}
            return 200, self._resp()

        with mock.patch.object(sources.G, "req", side_effect=fake_req):
            data = sources.github_raw(self.src, "tool.zip", "fake")
        self.assertEqual(data, self.big)         # 旧代码这里是 b""

    def test_06_empty_result_raises_instead_of_silent_empty_package(self):
        """声明有字节却取回 0 字节 → 报错，不静默装空包。"""
        with mock.patch.object(sources.G, "req",
                               return_value=(200, self._resp(size=len(self.big), sha=None))):
            with self.assertRaises(sources.SourceError) as cm:
                sources.github_raw(self.src, "tool.zip", "fake")
        self.assertIn("无 sha", str(cm.exception))

    def test_07_size_mismatch_raises(self):
        def fake_req(method, path, token, body=None, params=None):
            if "/git/blobs/" in path:
                return 200, {"content": base64.b64encode(b"short").decode(),
                             "encoding": "base64"}
            return 200, self._resp()

        with mock.patch.object(sources.G, "req", side_effect=fake_req):
            with self.assertRaises(sources.SourceError) as cm:
                sources.github_raw(self.src, "tool.zip", "fake")
        self.assertIn("字节数不符", str(cm.exception))

    def test_08_zero_byte_file_ok(self):
        with mock.patch.object(sources.G, "req",
                               return_value=(200, {"encoding": "base64", "content": "",
                                                   "size": 0, "sha": blob_sha(b"")})):
            self.assertEqual(sources.github_raw(self.src, ".gitkeep", "fake"), b"")


