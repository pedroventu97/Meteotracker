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
    sessions = commands.add_parser("sessions", help="Analisi read-only delle campagne registrate")
    session_commands = sessions.add_subparsers(dest="session_command", required=True)
    for name in ("list", "inspect", "qc", "compare"):
        command = session_commands.add_parser(name)
        command.add_argument("--workspace", default=argparse.SUPPRESS)
        command.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
        if name == "list":
            command.add_argument("--search", default="")
            command.add_argument("--batch")
            command.add_argument("--status")
            command.add_argument("--date-from")
            command.add_argument("--date-to")
        else:
            command.add_argument("campaign_ids", nargs="+" if name != "inspect" else 1)
        if name in {"qc", "compare"}:
            command.add_argument("--profile", choices=("recommended", "permissive", "restrictive"), default="recommended")
            command.add_argument("--preset", help="Preset JSON compatibile")
            command.add_argument("--disable", action="append", default=[], help="ID di controllo da disattivare")
            command.add_argument("--export", action="store_true", help="Salva solo in outputs/custom_analyses")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.json:
        _use_utf8_json_streams()
    service = ApplicationService(args.workspace)
    try:
        if args.command == "sessions":
            if args.session_command == "list":
                payload = service.list_sessions(search=args.search, batch=args.batch, status=args.status,
                                                date_from=args.date_from, date_to=args.date_to)
            elif args.session_command == "inspect":
                payload = service.inspect_session(args.campaign_ids[0])
            else:
                from .analysis_settings import DEFAULT_ACTIVE
                options = {"profile": args.profile, "active_controls": [g for g in DEFAULT_ACTIVE if g not in args.disable]}
                if args.preset:
                    preset = service.load_analysis_preset(args.preset)
                    options = {"profile": preset["origin_profile"], "active_controls": preset["active_controls"], "overrides": preset["overrides"]}
                if set(args.disable) - set(DEFAULT_ACTIVE):
                    raise ValueError("Controllo --disable sconosciuto")
                with service.preview_qc(args.campaign_ids, **options) as analysis:
                    payload = dict(analysis.report)
                    payload["comparison"] = service.compare_sessions(analysis=analysis)
                    payload["preview_directory"] = None  # context manager removes disposable data
                    if args.export:
                        payload["export_directory"] = service.export_custom_analysis(analysis)
        elif args.command == "doctor":
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


def _use_utf8_json_streams() -> None:
    """Machine-readable output is always UTF-8, independent of the Windows locale.

    With a redirected stdout Python uses the ANSI code page (e.g. cp1252): non-ASCII
    paths would become non-UTF-8 bytes and characters outside the code page would
    raise UnicodeEncodeError. Encoding errors stay strict.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")


def _print_human(command: str, payload: object) -> None:
    if command == "sessions":
        if isinstance(payload, list):
            for row in payload:
                print(f"{row['campaign_id']} | {row['date']} | {row['batch']} | {row['rows']} righe | {row['session_qc_status']}")
        else:
            print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    elif command == "doctor" and isinstance(payload, dict):
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
