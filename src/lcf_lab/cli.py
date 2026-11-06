"""Command-line entry points for LCF Lab."""

import argparse
import json
import sys
import webbrowser
from pathlib import Path

from . import __version__
from .demo import demo_analysis
from .engine import fit_batch
from .export import build_export
from .server import create_server


def main(argv=None) -> int:
    """Run the local interface, fit an analysis file, or write example data."""
    parser = argparse.ArgumentParser(prog="lcf-lab")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve", help="Open the local browser workbench")
    serve.add_argument("--port", type=int, default=0, help="Local port (default: choose an available port)")
    serve.add_argument("--no-browser", action="store_true")
    example = commands.add_parser("example", help="Write a synthetic analysis request")
    example.add_argument("element", choices=["Fe", "Mn"])
    example.add_argument("-o", "--output", required=True, type=Path)
    fit = commands.add_parser("fit", help="Fit an analysis request and export a ZIP")
    fit.add_argument("analysis", type=Path)
    fit.add_argument("-o", "--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "serve":
            with create_server(args.port) as server:
                url = f"http://127.0.0.1:{server.server_port}/"
                print(f"LCF Lab is available at {url}", flush=True)
                if not args.no_browser:
                    webbrowser.open(url)
                server.serve_forever()
            return 0
        if args.command == "example":
            data = json.dumps(demo_analysis(args.element), indent=2) + "\n"
            with args.output.open("x", encoding="utf-8") as target:
                target.write(data)
        else:
            analysis = json.loads(args.analysis.read_text(encoding="utf-8-sig"))
            output = build_export(analysis, fit_batch(analysis))
            with args.output.open("xb") as target:
                target.write(output)
        print(args.output)
        return 0
    except KeyboardInterrupt:
        return 0
    except (OSError, ValueError) as error:
        print(f"LCF Lab: {error}", file=sys.stderr)
        return 1
