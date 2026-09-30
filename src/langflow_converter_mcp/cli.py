"""Command-line entry point for stdio and local HTTP transports."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence
from pathlib import Path

from langflow_converter_mcp.server import create_server


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Langflow Converter MCP server")
    parser.add_argument(
        "--workspace",
        type=Path,
        default=Path.cwd(),
        help="Only this directory may be read or written (default: current directory)",
    )
    parser.add_argument(
        "--transport", choices=("stdio", "http"), default="stdio", help="MCP transport"
    )
    parser.add_argument("--port", type=int, default=8765, help="Local HTTP port")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    """Run the MCP server over stdio or localhost Streamable HTTP."""
    args = _parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    server = create_server(args.workspace)
    if args.transport == "http":
        server.run(
            "streamable-http",
            host="127.0.0.1",
            port=args.port,
            streamable_http_path="/mcp",
            max_request_body_size=5 * 1024 * 1024,
        )
    else:
        server.run("stdio")


if __name__ == "__main__":
    main()
