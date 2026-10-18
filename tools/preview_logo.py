#!/usr/bin/env python3
"""Render generated Vectrex line data to an SVG preview."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from svg_to_vectrex import preview_svg_text


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_json", type=Path)
    parser.add_argument("--output", type=Path, default=Path("generated/logo_preview_large.svg"))
    parser.add_argument("--width", type=int, default=800)
    parser.add_argument("--height", type=int, default=1000)
    args = parser.parse_args(argv)

    payload = json.loads(args.input_json.read_text(encoding="utf-8"))
    output = preview_svg_text(payload["lines"], width=args.width, height=args.height)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(output, encoding="utf-8")
    print(f"Wrote preview to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
