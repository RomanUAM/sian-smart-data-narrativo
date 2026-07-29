#!/usr/bin/env python3
from __future__ import annotations

import shutil
import sys
from pathlib import Path


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    min_gb = float(sys.argv[2]) if len(sys.argv) > 2 else 3.0
    total, used, free = shutil.disk_usage(path)
    free_gb = free / 1024**3
    print(f"path={path}")
    print(f"free_gb={free_gb:.2f}")
    print(f"required_gb={min_gb:.2f}")
    if free_gb < min_gb:
        print("ERROR: insufficient free disk space for a long collection run.")
        return 2
    print("OK: enough free disk space.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

