"""Launch the *built* Windows GUI executable and fail on crashes or hangs.

Called by both pull-request CI and release CI. The disposable APPDATA path
ensures that verification never uses or changes the runner's real profile.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python tools/smoke_exe.py path/to/program.exe")
    exe = Path(sys.argv[1]).resolve()
    if not exe.is_file():
        raise SystemExit(f"Missing Windows executable: {exe}")

    with tempfile.TemporaryDirectory(prefix="dp-typing-smoke-") as profile_dir:
        env = dict(os.environ)
        env["APPDATA"] = profile_dir
        try:
            result = subprocess.run([str(exe), "--smoke-test"], env=env,
                                    timeout=75, check=False)
        except subprocess.TimeoutExpired as exc:
            raise SystemExit("Executable hung during GUI startup") from exc
        if result.returncode:
            raise SystemExit(f"Executable failed startup with code {result.returncode}")
    print("Windows executable GUI startup and bundled resources: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
