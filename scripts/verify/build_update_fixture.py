"""Build a lower-version packaged GUI fixture without changing release sources."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from _bootstrap import setup
ROOT,OUTPUT=setup()
import importlib.util
import subprocess

fixture=OUTPUT/'update-fixture'
fixture.mkdir(parents=True,exist_ok=True)
entry=fixture/'fixture_main.py'
entry.write_text("import core.version\ncore.version.VERSION='0.0.9'\nfrom main_gui import main\nif __name__=='__main__':main()\n",encoding='utf-8')
spec=importlib.util.spec_from_file_location('build_fixture',ROOT/'package-exe/build.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
original=subprocess.check_call

def invoke(args):
    args=list(args)
    args[-1]=str(entry)
    args+=['--paths',str(ROOT)]
    args[args.index('--distpath')+1]=str(fixture/'dist')
    args[args.index('--workpath')+1]=str(fixture/'build')
    args[args.index('--specpath')+1]=str(fixture)
    original(args)

module.subprocess.check_call=invoke
module.build('gui')
