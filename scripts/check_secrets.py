"""扫描仓库中的明文凭据、内网地址与私钥。"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

SKIP_DIRS = {
    ".git", ".venv", "node_modules", "__pycache__", ".superpowers", "projects",
    "pw-profile", "apache-jmeter-5.6.3",
}
SKIP_SUFFIXES = {".pyc", ".png", ".jpg", ".jpeg", ".pdf", ".lock", ".ico", ".exe"}

PATTERNS = [
    (re.compile(r"""(?i)\b(password|passwd|secret|token|api_key)\b\s*[:=]\s*["'][^"']{6,}["']"""),
     "疑似明文凭据 {key}"),
    (re.compile(r"\bghp_[A-Za-z0-9]{20,}"), "GitHub token"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"), "GitHub fine-grained token"),
    (re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}"), "GitLab token"),
    (re.compile(r"BEGIN [A-Z ]*PRIVATE KEY"), "私钥"),
    (re.compile(r"\b(?:10\.\d{1,3}|192\.168\.|172\.(?:1[6-9]|2\d|3[01])\.)\d{1,3}\.\d{1,3}\b"),
     "内网地址"),
]


def _iter_files(paths):
    for raw in paths:
        path = Path(raw)
        if path.is_file():
            yield path
        elif path.is_dir():
            for child in path.rglob("*"):
                if any(part in SKIP_DIRS for part in child.parts):
                    continue
                if child.is_file() and child.suffix not in SKIP_SUFFIXES:
                    yield child


def scan(paths: list[Path]) -> list[tuple[Path, int, str]]:
    hits: list[tuple[Path, int, str]] = []
    for path in _iter_files(paths):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            if "noqa: secrets" in line:
                continue
            for pattern, label in PATTERNS:
                match = pattern.search(line)
                if not match:
                    continue
                if "{key}" in label and match.groups():
                    label = label.replace("{key}", match.group(1))
                hits.append((path, lineno, label))
                break
    return hits


def _tracked_files() -> list[Path]:
    try:
        out = subprocess.run(["git", "ls-files"], capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return [Path(".")]
    return [Path(line) for line in out.stdout.splitlines() if line.strip()]


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    paths = [Path(arg) for arg in args] if args else _tracked_files()
    hits = scan(paths)
    for path, lineno, label in hits:
        print(f"{path}:{lineno}: {label}")
    print(f"共 {len(hits)} 处" if hits else "未发现敏感信息")
    return 1 if hits else 0


if __name__ == "__main__":
    raise SystemExit(main())
