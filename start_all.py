"""
start_all.py
────────────
Runs BOTH main.py (deals bot) and ipo_bot.py (IPO bot) as two child
processes, inside ONE Railway service. Railway only lets you set one
Start Command per service — this script IS that one command, and it
launches both bots underneath it.

Every log line from each bot is tagged so you can tell them apart in
Railway's single Deploy Logs panel:
    [MAIN] ...   ← from main.py   (your existing deals bot)
    [IPO]  ...   ← from ipo_bot.py (the new IPO bot)

Use Railway's log search box and type "[IPO]" to see only the IPO
bot's logs — that's how you check ipo_bot.py specifically going
forward, since both processes share one Deploy Logs stream.

Set this as your Railway Start Command (Settings → Deploy → Start Command):
    python start_all.py
"""

import subprocess
import sys
import threading
import time

SCRIPTS = [
    ("main.py", "MAIN"),
    ("ipo_bot.py", "IPO"),
]


def _stream_output(proc: subprocess.Popen, tag: str):
    for line in proc.stdout:
        sys.stdout.write(f"[{tag}] {line}")
        sys.stdout.flush()


def _start(script: str, tag: str) -> subprocess.Popen:
    proc = subprocess.Popen(
        [sys.executable, script],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    threading.Thread(target=_stream_output, args=(proc, tag), daemon=True).start()
    print(f"[LAUNCHER] Started {script} (pid={proc.pid})")
    return proc


if __name__ == "__main__":
    processes = [(_start(script, tag), script, tag) for script, tag in SCRIPTS]

    # If either bot crashes and exits, stop the whole service — Railway
    # will then restart it fresh (both bots together), rather than
    # silently running with only one bot alive.
    while True:
        for proc, script, tag in processes:
            code = proc.poll()
            if code is not None:
                print(f"[LAUNCHER] {script} ([{tag}]) exited with code {code} — stopping service so Railway restarts both")
                sys.exit(code or 1)
        time.sleep(2)