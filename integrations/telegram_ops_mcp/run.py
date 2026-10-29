"""Launch with this project's .venv/bin/python -I -B; never install on connect."""

from pathlib import Path
import sys


def main() -> int:
    if len(sys.argv) != 1:
        print("telegram_ops_mcp: arguments_not_supported", file=sys.stderr)
        return 2

    # -I excludes the caller's directory; add only this known repository root.
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    try:
        from telegram_gateway.ops_mcp import main as run_server

        run_server()
    except KeyboardInterrupt:
        return 0
    except Exception:
        # Startup/protocol failures must not print private paths or inputs.
        print("telegram_ops_mcp: server_failed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
