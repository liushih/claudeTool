"""把 Markdown 报告渲染成 Word / PPT。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from runtime.render import parse_markdown, render_docx, render_pptx  # noqa: E402

MISSING = "缺少依赖：python-docx / python-pptx，请先 pip install -r requirements.txt"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="渲染报告文档")
    parser.add_argument("--input", required=True)
    parser.add_argument("--format", default="docx", help="docx,pptx")
    parser.add_argument("--out-dir", default=".")
    parser.add_argument("--title")
    parser.add_argument("--subtitle", default="")
    args = parser.parse_args(argv)

    source = Path(args.input)
    text = source.read_text(encoding="utf-8")
    title = args.title or parse_markdown(text)[0] or "报告"

    formats = [item.strip() for item in args.format.split(",") if item.strip()]
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    for fmt in formats:
        target = out_dir / f"{source.stem}.{fmt}"
        try:
            if fmt == "docx":
                render_docx(text, target, title)
            elif fmt == "pptx":
                render_pptx(text, target, title, args.subtitle)
            else:
                print(f"未知格式 {fmt}", file=sys.stderr)
                return 2
        except ImportError:
            print(MISSING)
            return 1
        print(target)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
