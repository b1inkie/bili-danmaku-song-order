"""黑名单英文文件名、旧数据迁移与冻结程序路径，不读写真实用户黑名单。"""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from core.app_dir import get_blacklist_path, get_config_path
from core.config import create_config
from core.settings import Settings


class BlacklistPathTests(unittest.TestCase):
    def test_legacy_is_renamed_without_changing_bytes(self):
        with tempfile.TemporaryDirectory() as root, patch('core.app_dir.get_app_dir', return_value=root):
            legacy = Path(root) / '.A歌曲黑名单.txt'
            original = '原有歌曲\r\n另一首\n'.encode('utf-8')
            legacy.write_bytes(original)
            target = Path(get_blacklist_path())
            self.assertEqual(target.name, 'song_blacklist.txt')
            self.assertEqual(target.read_bytes(), original)
            self.assertFalse(legacy.exists())
            self.assertEqual(Settings().get_blacklist(), {'原有歌曲', '另一首'})
            self.assertEqual(get_blacklist_path(), str(target))

    def test_existing_english_file_wins_without_overwrite(self):
        with tempfile.TemporaryDirectory() as root, patch('core.app_dir.get_app_dir', return_value=root):
            legacy = Path(root) / '.A歌曲黑名单.txt'
            target = Path(root) / 'song_blacklist.txt'
            legacy.write_text('旧名单', encoding='utf-8')
            target.write_text('当前名单', encoding='utf-8')
            self.assertEqual(get_blacklist_path(), str(target))
            self.assertEqual(target.read_text('utf-8'), '当前名单')
            self.assertEqual(legacy.read_text('utf-8'), '旧名单')

    def test_fresh_config_uses_only_english_blacklist(self):
        with tempfile.TemporaryDirectory() as root, patch('core.app_dir.get_app_dir', return_value=root):
            create_config()
            self.assertEqual({p.name for p in Path(root).iterdir()}, {'config.json', 'song_blacklist.txt'})
            self.assertEqual(Settings().get_blacklist(), {'义勇军进行曲', '威风堂堂'})

    def test_gui_initialization_seeds_once_and_respects_user_removal(self):
        with tempfile.TemporaryDirectory() as root, patch('core.app_dir.get_app_dir', return_value=root):
            settings = Settings()
            self.assertEqual(settings.get_blacklist_text(), '义勇军进行曲\n威风堂堂\n')
            settings.set_blacklist(['威风堂堂'])
            self.assertEqual(Settings().get_blacklist(), {'威风堂堂'})
            settings.set_blacklist([])
            create_config()
            self.assertEqual(Settings().get_blacklist(), set())
            self.assertEqual(Path(get_blacklist_path()).read_bytes(), b'')

    def test_frozen_files_live_next_to_exe_not_meipass_or_cwd(self):
        with tempfile.TemporaryDirectory() as root:
            binary = Path(root) / 'release' / 'bili-danmaku-song-order.exe'
            binary.parent.mkdir()
            with patch.object(sys, 'frozen', True, create=True), \
                 patch.object(sys, 'executable', str(binary)), \
                 patch.object(sys, '_MEIPASS', str(Path(root) / 'unpacked'), create=True):
                self.assertEqual(Path(get_blacklist_path()), binary.parent / 'song_blacklist.txt')
                self.assertEqual(Path(get_config_path()), binary.parent / 'config.json')

    def test_permission_error_is_not_silently_ignored(self):
        with tempfile.TemporaryDirectory() as root, patch('core.app_dir.get_app_dir', return_value=root):
            (Path(root) / '.A歌曲黑名单.txt').write_text('旧名单', encoding='utf-8')
            with patch('core.app_dir.os.rename', side_effect=PermissionError('read only')):
                with self.assertRaises(PermissionError):
                    get_blacklist_path()
            self.assertFalse((Path(root) / 'song_blacklist.txt').exists())


if __name__ == '__main__':
    unittest.main()
