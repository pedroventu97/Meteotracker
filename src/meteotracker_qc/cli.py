from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .application import ApplicationService, WorkspaceError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="meteotracker", description="Meteotracker workspace and QC application")
    parser.add_argument("--workspace", default=None, help="Meteotracker workspace path (or METEOTRACKER_WORKSPACE)")
    parser.add_argument("--json", action="store_true", help="Render structured JSON")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("doctor", "status", "history"):
        command = commands.add_parser(name)
        command.add_argument("--workspace", default=argparse.SUPPRESS)
        command.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    discover = commands.add_parser("discover")
    discover.add_argument("--workspace", default=argparse.SUPPRESS)
    discover.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    discover.add_argument("--path", action="append", default=[])
    check = commands.add_parser("check")
    check.add_argument("--workspace", default=argparse.SUPPRESS)
    check.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    check.add_argument("--new", action="store_true")
    check.add_argument("--path", action="append", default=[])
    for name in ("apply", "run"):
        command = commands.add_parser(name)
        command.add_argument("--workspace", default=argparse.SUPPRESS)
        command.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
        command.add_argument("--new", action="store_true")
        command.add_argument("--path", action="append", default=[])
        command.add_argument("--yes", action="store_true", help="Skip confirmation for run")
    commands.choices["history"].add_argument("--run-id")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    service = ApplicationService(args.workspace)
    try:
        if args.command == "doctor":
            payload = service.doctor()
        elif args.command == "status":
            payload = service.status()
        elif args.command == "history":
            payload = service.history(args.run_id)
        elif args.command == "discover":
            payload = [item.__dict__ for item in service.discover(args.path or None)]
        elif args.command == "check":
            payload = service.check(args.path or None, new_only=args.new)
        else:
            if args.command == "apply":
                payload = service.apply(args.path or None)
            else:
                payload = service.run(args.path or None, yes=args.yes)
    except WorkspaceError as exc:
        print(json.dumps({"status": "blocked", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 3
    except Exception as exc:
        print(json.dumps({"status": "error", "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False), file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
    else:
        _print_human(args.command, payload)
    if isinstance(payload, dict) and payload.get("status") == "fail":
        return 2
    return 0


def _print_human(command: str, payload: object) -> None:
    if command == "doctor" and isinstance(payload, dict):
        print(f"Workspace: {payload['workspace']} ({'valid' if payload['valid'] else 'invalid'})")
    elif command == "status" and isinstance(payload, dict):
        print(f"Workspace: {payload['workspace']}")
        print(f"Registered files: {payload['registered_files']}; new files: {payload['new_files']}")
    elif command == "discover" and isinstance(payload, list):
        print(f"Discovered CSV files: {len(payload)}")
        for item in payload:
            print(f"- {item['source_file']}: {item['validation'].get('classification')}")
    elif isinstance(payload, dict):
        print(f"{command}: {payload.get('status', 'completed')}")
        if payload.get("report_path"):
            print(f"Report: {payload['report_path']}")
    else:
        print(payload)


if __name__ == "__main__":
    raise SystemExit(main())
