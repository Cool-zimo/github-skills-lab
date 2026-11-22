#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sb3 适配层离线回归：全部本地，不需要 token、不调 GitHub API。

沿用 PR #1 的 Karpathy 思路：每条能力先写一个「故意错」的版本，
确认校验器会拒绝，再确认正确版本会通过。
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
sys.path.insert(0, PKG)
import sb3lib as S  # noqa: E402


def rewrite(src, dst, mutate):
    """复制 sb3 并按 mutate(project, files) 改内容，用于造反例。"""
    z = zipfile.ZipFile(src)
    files = {n: z.read(n) for n in z.namelist()}
    z.close()
    project = json.loads(files['project.json'].decode('utf-8'))
    mutate(project, files)
    files['project.json'] = json.dumps(project, ensure_ascii=False).encode('utf-8')
    with zipfile.ZipFile(dst, 'w', zipfile.ZIP_DEFLATED) as out:
        for n, data in files.items():
            out.writestr(n, data)
    return dst


class TestMakeAndCheck(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='sb3-test-')
        self.sb3 = os.path.join(self.tmp, 'demo.sb3')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_01_make_produces_valid_sb3(self):
        lines, code = S.make(self.sb3)
        self.assertEqual(code, 0, '\n'.join(lines))
        errors, warnings, info, code = S.check(self.sb3)
        self.assertEqual(code, 0, '\n'.join(errors))
        self.assertTrue(any('积木 5 块' in x for x in info))

    def test_02_check_rejects_broken_next(self):
        S.make(self.sb3)
        bad = os.path.join(self.tmp, 'bad.sb3')
        rewrite(self.sb3, bad, lambda p, f: p['targets'][1]['blocks']['move1'].update({'next': '不存在'}))
        errors, _, _, code = S.check(bad)
        self.assertEqual(code, 1)
        self.assertTrue(any('next 指向不存在' in e for e in errors))

    def test_03_check_rejects_parent_mismatch(self):
        S.make(self.sb3)
        bad = os.path.join(self.tmp, 'bad.sb3')
        rewrite(self.sb3, bad, lambda p, f: p['targets'][1]['blocks']['say1'].update({'parent': 'flag1'}))
        errors, _, _, code = S.check(bad)
        self.assertEqual(code, 1)
        self.assertTrue(any('链断裂' in e for e in errors))

    def test_04_check_rejects_missing_asset(self):
        S.make(self.sb3)
        bad = os.path.join(self.tmp, 'bad.sb3')

        def drop(p, f):
            key = p['targets'][0]['costumes'][0]['md5ext']
            f.pop(key)
        rewrite(self.sb3, bad, drop)
        errors, _, _, code = S.check(bad)
        self.assertEqual(code, 1)
        self.assertTrue(any('引用的文件不存在' in e for e in errors))

    def test_05_check_rejects_wrong_md5(self):
        S.make(self.sb3)
        bad = os.path.join(self.tmp, 'bad.sb3')
        rewrite(self.sb3, bad, lambda p, f: p['targets'][1]['costumes'][0].update({'assetId': '0' * 32}))
        errors, _, _, code = S.check(bad)
        self.assertEqual(code, 1)
        self.assertTrue(any('与内容 MD5' in e for e in errors))

    def test_06_check_rejects_nested_root(self):
        S.make(self.sb3)
        bad = os.path.join(self.tmp, 'bad.sb3')
        z = zipfile.ZipFile(self.sb3)
        files = {n: z.read(n) for n in z.namelist()}
        z.close()
        with zipfile.ZipFile(bad, 'w') as out:
            for n, data in files.items():
                out.writestr('build/' + n, data)   # 最常见的打包错误
        errors, _, _, code = S.check(bad)
        self.assertEqual(code, 1)
        self.assertTrue(any('根目录缺 project.json' in e or '根目录出现子目录' in e for e in errors))

    def test_07_check_rejects_bad_primitive_type(self):
        S.make(self.sb3)
        bad = os.path.join(self.tmp, 'bad.sb3')
        rewrite(self.sb3, bad,
                lambda p, f: p['targets'][1]['blocks']['move1']['inputs'].update({'STEPS': [1, [99, '10']]}))
        errors, _, _, code = S.check(bad)
        self.assertEqual(code, 1)
        self.assertTrue(any('类型码' in e for e in errors))

    def test_08_check_rejects_bom(self):
        S.make(self.sb3)
        bad = os.path.join(self.tmp, 'bad.sb3')
        z = zipfile.ZipFile(self.sb3)
        files = {n: z.read(n) for n in z.namelist()}
        z.close()
        files['project.json'] = b'\xef\xbb\xbf' + files['project.json']
        with zipfile.ZipFile(bad, 'w') as out:
            for n, data in files.items():
                out.writestr(n, data)
        errors, _, _, code = S.check(bad)
        self.assertEqual(code, 1)
        self.assertTrue(any('BOM' in e for e in errors))


class TestRoundTrip(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='sb3-test-')
        self.sb3 = os.path.join(self.tmp, 'demo.sb3')
        S.make(self.sb3)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_09_unpack_then_pack_is_valid(self):
        d = os.path.join(self.tmp, 'unpacked')
        n = S.unpack(self.sb3, d)
        self.assertEqual(n, 3)
        out = os.path.join(self.tmp, 'again.sb3')
        lines, code = S.pack(d, out)
        self.assertEqual(code, 0, '\n'.join(lines))
        errors, _, _, code = S.check(out)
        self.assertEqual(code, 0, '\n'.join(errors))

    def test_10_pack_recomputes_md5(self):
        d = os.path.join(self.tmp, 'unpacked')
        S.unpack(self.sb3, d)
        # 故意把素材文件名与 assetId 写坏，pack 应自动重算
        pj = os.path.join(d, 'project.json')
        with open(pj, encoding='utf-8') as f:
            p = json.load(f)
        a = p['targets'][0]['costumes'][0]
        old = a['md5ext']
        a['assetId'] = '0' * 32
        a['md5ext'] = 'wrong.svg'
        os.rename(os.path.join(d, old), os.path.join(d, 'wrong.svg'))
        with open(pj, 'w', encoding='utf-8') as f:
            json.dump(p, f, ensure_ascii=False)
        out = os.path.join(self.tmp, 'fixed.sb3')
        lines, code = S.pack(d, out)
        self.assertEqual(code, 0, '\n'.join(lines))
        self.assertTrue(any('重算' in x for x in lines))
        errors, _, _, code = S.check(out)
        self.assertEqual(code, 0, '\n'.join(errors))

    def test_11_unpack_refuses_nonempty_dir(self):
        d = os.path.join(self.tmp, 'busy')
        os.makedirs(d)
        with open(os.path.join(d, 'x'), 'w') as f:
            f.write('x')
        with self.assertRaises(S.Sb3Error):
            S.unpack(self.sb3, d)

    def test_12_tree_lists_stage_and_sprite(self):
        lines = S.tree(self.sb3)
        text = '\n'.join(lines)
        self.assertIn('[舞台] Stage', text)
        self.assertIn('[角色] Sprite1', text)
        self.assertIn('event_whenflagclicked', text)


class TestCLI(unittest.TestCase):
    """smoke：github sb3 子命令真的挂上了，且不需要 token。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='sb3-cli-')
        # sb3/ 目录自带 github + ghlib.py + sb3lib.py，可独立运行
        self.cli = os.path.join(PKG, 'github')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, *args, anon=False):
        env = os.environ.copy()
        if anon:
            env.pop('GH_TOKENS_FILE', None)
            env['GH_TOKENS_FILE'] = os.path.join(self.tmp, 'no-such-tokens')
        cwd = os.path.dirname(self.cli)
        return subprocess.run([sys.executable, self.cli] + list(args),
                              cwd=cwd, env=env, capture_output=True, text=True, timeout=30)

    def test_13_help_contains_sb3_and_original_commands(self):
        r = self._run('--help')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('sb3', r.stdout)
        self.assertIn('sync', r.stdout)
        self.assertIn('pages', r.stdout)

    def test_14_make_check_tree_roundtrip_cli(self):
        out = os.path.join(self.tmp, 'a.sb3')
        self.assertEqual(self._run('sb3', 'make', out).returncode, 0)
        r = self._run('sb3', 'check', out)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('通过', r.stdout)
        self.assertEqual(self._run('sb3', 'tree', out).returncode, 0)
        d = os.path.join(self.tmp, 'u')
        self.assertEqual(self._run('sb3', 'unpack', out, d).returncode, 0)
        out2 = os.path.join(self.tmp, 'b.sb3')
        self.assertEqual(self._run('sb3', 'pack', d, '-o', out2).returncode, 0)
        self.assertEqual(self._run('sb3', 'check', '--json', out2).returncode, 0)
        # 注意：check 的 --json 在 file 之前，argparse 支持
        self.assertEqual(self._run('sb3', 'guide').returncode, 0)

    def test_15_sb3_works_without_token(self):
        out = os.path.join(self.tmp, 'a.sb3')
        self._run('sb3', 'make', out)
        r = self._run('sb3', 'check', out, anon=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn('❌', r.stdout)

    def test_16_check_json_is_parseable(self):
        out = os.path.join(self.tmp, 'a.sb3')
        self._run('sb3', 'make', out)
        r = self._run('sb3', 'check', out, '--json')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        d = json.loads(r.stdout)
        self.assertTrue(d['ok'])
        self.assertEqual(d['errors'], [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
