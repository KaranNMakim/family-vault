"""Cross-platform task runner. The Makefile and make.cmd both delegate here.

Usage: python scripts/tasks.py <target>   (targets: install, lint, test, eval, seed, demo, web-test)
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
IS_WIN = os.name == "nt"


def _npm() -> str:
    exe = shutil.which("npm")
    if not exe and IS_WIN:
        candidate = Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "nodejs" / "npm.cmd"
        exe = str(candidate) if candidate.exists() else None
    if not exe:
        sys.exit("npm not found — install Node.js LTS (see README).")
    return exe


def run(cmd: list[str], cwd: Path = ROOT, env: dict | None = None) -> None:
    print(f"$ {' '.join(cmd)}", flush=True)
    r = subprocess.run(cmd, cwd=cwd, env={**os.environ, **(env or {})})
    if r.returncode:
        sys.exit(r.returncode)


def py(*args: str) -> list[str]:
    return [sys.executable, *args]


def t_install() -> None:
    run(["uv", "sync"])
    run([_npm(), "install", "--no-fund", "--no-audit"], cwd=WEB)


def t_lint() -> None:
    run(py("-m", "ruff", "check", "app", "tests", "scripts"))


def t_test() -> None:
    t_lint()
    run(py("-m", "pytest", "--cov=app/core", "--cov=app/kg", "--cov-report=term-missing:skip-covered",
           "--cov-fail-under=80"))
    if (WEB / "node_modules").exists():
        run([_npm(), "run", "test", "--silent"], cwd=WEB)
    else:
        print("web/node_modules missing — skipping web tests (run `make install`).")


def t_seed() -> None:
    run(py("-m", "app.seed"))


def t_eval() -> None:
    run(py("-m", "app.eval"))


def t_web_test() -> None:
    run([_npm(), "run", "test", "--silent"], cwd=WEB)


def t_demo() -> None:
    t_seed()
    npm = _npm()
    if not (WEB / "node_modules").exists():
        run([npm, "install", "--no-fund", "--no-audit"], cwd=WEB)
    if not (WEB / ".next" / "BUILD_ID").exists():
        run([npm, "run", "build"], cwd=WEB)
    procs = [
        subprocess.Popen(py("-m", "uvicorn", "app.api.main:app", "--port", "8000"), cwd=ROOT),
        subprocess.Popen([npm, "run", "start"], cwd=WEB),
    ]
    print("\n  family-vault DEMO  ->  web http://localhost:3000   api http://localhost:8000/docs\n"
          "  Synthetic data only. Ctrl+C to stop.\n", flush=True)
    try:
        while all(p.poll() is None for p in procs):
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        for p in procs:
            if p.poll() is None:
                p.terminate()


TARGETS = {
    "install": t_install,
    "lint": t_lint,
    "test": t_test,
    "seed": t_seed,
    "eval": t_eval,
    "demo": t_demo,
    "web-test": t_web_test,
}

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "demo"
    if target not in TARGETS:
        sys.exit(f"unknown target {target!r}; choose from {', '.join(TARGETS)}")
    TARGETS[target]()
