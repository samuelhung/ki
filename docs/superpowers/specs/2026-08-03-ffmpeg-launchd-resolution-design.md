# LaunchAgent ffmpeg Resolution Design

## Context

The production ingest task `task-d7ff5704ef2c` now completes Douyin parsing,
download, and persistence after the Fake-IP fix, but fails during audio
extraction. The downloaded MP4 is valid and can be decoded successfully.
Production installs ffmpeg at `/usr/local/bin/ffmpeg`, while the LaunchAgent
uses `/usr/bin:/bin:/usr/sbin:/sbin`; consequently `shutil.which("ffmpeg")`
returns `None` inside the service.

## Options Considered

1. Extend the LaunchAgent `PATH` with Homebrew directories. This is simple,
   but broadens executable lookup for every child process owned by the service.
2. Add a media-local trusted-path fallback. This keeps the behavior scoped to
   ffmpeg, is directly testable, and does not change the environment of other
   subprocesses. This is the selected option.
3. Add an application setting for the ffmpeg path. This is flexible but adds a
   configuration surface and operational failure mode that the current single
   host deployment does not need.

## Design

Add a small resolver in `zhiji_backend.ingest.media`. It first calls
`shutil.which("ffmpeg")` so existing deployments and test environments keep
their current behavior. If that lookup fails, it checks these fixed candidates
in order:

1. `/usr/local/bin/ffmpeg` for the current Intel production host.
2. `/opt/homebrew/bin/ffmpeg` for Apple Silicon compatibility.

A fixed candidate is accepted only when it exists, is a regular file, and is
executable by the service account. Symlinks are allowed only when their resolved
target satisfies those checks; this matches normal Homebrew installation while
rejecting missing, directory, and non-executable candidates. The resolver
returns the first accepted absolute path. If no path qualifies, it raises the
existing `RuntimeError("ffmpeg executable not found")` through
`extract_audio()`.

No global `PATH`, LaunchAgent configuration, ingest database state, or ffmpeg
arguments change. The existing subprocess isolation, timeout, resource limits,
output-size limit, and partial-output cleanup remain intact.

## Test Strategy

Focused unit tests will prove:

- a result from `shutil.which("ffmpeg")` remains preferred;
- `/usr/local/bin/ffmpeg` is selected when `PATH` lookup fails;
- `/opt/homebrew/bin/ffmpeg` is selected when the Intel path is unavailable;
- missing, non-regular, and non-executable candidates are rejected;
- `extract_audio()` continues to raise the existing error when no candidate is
  usable.

The implementation follows red-green TDD. After focused tests, the complete
backend, frontend, lint, type-check, and production artifact checks run again.

## Deployment And Acceptance

Build a new immutable artifact from the resulting commit and deploy it as
`2.0.0+109` with `--preserve-history`. Keep `2.0.0+108` and all existing
backups as rollback material; do not modify or remove
`/Users/mrh/Documents/KI/data`.

After deployment, retry `task-d7ff5704ef2c` through the authenticated API. The
fix is accepted only when the original task reaches `done`, the queue displays
its timestamp in `Asia/Shanghai` (for example, `2026-08-03 09:56:03 UTC` as
`2026/8/3 17:56:03`), desktop and mobile views remain coherent, SQLite
`quick_check` is `ok`, health stays green, and the service PID/run count and
logs remain stable during the observation window.

If deployment verification fails, switch `current` back to `2.0.0+108`, restart
the LaunchAgent, and re-run health and database checks. Task data and downloaded
media remain in place for diagnosis and retry.
