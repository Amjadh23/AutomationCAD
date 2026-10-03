"""Command line: `shipdraw build <job.yaml>` and `shipdraw serve`."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import CONFIG_DIR, ConfigError
from .job import load_job
from .pipeline import build, format_summary
from .profiles import ProfileLibrary
from .standard import load_standard
from .web.api import DrawingService
from .web.server import serve


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="shipdraw", description="Generate ship structural drawings (DXF) from job files.")
    commands = parser.add_subparsers(dest="command", required=True)
    build_cmd = commands.add_parser("build", help="build one drawing from a job file")
    build_cmd.add_argument("job", type=Path, help="job file (YAML)")
    build_cmd.add_argument("-o", "--out", type=Path, default=Path("out"), help="output folder (default: out)")
    build_cmd.add_argument("--no-preview", action="store_true", help="skip the PNG preview")
    serve_cmd = commands.add_parser("serve", help="open the drawing page in your browser")
    serve_cmd.add_argument("--port", type=int, default=8765, help="port to use (a free one is picked if it is busy)")
    serve_cmd.add_argument("--no-browser", action="store_true", help="don't open the browser")
    for command in (build_cmd, serve_cmd):
        command.add_argument("--config", type=Path, default=CONFIG_DIR, help="folder with standard.yaml and profiles.yaml")
    args = parser.parse_args(argv)

    try:
        standard = load_standard(args.config / "standard.yaml")
        profiles = ProfileLibrary.load(args.config / "profiles.yaml")
        if args.command == "serve":
            serve(DrawingService(standard, profiles), port=args.port, open_browser=not args.no_browser)
            return 0
        job = load_job(args.job)
        result = build(job, standard, profiles, args.out, preview=not args.no_preview)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(format_summary(result))
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
