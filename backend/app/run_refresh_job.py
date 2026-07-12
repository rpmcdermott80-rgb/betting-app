"""Subprocess entrypoint for a single refresh run. Usage: python -m app.run_refresh_job <run_id>

Launched via subprocess.Popen (see app/routers/refresh.py) rather than an in-process
thread — a hang in here (this project has seen a few, never fully root-caused) then
only kills this one process, not the whole API server, and the watchdog in
app/refresh.py can tell it apart from a live run by PID and kill it cleanly.
"""

import sys

from app.refresh import execute_refresh

if __name__ == "__main__":
    execute_refresh(int(sys.argv[1]))
