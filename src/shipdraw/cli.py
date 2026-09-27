"""Command line: shipdraw build <job.yaml>."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import CONFIG_DIR, ConfigError
from .job import load_job
from .pipeline import build, format_summary
from .profiles import ProfileLibrary
from .standard import load_standard


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="shipdraw", description="Generate ship structural drawings (DXF) from job files.")
    commands = parser.add_subparsers(dest="command", required=True)
    build_cmd = commands.add_parser("build", help="build one drawing from a job file")
    build_cmd.add_argument("job", type=Path, help="job file (YAML)")
    build_cmd.add_argument("-o", "--out", type=Path, default=Path("out"), help="output folder (default: out)")
    build_cmd.add_argument("--config", type=Path, default=CONFIG_DIR, help="folder with standard.yaml and profiles.yaml")
    build_cmd.add_argument("--no-preview", action="store_true", help="skip the PNG preview")
    args = parser.parse_args(argv)

    try:
        job = load_job(args.job)
        standard = load_standard(args.config / "standard.yaml")
        profiles = ProfileLibrary.load(args.config / "profiles.yaml")
        result = build(job, standard, profiles, args.out, preview=not args.no_preview)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(format_summary(result))
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
