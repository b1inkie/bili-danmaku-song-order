"""Directory refactor regression; no login, live playback or actual PyInstaller build."""
import importlib
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class LayoutTests(unittest.TestCase):
    def test_root_only_has_python_entrypoints(self):
        self.assertEqual({p.name for p in ROOT.glob('*.py')}, {'main.py', 'main_gui.py'})

    def test_modules_import_and_paths_remain_stable(self):
        from core.app_dir import get_app_dir, get_web_dir, get_config_path
        self.assertEqual(Path(get_app_dir()), ROOT)
        self.assertEqual(Path(get_web_dir()), ROOT / 'web')
        self.assertEqual(Path(get_config_path()), ROOT / 'config.json')
        for module in ('main', 'main_gui', 'core.config', 'core.bili_login', 'core.qr_page',
                       'legacy.search', 'legacy.song_handler', 'legacy.lxmusic'):
            importlib.import_module(module)

    def test_theme_tool_from_foreign_cwd(self):
        with tempfile.TemporaryDirectory() as cwd:
            result = subprocess.run([sys.executable, str(ROOT/'tools/theme_tool.py'),
                                     'validate', str(ROOT/'docs/themes/examples/minimal')],
                                    cwd=cwd, capture_output=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))

    def test_packaging_paths_and_imports_without_building(self):
        spec = importlib.util.spec_from_file_location('songdesk_build', ROOT/'package-exe/build.py')
        build = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(build)
        for mode in ('gui', 'console'):
            with patch.object(build, 'install_pyinstaller'), patch.object(build.subprocess, 'check_call') as call:
                build.build(mode)
                args = call.call_args.args[0]
            self.assertTrue(Path(args[-1]).is_file())
            if mode == 'gui':
                self.assertEqual(args[args.index('--name')+1], 'bili-danmaku-song-order')
            for index, value in enumerate(args):
                if value == '--hidden-import':
                    module = args[index+1]
                    if module.startswith(('core', 'legacy')):
                        self.assertIsNotNone(importlib.util.find_spec(module), module)
                if value == '--add-data':
                    import os
                    source, destination = args[index+1].rsplit(os.pathsep, 1)
                    self.assertTrue(Path(source).exists(), source)
                    self.assertIn(destination, ('web', 'docs/themes', 'core'))


    def test_png_icon_generates_windows_sizes_and_preserves_alpha(self):
        from PIL import Image
        spec = importlib.util.spec_from_file_location('songdesk_icon_build', ROOT/'package-exe/build.py')
        build = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(build)
        with tempfile.TemporaryDirectory() as root:
            source = Path(root)/'app-icon.png'
            target = Path(root)/'build/icon.ico'
            self.assertIsNone(build.prepare_icon(source,target))
            Image.new('RGBA',(512,512),(180,60,100,80)).save(source)
            self.assertEqual(build.prepare_icon(source,target),target)
            with Image.open(target) as icon:
                self.assertEqual(icon.format,'ICO')
                self.assertEqual(icon.ico.sizes(), {(x,x) for x in (16,24,32,48,64,128,256)})
                self.assertEqual(icon.convert('RGBA').getpixel((0,0))[3],80)

if __name__ == '__main__':
    unittest.main()
