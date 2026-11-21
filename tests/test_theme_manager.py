"""Theme format/storage/security regression: no accounts, player or real user data."""
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from PIL import Image
from core.theme_manager import ThemeManager, read_json


def png():
    data = io.BytesIO()
    Image.new('RGBA', (32, 40), (150, 60, 70, 90)).save(data, 'PNG')
    return data.getvalue()


class ThemeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.manager = ThemeManager(Path(self.tmp.name) / 'themes')
        self.minimal = {'schemaVersion': 1, 'id': 'my-first-theme', 'name': '测试主题', 'template': 'rose-nocturne'}

    def tearDown(self):
        self.tmp.cleanup()

    def pack(self, config=None, extra=None):
        path = Path(self.tmp.name) / 'import.songtheme'
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('theme.json', json.dumps(config or self.minimal))
            for name, value in (extra or {}).items():
                info = zipfile.ZipInfo(name)
                info.filename = name  # Windows writer otherwise normalizes backslashes before testing reader.
                archive.writestr(info, value)
        return path

    def test_minimal_defaults(self):
        c = self.manager.validate(self.minimal)
        self.assertEqual(c['layout']['characterRatio'], .43)
        self.assertEqual(c['character']['image'], '')
        self.assertEqual(self.minimal.keys(), {'schemaVersion','id','name','template'})

    def test_invalid_fields_ranges_and_script_paths(self):
        for key, value in [('layout', {'characterRatio': .9}), ('colors', {'accent': 'red;display:none'}),
                           ('character', {'image': 'https://example.com/a.png'}), ('customCSS', 'body{}'),
                           ('schemaVersion', 2), ('name', '')]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.manager.validate({**self.minimal, key: value})

    def test_png_optimized_and_alpha_preserved(self):
        ref = self.manager.optimize_image(png())
        self.assertTrue(ref.endswith('.webp'))
        with Image.open(self.manager._asset(ref)) as image:
            self.assertEqual(image.size, (32,40))
            self.assertEqual(image.getpixel((0,0))[3], 90)
        self.assertEqual(self.manager.optimize_image(png()), ref)

    def test_invalid_image(self):
        for value in (b'<svg><script/></svg>', b'bad image'):
            with self.assertRaises(ValueError): self.manager.optimize_image(value)

    def test_save_export_png_import_roundtrip(self):
        c = copy.deepcopy(self.minimal)
        c['character'] = {'image': 'assets/character.png'}
        result = self.manager.import_pack(self.pack(c, {'assets/character.png': png()}))
        config = result['config']
        self.assertTrue(config['character']['image'].endswith('.webp'))
        self.assertTrue(result['assets'][config['character']['image']].startswith('data:image/webp;base64,'))
        self.manager.select(config['id'])
        self.assertEqual(ThemeManager(self.manager.root).active, config['id'])
        target = Path(self.tmp.name) / 'export.songtheme'
        self.manager.export_pack(config['id'], target)
        with zipfile.ZipFile(target) as archive:
            self.assertEqual(set(archive.namelist()), {'theme.json', config['character']['image']})
        result2 = self.manager.import_pack(target)
        self.assertNotEqual(config['id'], result2['config']['id'])
        self.assertEqual(len(self.manager.catalog()), 2)

    def test_zip_traversal_script_and_missing_assets(self):
        for name in ('../evil.png', 'assets/../../evil.png', '/evil.png', 'assets\\evil.png',
                     'assets/a.js', 'evil.html', 'assets/CON:bad.png'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.manager.import_pack(self.pack(extra={name: b'no'}))
        c = {**self.minimal, 'character': {'image': 'assets/missing.png'}}
        with self.assertRaises(ValueError): self.manager.import_pack(self.pack(c))
        self.assertEqual(self.manager.catalog(), [])

    def test_duplicate_json_keys_rejected(self):
        with self.assertRaises(ValueError): read_json('{"name":"a","name":"b"}')

    def test_state_cache_and_corrupt_fallback(self):
        c = self.manager.validate(self.minimal)
        self.manager.save(c)
        state = self.manager.select(c['id'])
        self.assertIn('payload', state)
        self.assertNotIn('payload', self.manager.state(state['revision']))
        self.assertEqual(self.manager.state(capture=True)['payload']['assets'], {})
        path = self.manager.root / 'installed' / c['id'] / 'theme.json'
        path.write_text('corrupt', encoding='utf-8')
        self.assertEqual(self.manager.state()['id'], 'dark')
        self.assertEqual(ThemeManager(self.manager.root).active, 'dark')

    def test_builtin_and_invalid_ids_cannot_overwrite(self):
        for value in ('haruka', '../escape', 'bad id'):
            with self.assertRaises(ValueError): self.manager.save({**self.minimal,'id':value})
        self.assertEqual(self.manager.select('light')['id'], 'light')

    def test_preview_does_not_save_or_apply(self):
        draft = self.manager.new()
        self.assertEqual(self.manager.catalog(), [])
        self.assertEqual(self.manager.active, 'dark')
        self.assertEqual(draft['config']['character']['image'], '')
        self.assertEqual(draft['assets'], {})
        expected = {'name':'这里是名字','signature':'这里是签名','heading':'这里是主标题',
                    'subtitle':'这里是副标题','eyebrow':'这里是引导语','motto':'这里是签名说明',
                    'vertical':'这里是竖排文案','sceneTitle':'这里是主题名'}
        for key, value in expected.items():
            self.assertEqual(draft['config']['text'][key], value)
        self.assertNotIn('渚花遥', json.dumps(draft, ensure_ascii=False))
        defaults = self.manager.validate(self.minimal)['text']
        for key in ('name','signature','heading','subtitle','eyebrow','motto'):
            self.assertEqual(defaults[key], expected[key])


    def test_save_active_draft_requires_explicit_apply(self):
        c = self.manager.validate(self.minimal)
        self.manager.save(c)
        before = self.manager.select(c['id'])
        c['text']['heading'] = '修改但未应用'
        self.manager.save(c)
        self.assertEqual(self.manager.state()['revision'], before['revision'])
        self.assertNotEqual(self.manager.state()['payload']['config']['text']['heading'], c['text']['heading'])
        self.assertNotEqual(ThemeManager(self.manager.root).state()['payload']['config']['text']['heading'], c['text']['heading'])
        self.assertEqual(self.manager.select(c['id'])['payload']['config']['text']['heading'], c['text']['heading'])

    def test_nonfinite_and_oversized_json_rejected(self):
        with self.assertRaises(ValueError):
            self.manager.validate({**self.minimal, 'character': {'scale': float('nan')}})
        with self.assertRaises(ValueError):
            self.manager.validate({**self.minimal, 'description': 'a' * 140000})

    def test_workshop_dialog_png_import_export(self):
        from unittest.mock import Mock
        from core.theme_workshop import WorkshopApi
        source = Path(self.tmp.name) / '用户不需要转格式.png'
        source.write_bytes(png())
        api = WorkshopApi(self.manager)
        api._window = Mock()
        api._window.create_file_dialog.return_value = [str(source)]
        image = api.choose_image()
        self.assertTrue(image['path'].endswith('.webp'))
        c = {**self.minimal, 'character': {'image': image['path']}}
        api.save_theme(c)
        output = Path(self.tmp.name) / 'sharing.songtheme'
        api._window.create_file_dialog.return_value = str(output)
        self.assertTrue(api.export_theme(c['id']))
        self.assertTrue(output.is_file())
        api._window.create_file_dialog.return_value = [str(output)]
        self.assertNotEqual(api.import_theme()['config']['id'], c['id'])
        api._window.create_file_dialog.return_value = None
        self.assertIsNone(api.choose_image())
        self.assertIsNone(api.import_theme())
        self.assertFalse(api.export_theme(c['id']))

    def test_archive_duplicate_symlink_and_file_count(self):
        import warnings
        path = Path(self.tmp.name) / 'bad.zip'
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            with zipfile.ZipFile(path, 'w') as archive:
                archive.writestr('theme.json', json.dumps(self.minimal))
                archive.writestr('theme.json', json.dumps(self.minimal))
        with self.assertRaises(ValueError): self.manager.import_pack(path)
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('theme.json', json.dumps(self.minimal))
            info = zipfile.ZipInfo('assets/link.png')
            info.create_system = 3
            info.external_attr = (0o120777 << 16)
            archive.writestr(info, 'outside.png')
        with self.assertRaises(ValueError): self.manager.import_pack(path)
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('theme.json', json.dumps(self.minimal))
            for index in range(64): archive.writestr(f'assets/a{index}.png', b'')
        with self.assertRaises(ValueError): self.manager.import_pack(path)

    def test_copy_prompt_is_self_contained_and_example_imports(self):
        import re
        from core.theme_workshop import WorkshopApi
        from unittest.mock import Mock
        api = WorkshopApi(self.manager)
        api._copy_text = Mock()
        result = api.copy_theme_guide()
        text = api._copy_text.call_args.args[0]
        self.assertTrue(result['copied'])
        self.assertEqual(result['characters'], len(text))
        self.assertLess(len(text), 6500)
        for part in ('你不需要程序源码', '具体做法', 'assets/character.png', 'ZIP 根目录', '保存并应用', '一个主题一个文件夹', '相对本主题文件夹'):
            self.assertIn(part, text)
        for part in ('sceneNumber', 'sectionNumber', 'background', 'fontSize', 'compact', '300×280', '无需另做小窗包', '不能只将JSON改后缀'):
            self.assertIn(part, text)
        for part in ('docs/themes/', 'theme_tool.py', 'pip install', 'JSON Schema', '{{THEME_JSON}}', str(self.manager.root)):
            self.assertNotIn(part, text)
        blocks = re.findall(r'```json\n(.*?)\n```', text, re.S)
        self.assertEqual(len(blocks), 1)
        config = json.loads(blocks[0])
        normalized = self.manager.validate(config)
        self.assertEqual(config, normalized, 'prompt example must include all defaults')
        def compare_fields(value, schema):
            self.assertEqual(set(value), set(schema['properties']))
            for key, spec in schema['properties'].items():
                if spec.get('type') == 'object': compare_fields(value[key], spec)
        compare_fields(config, self.manager.schema)
        imported = self.manager.import_pack(self.pack(config, {'assets/character.png': png()}))
        self.assertEqual(imported['config']['id'], 'my-music-room')
        self.assertNotIn('渚花遥', text)
        self.assertNotIn('haruka', config['text']['signature'].lower())
        config=imported['config']  # use normalized image references returned by real import
        config['capture']={'background':'#142536','card':'#263748','fontSize':18,'compact':True}
        self.manager.save(config)
        target=Path(self.tmp.name)/'prompt-roundtrip.songtheme'
        self.manager.export_pack(config['id'],target)
        recipient=ThemeManager(Path(self.tmp.name)/'recipient')
        delivered=recipient.import_pack(target)['config']
        self.assertEqual(delivered['capture'],config['capture'])
        recipient.select(delivered['id'])
        self.assertEqual(recipient.state(capture=True)['payload']['config']['capture'],config['capture'])

    def test_delete_active_theme_falls_back_and_keeps_other_theme_images(self):
        reference = self.manager.optimize_image(png())
        first = {**self.minimal, 'character': {'image': reference}}
        second = {**first, 'id': 'another-theme'}
        self.manager.save(first)
        self.manager.save(second)
        self.manager.select(first['id'])
        result = self.manager.delete(first['id'])
        self.assertEqual(result['deleted'], first['id'])
        self.assertEqual(result['id'], 'dark')
        self.assertEqual(self.manager.active, 'dark')
        self.assertIsNone(self.manager._applied_config)
        self.assertEqual(ThemeManager(self.manager.root).active, 'dark')
        self.assertEqual([x['id'] for x in self.manager.catalog()], ['another-theme'])
        self.assertFalse((self.manager.root / 'installed' / first['id']).exists())
        self.assertTrue(self.manager._asset(reference, 'another-theme').is_file())
        self.assertEqual(self.manager.load('another-theme')['character']['image'], reference)

    def test_delete_inactive_theme_preserves_current_selection(self):
        self.manager.save(self.minimal)
        other = {**self.minimal, 'id': 'another-theme'}
        self.manager.save(other)
        before = self.manager.select(other['id'])
        self.manager.delete(self.minimal['id'])
        self.assertEqual(self.manager.state(), before)
        for value in ('dark', 'light', 'haruka', '../escape', 'missing-theme'):
            with self.assertRaises(ValueError): self.manager.delete(value)
        self.assertEqual(self.manager.active, other['id'])

    def test_delete_does_not_remove_unrelated_files(self):
        self.manager.save(self.minimal)
        folder = self.manager.root / 'installed' / self.minimal['id']
        unrelated = folder / 'keep.txt'
        unrelated.write_text('not a theme file', encoding='utf-8')
        self.manager.delete(self.minimal['id'])
        self.assertTrue(unrelated.is_file())
        self.assertFalse((folder / 'theme.json').exists())

    def test_decorative_text_defaults_and_pack_roundtrip(self):
        keys = ('vertical','sceneNumber','sceneTitle','sectionNumber')
        old = self.manager.validate(self.minimal)
        self.assertEqual({key:old['text'][key] for key in keys}, dict.fromkeys(keys,''))
        values = dict(zip(keys, ('VIOLET · MUSIC','02','BLACK LOTUS','B')))
        config = {**self.minimal,'text':values,'fonts':{'sceneTitle':'Georgia'}}
        self.manager.save(config)
        target = Path(self.tmp.name) / 'decoration.songtheme'
        self.manager.export_pack(config['id'], target)
        imported = self.manager.import_pack(target)['config']
        self.assertEqual({key:imported['text'][key] for key in keys}, values)
        self.assertEqual(imported['fonts']['sceneTitle'],'Georgia')
        with self.assertRaises(ValueError):
            self.manager.validate({**self.minimal,'text':{'sceneNumber':'x'*13}})

    def test_per_text_fonts_defaults_save_and_export(self):
        old = self.manager.validate(self.minimal)
        self.assertEqual(old['fonts'], dict.fromkeys(self.manager.schema['properties']['text']['properties'], ''))
        config = {**self.minimal, 'fonts': {'name':'华文行楷','heading':'Arial','signature':'Missing Custom Font'}}
        self.manager.save(config)
        loaded = self.manager.load(config['id'])
        self.assertEqual(loaded['fonts']['heading'], 'Arial')
        self.assertEqual(loaded['fonts']['subtitle'], '')
        target = Path(self.tmp.name) / 'font-theme.songtheme'
        self.manager.export_pack(config['id'], target)
        imported = self.manager.import_pack(target)['config']
        self.assertEqual(imported['fonts'], loaded['fonts'])
        for bad in ({'unknown':'Arial'}, {'heading':'a\nb'}, {'heading':'a'*101}):
            with self.assertRaises(ValueError): self.manager.validate({**self.minimal, 'fonts':bad})

    def test_preset_edit_export_delete_does_not_resurrect(self):
        from core.theme_manager import BUILTINS
        preset = 'black-lotus-violet-resonance'
        self.assertEqual(BUILTINS, ('dark', 'light'))
        manager = ThemeManager(self.manager.root, install_presets=True)
        bundled = {'black-lotus-violet-resonance', 'strelizia-twilight-resonance'}
        self.assertEqual({x['id'] for x in manager.catalog()}, bundled)
        config = manager.load(preset)
        config['text']['heading'] = '已编辑预设'
        manager.save(config)
        manager.select(preset)
        reloaded = ThemeManager(manager.root, install_presets=True)
        self.assertEqual(reloaded.load(preset)['text']['heading'], '已编辑预设')
        self.assertEqual(reloaded.active, preset)
        exported = Path(self.tmp.name) / 'preset.songtheme'
        reloaded.export_pack(preset, exported)
        self.assertTrue(exported.is_file())
        reloaded.delete(preset)
        restarted = ThemeManager(manager.root, install_presets=True)
        self.assertEqual(restarted.active, 'dark')
        self.assertEqual({x['id'] for x in restarted.catalog()}, bundled - {preset})

    def test_old_haruka_selection_does_not_seed_removed_preset(self):
        self.manager.root.mkdir(parents=True)
        (self.manager.root / 'selection.json').write_text(json.dumps({'active':'haruka'}), encoding='utf-8')
        migrated = ThemeManager(self.manager.root, install_presets=True)
        self.assertEqual(migrated.active, 'dark')
        self.assertNotIn('preset-haruka', {x['id'] for x in migrated.catalog()})

    def test_existing_haruka_is_preserved_without_initial_install(self):
        config = self.manager.new()['config']
        config['id'] = 'preset-haruka'
        self.manager.save(config)
        self.manager.select(config['id'])
        existing = ThemeManager(self.manager.root, install_presets=True)
        self.assertEqual(existing.active, 'preset-haruka')
        self.assertEqual(existing.load('preset-haruka')['name'], config['name'])

    def test_background_transform_defaults_and_roundtrip(self):
        default = self.manager.validate(self.minimal)['background']
        self.assertEqual((default['scale'], default['x'], default['y']), (1, 0, 0))
        config = {**self.minimal, 'background': {'scale':1.5, 'x':120, 'y':-80}}
        self.manager.save(config)
        target = Path(self.tmp.name) / 'background.songtheme'
        self.manager.export_pack(config['id'], target)
        loaded = self.manager.import_pack(target)['config']['background']
        self.assertEqual((loaded['scale'], loaded['x'], loaded['y']), (1.5,120,-80))
        for invalid in ({'scale':0}, {'scale':3.1}, {'x':1001}, {'y':-1001}):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                self.manager.validate({**self.minimal, 'background':invalid})

    def test_independent_folders_can_be_copied_without_shared_assets(self):
        import shutil
        ref = self.manager.optimize_image(png())
        first = {**self.minimal, 'character': {'image': ref}}
        self.manager.save(first)
        self.manager.save({**first, 'id':'another-theme'})
        one = self.manager._asset(ref, first['id'])
        two = self.manager._asset(ref, 'another-theme')
        self.assertNotEqual(one, two)
        self.assertFalse((self.manager.root / 'assets').exists())
        portable = Path(self.tmp.name) / 'standalone'
        shutil.copytree(one.parent.parent, portable / 'installed' / first['id'])
        fresh = ThemeManager(portable)
        self.assertTrue(fresh.payload(fresh.load(first['id']))['assets'])
        self.manager.delete(first['id'])
        self.assertFalse(one.parent.parent.exists())
        self.assertTrue(two.exists())
        target = Path(self.tmp.name) / 'other.songtheme'
        self.manager.export_pack('another-theme', target)
        with zipfile.ZipFile(target) as archive:
            self.assertEqual(set(archive.namelist()), {'theme.json',ref})

    def test_legacy_shared_assets_migrate_including_applied_snapshot(self):
        root = self.manager.root
        old = root / 'assets/character.png'
        old.parent.mkdir(parents=True)
        old.write_bytes(png())
        applied = root / 'assets/applied.png'
        applied.write_bytes(png())
        first = self.manager.validate({**self.minimal,'character':{'image':'assets/character.png'}})
        for config in (first, {**first,'id':'another-theme'}):
            path = root / 'installed' / config['id'] / 'theme.json'
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(config),encoding='utf-8')
        snapshot = copy.deepcopy(first)
        snapshot['character']['image']='assets/applied.png'
        (root / 'selection.json').write_text(json.dumps({'active':first['id'],'config':snapshot}),encoding='utf-8')
        migrated = ThemeManager(root)
        self.assertEqual(migrated.active,first['id'])
        for theme in (first['id'],'another-theme'):
            self.assertTrue(migrated._asset('assets/character.png',theme).exists())
        self.assertTrue(migrated._asset('assets/applied.png',first['id']).exists())
        self.assertTrue(migrated.state()['payload']['assets'])
        self.assertTrue(old.exists(),'migration must retain original backup')
        # Once migrated, missing local images must NOT silently resurrect from old shared data.
        migrated._asset('assets/character.png','another-theme').unlink()
        restarted=ThemeManager(root)
        with self.assertRaises(ValueError):restarted.load('another-theme')

    def test_same_filename_different_themes_do_not_collide_when_copied(self):
        for theme,color in [('one-theme','red'),('two-theme','blue')]:
            directory=self.manager.root/'installed'/theme
            (directory/'assets').mkdir(parents=True)
            Image.new('RGBA',(32,40),color).save(directory/'assets/character.png')
            config={**self.minimal,'id':theme,'character':{'image':'assets/character.png'}}
            (directory/'theme.json').write_text(json.dumps(config),encoding='utf-8')
        a=self.manager.payload(self.manager.load('one-theme'))
        b=self.manager.payload(self.manager.load('two-theme'))
        self.assertNotEqual(a['config']['character']['image'],b['config']['character']['image'])
        a['config']['id']='copied-theme'
        self.manager.save(a['config'])
        image=self.manager._asset(a['config']['character']['image'],'copied-theme')
        with Image.open(image) as source:self.assertEqual(source.getpixel((0,0)),(255,0,0,255))

    def test_workshop_open_directory_and_delete_bridge(self):
        from core.theme_workshop import WorkshopApi
        from unittest.mock import patch
        api = WorkshopApi(self.manager)
        with patch('os.startfile') as opened:
            directory = api.open_theme_directory()
            self.assertEqual(directory, str(self.manager.root / 'installed'))
            self.assertTrue(Path(directory).is_dir())
            opened.assert_called_once_with(directory)
        self.manager.save(self.minimal)
        self.manager.select(self.minimal['id'])
        self.assertEqual(api.delete_theme(self.minimal['id'])['id'], 'dark')
        self.assertFalse(self.manager.catalog())
        with self.assertRaises(ValueError): api.delete_theme('dark')

    def test_workshop_window_actions_and_resize_validation(self):
        from core.theme_workshop import WorkshopApi
        from unittest.mock import Mock
        api = WorkshopApi(self.manager)
        api._window = Mock()
        api.window_action('minimize')
        api._window.minimize.assert_called_once()
        api.window_action('close')
        api._window.destroy.assert_called_once()
        with self.assertRaises(ValueError): api.window_action('arbitrary')
        api.resize_window(1000,700,'se')
        api._window.resize.assert_called_once()
        for args in ((900,700,'se'),(1000,600,'se'),(1000,700,'bad')):
            with self.subTest(args=args), self.assertRaises(ValueError): api.resize_window(*args)

    def test_new_presets_install_on_upgrade_without_restoring_deleted_haruka(self):
        root = self.manager.root
        root.mkdir(parents=True, exist_ok=True)
        (root / 'presets-v1.json').write_text(json.dumps({'installed':['preset-haruka']}), encoding='utf-8')
        manager = ThemeManager(root, install_presets=True)
        expected = {'black-lotus-violet-resonance', 'strelizia-twilight-resonance'}
        self.assertEqual({x['id'] for x in manager.catalog()}, expected)
        for theme_id in expected:
            config = manager.load(theme_id)
            self.assertTrue(manager.payload(config)['assets'])
            manager.delete(theme_id)
        self.assertEqual(ThemeManager(root, install_presets=True).catalog(), [])

if __name__ == '__main__': unittest.main()
