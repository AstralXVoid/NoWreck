from __future__ import annotations

import os
import pty
import select
import subprocess
import time


def run_interactive(
    inputs: list[str],
    command: list[str] | None = None,
    timeout: float = 8.0,
    prompt_delay: float = 0.15,
) -> str:
    """Run ``nowreck --interactive`` inside a PTY and script keystrokes.

    Args:
        inputs: Keystrokes to send (e.g. ``"\\r"``, ``\"Add validation\"``).
        command: Command to run (defaults to ``[\"nowreck\", \"--interactive\"]``).
        timeout: Total seconds to wait before reading output.
        prompt_delay: Seconds to wait between keystrokes for the prompt
            to render.  Increase for slower machines.

    Returns:
        All terminal output captured from the PTY.
    """
    if command is None:
        command = ["nowreck", "--interactive"]

    master_fd, slave_fd = pty.openpty()
    proc = subprocess.Popen(
        command,
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
        close_fds=True,
    )
    os.close(slave_fd)

    output_chunks: list[bytes] = []
    deadline = time.monotonic() + timeout

    for keystroke in inputs:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break

        # Send the keystroke
        os.write(master_fd, keystroke.encode() if isinstance(keystroke, str) else keystroke)
        time.sleep(prompt_delay)

        # Drain available output (non-blocking)
        while True:
            r, _w, _x = select.select([master_fd], [], [], 0.01)
            if not r:
                break
            try:
                chunk = os.read(master_fd, 4096)
                if chunk:
                    output_chunks.append(chunk)
                else:
                    break
            except OSError:
                break

    # Final drain
    time.sleep(0.3)
    while True:
        r, _w, _x = select.select([master_fd], [], [], 0.05)
        if not r:
            break
        try:
            chunk = os.read(master_fd, 4096)
            if chunk:
                output_chunks.append(chunk)
            else:
                break
        except OSError:
            break

    os.close(master_fd)
    proc.terminate()
    proc.wait(timeout=3)

    raw = b"".join(output_chunks)
    return raw.decode("utf-8", errors="replace")


def strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences from terminal output."""
    import re
    return re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", text)


def strip_control(text: str) -> str:
    """Remove control characters but keep newlines and printable chars."""
    return "".join(ch for ch in text if ch.isprintable() or ch in "\n\r")
