"""Validate the bundled Windows/Python runtime before opening the local UI."""
from pathlib import Path
import platform
import struct
import subprocess
import sys

BASE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True

def check_runtime():
    if sys.version_info[:2] != (3, 12) or struct.calcsize('P') != 8 or sys.platform != 'win32':
        raise RuntimeError('Can Python 3.12 Windows 64-bit de dung cac thu vien di kem. '
                           'Cai Python 3.12 64-bit (bao gom Tcl/Tk), sau do chay lai Start Local.cmd.')
    sys.path.insert(0, str(BASE / 'vendor'))
    try:
        import tkinter
        import yaml
        from PIL import Image
    except (ImportError, OSError) as error:
        raise RuntimeError('Thieu Tkinter hoac thu vien trong folder vendor. '
                           'Giu nguyen toan bo folder cong cu khi copy. Chi tiet: ' + str(error)) from error
    import json
    manifest = BASE / 'plugin' / 'manifest.json'
    if not manifest.is_file():
        raise RuntimeError('Thieu plugin/manifest.json. Copy lai folder cong cu day du; khong can New plugin.')
    data = json.loads(manifest.read_text(encoding='utf-8-sig'))
    if data.get('name') != 'Game UI Reskin' or not str(data.get('id', '')).isdigit():
        raise RuntimeError('Manifest Game UI Reskin khong hop le. Dung manifest di kem cong cu.')
    for name in ('code.js', 'ui.html'):
        if not (BASE / 'plugin' / name).is_file():
            raise RuntimeError('Thieu file plugin/' + name + '. Copy lai folder cong cu day du.')
    return str(sys.version).split()[0]

def main():
    try:
        version = check_runtime()
        if '--check' in sys.argv:
            print('OK: Python ' + version + ' 64-bit, Tkinter, Pillow, PyYAML, manifest va plugin files.')
            return 0
        pythonw = Path(sys.executable).with_name('pythonw.exe')
        if not pythonw.is_file():
            raise RuntimeError('Khong tim thay pythonw.exe trong ban cai Python 3.12.')
        subprocess.Popen([str(pythonw), str(BASE / 'desktop.py')], cwd=str(BASE),
                         creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        return 0
    except Exception as error:
        print('Khong mo duoc Game UI Reskin: ' + str(error))
        return 1

if __name__ == '__main__':
    sys.exit(main())
