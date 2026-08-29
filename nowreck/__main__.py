from __future__ import annotations

import sys

try:
    from nowreck.main import main
except ImportError as exc:
    pkg = str(exc).split("'")[-2] if "'" in str(exc) else str(exc)
    pip_name = pkg.replace(".", "-") if pkg else pkg
    print(
        f"Error: missing dependency '{pkg}'.\nInstall it with:  pip install {pip_name}",
        file=sys.stderr,
    )
    sys.exit(1)

if __name__ == "__main__":
    sys.exit(main())
