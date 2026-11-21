# -*- coding: utf-8 -*-
"""语法检查所有改动文件"""
import py_compile
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
files = [str(p) for folder in ('core', 'legacy', 'tests', 'scripts', 'tools', 'package-exe')
         for p in (root / folder).rglob('*.py')]
files += [str(root / name) for name in ('main.py', 'main_gui.py')]
ok = True
for f in files:
    try:
        py_compile.compile(f, doraise=True)
        print("OK  ", f)
    except Exception as e:
        ok = False
        print("FAIL", f, e)
sys.exit(0 if ok else 1)
