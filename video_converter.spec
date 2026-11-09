# -*- mode: python ; coding: utf-8 -*-
# Qt 6.12 uses the Windows system ICU API (unsuffixed symbols).
# Do not collect another program's ICU with the same filename and suffixed symbols.
a = Analysis(['main.py'], pathex=[], binaries=[], datas=[], hiddenimports=[],
             hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[],
             noarchive=False, optimize=0)
a.binaries = [entry for entry in a.binaries
              if entry[0].replace('\\', '/').split('/')[-1].lower()
              not in {'icuuc.dll', 'icudt78.dll'}]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='VideoConverter',
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
          console=False, disable_windowed_traceback=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='VideoConverter')
