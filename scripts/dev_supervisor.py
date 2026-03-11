#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parent.parent
STATE_FILE = ROOT_DIR / ".dev-supervisor.json"
BACKEND_HOST = "127.0.0.1"
BACKEND_PORT = "8000"
FRONTEND_HOST = "127.0.0.1"
FRONTEND_PORT = "3000"
STOP_RETRIES = 5
STOP_WAIT_SECONDS = 1.0


def main() -> int:
    parser = argparse.ArgumentParser(description="Cross-platform dev process supervisor.")
    parser.add_argument("command", choices=("run", "stop"))
    args = parser.parse_args()

    if args.command == "stop":
        return stop_managed_processes()
    return run_supervisor()


def run_supervisor() -> int:
    stop_managed_processes(verbose=False)

    backend = start_process(
        name="backend",
        command=build_backend_command(),
        cwd=ROOT_DIR,
    )
    frontend = start_process(
        name="frontend",
        command=build_frontend_command(),
        cwd=ROOT_DIR / "frontend",
    )
    processes = [backend, frontend]
    write_state(processes)

    reader_threads = [start_output_reader(process) for process in processes]
    exit_code = 0

    try:
        while True:
            time.sleep(0.25)
            exited = [process for process in processes if process["popen"].poll() is not None]
            if not exited:
                continue

            failed = next(
                (process for process in exited if int(process["popen"].returncode or 0) != 0),
                None,
            )
            if failed is not None:
                print(
                    "[dev] {name} exited with code {code}.".format(
                        name=failed["name"],
                        code=failed["popen"].returncode,
                    ),
                    file=sys.stderr,
                )
                exit_code = int(failed["popen"].returncode or 1)
            else:
                first = exited[0]
                print(
                    "[dev] {name} exited.".format(name=first["name"]),
                    file=sys.stderr,
                )
                exit_code = int(first["popen"].returncode or 0)
            break
    except KeyboardInterrupt:
        exit_code = 130
        print("[dev] Stopping backend and frontend.", file=sys.stderr)
    finally:
        stop_processes(processes)
        remove_state_file()
        for thread in reader_threads:
            thread.join(timeout=1.0)

    return exit_code


def stop_managed_processes(*, verbose: bool = True) -> int:
    state = read_state()
    if not state:
        if verbose:
            print("[dev] No managed dev processes found.")
        return 0

    processes = [{"name": item.get("name", "process"), "pid": int(item["pid"])} for item in state if item.get("pid")]
    if not processes:
        remove_state_file()
        if verbose:
            print("[dev] No managed dev processes found.")
        return 0

    if verbose:
        print(
            "[dev] Stopping managed processes: {items}".format(
                items=", ".join("{name}({pid})".format(name=item["name"], pid=item["pid"]) for item in processes)
            )
        )

    stop_processes(processes, managed_only=True)
    remove_state_file()
    return 0


def build_backend_command() -> list[str]:
    return [
        sys.executable,
        "-m",
        "uvicorn",
        "server:app",
        "--app-dir",
        "src",
        "--reload",
        "--reload-dir",
        "src",
        "--reload-dir",
        "tests",
        "--reload-dir",
        "scripts",
        "--reload-include",
        "*.py",
        "--reload-exclude",
        "frontend/*",
        "--reload-exclude",
        ".venv/*",
        "--reload-exclude",
        "*/.venv/*",
        "--reload-exclude",
        "venv/*",
        "--reload-exclude",
        "*/venv/*",
        "--reload-exclude",
        "*site-packages/*",
        "--reload-exclude",
        "__pycache__/*",
        "--host",
        BACKEND_HOST,
        "--port",
        BACKEND_PORT,
    ]


def build_frontend_command() -> list[str]:
    npm = shutil.which("npm.cmd") or shutil.which("npm")
    if not npm:
        raise RuntimeError("npm is not installed or not on PATH.")
    return [
        npm,
        "run",
        "dev",
        "--",
        "--host",
        FRONTEND_HOST,
        "--port",
        FRONTEND_PORT,
    ]


def start_process(*, name: str, command: list[str], cwd: Path) -> dict[str, Any]:
    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")
    popen_kwargs: dict[str, Any] = {
        "cwd": str(cwd),
        "env": env,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.STDOUT,
        "text": True,
        "bufsize": 1,
    }
    if os.name == "nt":
        popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        popen_kwargs["start_new_session"] = True

    process = subprocess.Popen(command, **popen_kwargs)
    return {
        "name": name,
        "pid": process.pid,
        "command": command,
        "cwd": str(cwd),
        "popen": process,
    }


def start_output_reader(process: dict[str, Any]) -> threading.Thread:
    thread = threading.Thread(
        target=stream_output,
        args=(process["name"], process["popen"]),
        daemon=True,
    )
    thread.start()
    return thread


def stream_output(name: str, process: subprocess.Popen[str]) -> None:
    if process.stdout is None:
        return
    for line in process.stdout:
        sys.stdout.write("[{name}] {line}".format(name=name, line=line))
        sys.stdout.flush()


def stop_processes(processes: list[dict[str, Any]], *, managed_only: bool = False) -> None:
    pids = [int(process["pid"] if managed_only else process["popen"].pid) for process in processes]
    graceful_terminate(pids)

    remaining = wait_for_exit(pids)
    if remaining:
        force_terminate(remaining)
        wait_for_exit(remaining)


def graceful_terminate(pids: list[int]) -> None:
    for pid in pids:
        terminate_pid(pid, force=False)


def force_terminate(pids: list[int]) -> None:
    for pid in pids:
        terminate_pid(pid, force=True)


def wait_for_exit(pids: list[int]) -> list[int]:
    remaining = [pid for pid in pids if pid_running(pid)]
    for _ in range(STOP_RETRIES):
        if not remaining:
            return []
        time.sleep(STOP_WAIT_SECONDS)
        remaining = [pid for pid in remaining if pid_running(pid)]
    return remaining


def terminate_pid(pid: int, *, force: bool) -> None:
    if pid <= 0:
        return
    if os.name == "nt":
        command = ["taskkill", "/PID", str(pid), "/T"]
        if force:
            command.append("/F")
        subprocess.run(command, capture_output=True, text=True, check=False)
        return

    try:
        os.killpg(os.getpgid(pid), signal.SIGKILL if force else signal.SIGTERM)
    except ProcessLookupError:
        return
    except Exception:
        try:
            os.kill(pid, signal.SIGKILL if force else signal.SIGTERM)
        except ProcessLookupError:
            return


def pid_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        result = subprocess.run(
            ["tasklist", "/FI", "PID eq {pid}".format(pid=pid)],
            capture_output=True,
            text=True,
            check=False,
        )
        return str(pid) in result.stdout

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def write_state(processes: list[dict[str, Any]]) -> None:
    payload = {
        "processes": [
            {
                "name": process["name"],
                "pid": process["popen"].pid,
                "command": process["command"],
                "cwd": process["cwd"],
            }
            for process in processes
        ]
    }
    STATE_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def read_state() -> list[dict[str, Any]]:
    if not STATE_FILE.exists():
        return []
    try:
        payload = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    processes = payload.get("processes")
    if not isinstance(processes, list):
        return []
    return [item for item in processes if isinstance(item, dict)]


def remove_state_file() -> None:
    try:
        STATE_FILE.unlink()
    except FileNotFoundError:
        return


if __name__ == "__main__":
    raise SystemExit(main())
