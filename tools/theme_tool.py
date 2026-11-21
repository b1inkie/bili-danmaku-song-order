"""Data-only theme tools for users/AI. Never touches installed user themes.
python tools/theme_tool.py validate path/to/theme.json
python tools/theme_tool.py validate path/to/theme.songtheme
python tools/theme_tool.py pack path/to/theme-directory output.songtheme
"""
if __package__:
    from ._bootstrap import setup
else:
    from _bootstrap import setup
setup()
import argparse
import json
from pathlib import Path
import tempfile
import zipfile
from core.theme_manager import ThemeManager, IMAGE_PATH


def source_pack(source, destination):
    source = Path(source)
    if not source.is_dir():
        return source
    files = list(source.rglob('*'))
    if any(p.is_symlink() for p in files):
        raise ValueError('主题目录不能包含符号链接')
    with zipfile.ZipFile(destination, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            if path.is_file():
                archive.write(path, path.relative_to(source).as_posix())
    return destination


def main():
    parser = argparse.ArgumentParser(description='点歌台主题v1校验与打包（不更改当前主题）')
    sub = parser.add_subparsers(dest='command', required=True)
    check = sub.add_parser('validate', help='校验JSON格式、目录或完整ZIP主题包')
    check.add_argument('source')
    check.add_argument('--normalized', action='store_true', help='打印补全默认值的配置')
    pack = sub.add_parser('pack', help='校验目录并优化素材，生成可导入主题包')
    pack.add_argument('source')
    pack.add_argument('output')
    args = parser.parse_args()
    try:
        with tempfile.TemporaryDirectory() as temporary:
            manager = ThemeManager(Path(temporary) / 'themes')
            source = Path(args.source)
            if source.suffix.lower() == '.json' and args.command == 'validate':
                from core.theme_manager import read_json
                config = manager.validate(read_json(source.read_text('utf-8-sig')))
                print('PASS: JSON字段/范围/默认值有效（素材完整性请校验目录或主题包）')
            else:
                archive = source_pack(source, Path(temporary) / 'source.zip')
                config = manager.import_pack(archive)['config']
                print('PASS: 主题配置、路径、素材及导入有效')
                if args.command == 'pack':
                    manager.export_pack(config['id'], args.output)
                    print('已生成：' + str(Path(args.output).resolve()))
            if getattr(args, 'normalized', False):
                print(json.dumps(config, ensure_ascii=False, indent=2))
    except Exception as exc:
        parser.exit(1, 'FAIL: ' + str(exc) + '\n')


if __name__ == '__main__': main()
