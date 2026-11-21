"""Package the desktop interface beside the Unity project."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parent
with tempfile.TemporaryDirectory(prefix="cube-studio-build-") as temp:
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
        "--windowed", "--name", "Cube Coach Studio", "--osx-bundle-identifier",
        "local.cubecoach.studio", "--distpath", str(root.parent),
        "--workpath", str(Path(temp) / "work"), "--specpath", temp,
        str(root / "studio.py")], cwd=root, env=dict(os.environ, PYINSTALLER_CONFIG_DIR=str(Path(temp) / "cache")), check=True)
print("Built", root.parent / "Cube Coach Studio.app")
