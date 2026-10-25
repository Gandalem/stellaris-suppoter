# Windows Qt 6.12 uses OS ICU; do not shadow it with unrelated build-host ICU.
import os
from pathlib import Path

root = Path(SPECPATH).parent
console = os.environ.get("STELLARIS_BUILD_CONSOLE") == "1"
name = "StellarisSupporterDebug" if console else "StellarisSupporter"
a = Analysis([str(root / "scripts" / "desktop_entry.py")], pathex=[str(root / "src")],
             binaries=[], datas=[], hiddenimports=[], hookspath=[], hooksconfig={},
             runtime_hooks=[], excludes=[], noarchive=False, optimize=0)
a.binaries = [entry for entry in a.binaries
              if Path(entry[0]).name.casefold() != "icuuc.dll"
              and not Path(entry[0]).name.casefold().startswith("icudt")]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name=name, debug=False,
          bootloader_ignore_signals=False, strip=False, upx=False, console=console,
          disable_windowed_traceback=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name=name)
