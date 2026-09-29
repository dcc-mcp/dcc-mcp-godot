"""Unattended Godot host launch for scene rendering.

Godot cannot render under ``--headless``: the flag degrades the renderer to
``rendering/dummy``, where even an offscreen ``SubViewport`` reads back nothing.
The measured alternative is to start a normal windowed host and hide its main
window, which renders byte-identically to a visible window. This module owns
that launch so scene previews can run from CI, scheduled tasks, or a headless
wrapper without a human watching a desktop.

Two levels are available, and the response always reports which one was used:

``private-desktop``
    Windows only. The host process is created on a private desktop
    (``CreateDesktop``), so no window of the run is ever visible on the
    interactive desktop. This is the real unattended wrapper and the only
    measured way to get a clean unattended render.
``plain``
    Everywhere else. The host is started as a normal child process and asked
    to hide its main window. Treat this as reduced-visibility, not invisible:
    on the Godot editor main window the hide request is best-effort only.

Never hide by minimizing: under ``gl_compatibility`` a minimized window reports
success while rendering an entirely black frame.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Optional, Sequence

HIDE_WINDOW_ENV = "DCC_MCP_GODOT_HIDE_WINDOW"
HIDE_WINDOW_ARG = "--dcc-mcp-hide-window"
PRIVATE_DESKTOP_NAME = "dcc-mcp-godot"

MODE_PRIVATE_DESKTOP = "private-desktop"
MODE_PLAIN = "plain"


@dataclass(frozen=True)
class LaunchRequest:
    """One unattended Godot host launch."""

    godot: str
    project: str
    extra_args: Sequence[str] = ()
    hide_window: bool = True
    private_desktop: bool = True
    timeout_secs: Optional[float] = None


@dataclass
class LaunchResult:
    """Outcome of one unattended launch, safe to serialize for a receipt."""

    mode: str
    command: list[str] = field(default_factory=list)
    exit_code: int = 0
    timed_out: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "command": self.command,
            "exit_code": self.exit_code,
            "timed_out": self.timed_out,
        }


def supports_private_desktop() -> bool:
    """Report whether this platform can host a run off the interactive desktop."""
    return sys.platform == "win32"


def resolve_mode(request: LaunchRequest) -> str:
    """Return the isolation mode this launch will actually use."""
    if request.private_desktop and supports_private_desktop():
        return MODE_PRIVATE_DESKTOP
    return MODE_PLAIN


def build_editor_command(request: LaunchRequest) -> list[str]:
    """Build the windowed editor command line used for unattended rendering.

    Everything after the bare ``--`` reaches the project as user arguments;
    without it Godot would consume them as engine arguments and the host
    addon would never see them.
    """
    command = [request.godot, "--path", request.project, "--editor", "--", *request.extra_args]
    if request.hide_window:
        command.append(HIDE_WINDOW_ARG)
    return command


def launch_host(request: LaunchRequest) -> LaunchResult:
    """Start a Godot editor host unattended and wait for it to exit."""
    mode = resolve_mode(request)
    command = build_editor_command(request)
    if mode == MODE_PRIVATE_DESKTOP:
        return _launch_on_private_desktop(
            command, timeout_secs=request.timeout_secs, hide_window=request.hide_window
        )
    return _launch_plain(
        command, timeout_secs=request.timeout_secs, hide_window=request.hide_window
    )


def _launch_plain(
    command: Sequence[str], *, timeout_secs: Optional[float], hide_window: bool = True
) -> LaunchResult:
    environment = dict(os.environ)
    # Mirror build_editor_command(): with --no-hide-window the flag is absent,
    # and this must not re-enable hiding behind the caller's back.
    environment[HIDE_WINDOW_ENV] = "1" if hide_window else "0"
    try:
        completed = subprocess.run(  # noqa: S603 - operator-supplied command
            list(command), env=environment, check=False, timeout=timeout_secs
        )
    except subprocess.TimeoutExpired:
        return LaunchResult(mode=MODE_PLAIN, command=list(command), exit_code=1, timed_out=True)
    return LaunchResult(mode=MODE_PLAIN, command=list(command), exit_code=completed.returncode)


def _launch_on_private_desktop(
    command: Sequence[str], *, timeout_secs: Optional[float], hide_window: bool = True
) -> LaunchResult:
    """Run the host on a private Windows desktop so nothing is ever visible."""
    import ctypes
    import ctypes.wintypes as wt

    GENERIC_ALL = 0x10000000
    INFINITE = 0xFFFFFFFF
    WAIT_TIMEOUT = 0x00000102
    CREATE_UNICODE_ENVIRONMENT = 0x00000400

    class STARTUPINFO(ctypes.Structure):
        _fields_ = [
            ("cb", wt.DWORD),
            ("lpReserved", ctypes.c_wchar_p),
            ("lpDesktop", ctypes.c_wchar_p),
            ("lpTitle", ctypes.c_wchar_p),
            ("dwX", wt.DWORD),
            ("dwY", wt.DWORD),
            ("dwXSize", wt.DWORD),
            ("dwYSize", wt.DWORD),
            ("dwXCountChars", wt.DWORD),
            ("dwYCountChars", wt.DWORD),
            ("dwFillAttribute", wt.DWORD),
            ("dwFlags", wt.DWORD),
            ("wShowWindow", ctypes.c_ushort),
            ("cbReserved2", ctypes.c_ushort),
            ("lpReserved2", ctypes.c_void_p),
            ("hStdInput", wt.HANDLE),
            ("hStdOutput", wt.HANDLE),
            ("hStdError", wt.HANDLE),
        ]

    class PROCESS_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("hProcess", wt.HANDLE),
            ("hThread", wt.HANDLE),
            ("dwProcessId", wt.DWORD),
            ("dwThreadId", wt.DWORD),
        ]

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    desktop = user32.CreateDesktopW(PRIVATE_DESKTOP_NAME, None, None, 0, GENERIC_ALL, None)
    if not desktop:
        raise RuntimeError(
            "CreateDesktopW failed: %s" % ctypes.FormatError(ctypes.get_last_error())
        )
    startup_info = STARTUPINFO()
    startup_info.cb = ctypes.sizeof(startup_info)
    startup_info.lpDesktop = PRIVATE_DESKTOP_NAME
    process_info = PROCESS_INFORMATION()
    # The child needs the caller's whole environment (PATH, driver paths, ...),
    # packed as NUL-separated UTF-16 pairs and terminated by an extra NUL.
    environment = dict(os.environ)
    environment[HIDE_WINDOW_ENV] = "1" if hide_window else "0"
    environment_block = ctypes.create_unicode_buffer(
        "".join("%s=%s\0" % (key, value) for key, value in environment.items()) + "\0"
    )
    created = kernel32.CreateProcessW(
        None,
        subprocess.list2cmdline(list(command)),
        None,
        None,
        False,
        CREATE_UNICODE_ENVIRONMENT,
        environment_block,
        None,
        ctypes.byref(startup_info),
        ctypes.byref(process_info),
    )
    if not created:
        user32.CloseDesktop(desktop)
        raise RuntimeError(
            "CreateProcessW failed: %s" % ctypes.FormatError(ctypes.get_last_error())
        )

    try:
        if timeout_secs is None:
            kernel32.WaitForSingleObject(process_info.hProcess, INFINITE)
            timed_out = False
        else:
            timeout_ms = int(timeout_secs * 1000)
            timed_out = (
                kernel32.WaitForSingleObject(process_info.hProcess, timeout_ms) == WAIT_TIMEOUT
            )
            if timed_out:
                kernel32.TerminateProcess(process_info.hProcess, 1)
        exit_code = wt.DWORD()
        kernel32.GetExitCodeProcess(process_info.hProcess, ctypes.byref(exit_code))
    finally:
        kernel32.CloseHandle(process_info.hProcess)
        kernel32.CloseHandle(process_info.hThread)
        user32.CloseDesktop(desktop)

    if timed_out:
        return LaunchResult(
            mode=MODE_PRIVATE_DESKTOP, command=list(command), exit_code=1, timed_out=True
        )
    return LaunchResult(
        mode=MODE_PRIVATE_DESKTOP,
        command=list(command),
        exit_code=int(exit_code.value),
        timed_out=False,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point: ``dcc-mcp-godot unattended``."""
    import argparse
    import json

    parser = argparse.ArgumentParser(
        prog="dcc-mcp-godot unattended",
        description=(
            "Start a Godot editor host for unattended scene rendering. Godot cannot "
            "render under --headless, so this starts a windowed host and hides its "
            "main window; on Windows the run is additionally placed on a private "
            "desktop so nothing is visible on the interactive desktop."
        ),
    )
    parser.add_argument("--godot", required=True, help="Path to the Godot editor executable.")
    parser.add_argument("--project", required=True, help="Project directory to open.")
    parser.add_argument(
        "--timeout", type=float, default=None, help="Kill the host after this many seconds."
    )
    parser.add_argument(
        "--no-hide-window",
        action="store_true",
        help="Leave the host window visible (debugging only; not unattended).",
    )
    parser.add_argument(
        "--no-private-desktop",
        action="store_true",
        help="Do not use a Windows private desktop, even if available.",
    )
    parser.add_argument("--json", action="store_true", help="Print the launch receipt as JSON.")
    parser.add_argument(
        "extra_args",
        nargs="*",
        help="Extra Godot arguments, placed before the hide-window flag.",
    )
    arguments = parser.parse_args(list(argv) if argv is not None else None)

    result = launch_host(
        LaunchRequest(
            godot=arguments.godot,
            project=arguments.project,
            extra_args=tuple(arguments.extra_args),
            hide_window=not arguments.no_hide_window,
            private_desktop=not arguments.no_private_desktop,
            timeout_secs=arguments.timeout,
        )
    )
    if arguments.json:
        print(json.dumps(result.as_dict(), indent=2))
    else:
        print(
            "mode=%s exit_code=%d%s"
            % (result.mode, result.exit_code, " timed_out=true" if result.timed_out else "")
        )
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
