"""Build a local standalone Windows folder without publishing or modifying game files."""
import argparse
import os
import subprocess
import sys
from pathlib import Path


def main():
    if os.name != "nt":
        raise SystemExit("The desktop executable must be built on Windows.")
    parser = argparse.ArgumentParser()
    parser.add_argument("--console", action="store_true", help="Build a separate diagnostic console executable")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    env = dict(os.environ, STELLARIS_BUILD_CONSOLE="1" if args.console else "0")
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
                    "--distpath", str(root / "dist"), "--workpath", str(root / "build" / "desktop"),
                    str(root / "packaging" / "desktop.spec")], cwd=root, env=env, check=True)


if __name__ == "__main__":
    main()
