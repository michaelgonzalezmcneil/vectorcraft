"""Behavioral checks for the original Loomwell workflow add-on."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('loomwell_vector_export', HERE / 'export.py')
exporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exporter)


class ExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cli = exporter.find_cli(os.environ.get('VECTORCRAFT_CLI'))
        cls.temporary = tempfile.TemporaryDirectory(prefix='loomwell-vector-tests-')
        cls.output = Path(cls.temporary.name) / 'exports'
        subprocess.run([sys.executable, str(HERE / 'export.py'), 'export', 'all',
                        '--output', str(cls.output), '--cli', cls.cli], check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_export_sizes_fonts_live_text_and_declared_digests(self):
        manifest = json.loads((self.output / 'manifest.json').read_text())
        for filename, digest in manifest['files'].items():
            self.assertEqual(hashlib.sha256((self.output / filename).read_bytes()).hexdigest(), digest)
        for name, dimensions in [('website', (1600, 900)), ('social', (1200, 630)), ('square', (1080, 1080))]:
            image = (self.output / (name + '.png')).read_bytes()
            self.assertEqual(struct.unpack('>II', image[16:24]), dimensions)
            info = json.loads(subprocess.check_output([self.cli, 'info', str(self.output / (name + '.vectorcraft'))]))
            self.assertGreater(info['kinds']['Type'], 0)
            self.assertTrue(all(font['status'] == 'exact' and font['missingGlyphs'] == 0 for font in info['fonts']))
        palette = json.loads((self.output / 'loomwell.vcswatches').read_text())
        self.assertEqual(len(palette['groups'][0]['swatches']), 4)
        self.assertTrue(all(swatch['global'] for swatch in palette['groups'][0]['swatches']))

    def test_native_master_reopens_to_identical_png(self):
        reopened = self.output / 'reopened.png'
        subprocess.run([self.cli, 'convert', str(self.output / 'social.vectorcraft'), str(reopened)],
                       check=True, capture_output=True)
        self.assertEqual(reopened.read_bytes(), (self.output / 'social.png').read_bytes())

    def test_pack_runs_from_an_independent_copy_with_explicit_cli(self):
        copied = Path(self.temporary.name) / 'standalone' / 'loomwell'
        shutil.copytree(HERE, copied, ignore=shutil.ignore_patterns('__pycache__'))
        custom = copied.parent / 'custom.json'
        custom.write_text(json.dumps({'headline': 'Context & correction.\nUseful examples.'}))
        target = copied.parent / 'result'
        subprocess.run([sys.executable, str(copied / 'export.py'), 'export', 'social', '--output',
                        str(target), '--content', str(custom), '--cli', self.cli], check=True, capture_output=True)
        self.assertIn('Context &amp; correction.', (target / 'social.source.svg').read_text())
        self.assertTrue((target / 'social.vectorcraft').is_file())

    def test_oversized_or_unknown_content_fails_before_output(self):
        for payload in ({'headline': 'a'*25}, {'unexpected': 'value'}):
            custom = Path(self.temporary.name) / 'invalid.json'
            custom.write_text(json.dumps(payload))
            output = Path(self.temporary.name) / 'should-not-exist'
            result = subprocess.run([sys.executable, str(HERE / 'export.py'), 'export', 'social',
                                     '--output', str(output), '--content', str(custom), '--cli', self.cli],
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(output.exists())
            self.assertNotIn('Traceback', result.stderr)

    def test_wide_glyph_overflow_preserves_previous_delivery(self):
        # This fits the character budget but exceeds the real bundled-font column width.
        custom = Path(self.temporary.name) / 'wide.json'
        custom.write_text(json.dumps({'headline': 'W'*24}))
        previous_png = (self.output / 'social.png').read_bytes()
        previous_manifest = (self.output / 'manifest.json').read_bytes()
        result = subprocess.run([sys.executable, str(HERE / 'export.py'), 'export', 'social',
                                 '--output', str(self.output), '--content', str(custom), '--cli', self.cli],
                                capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('safe area', result.stderr)
        self.assertEqual((self.output / 'social.png').read_bytes(), previous_png)
        self.assertEqual((self.output / 'manifest.json').read_bytes(), previous_manifest)


if __name__ == '__main__':
    unittest.main()
