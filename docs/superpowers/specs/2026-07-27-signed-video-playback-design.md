# Signed Video Playback Design

## Goal

Restore video playback in content ingest event details when the production UI is
opened from the non-secure LAN origin `http://10.8.0.105:9120`. Preserve remote
authentication, HTTP range requests, existing content data, and the current
cinematic layout.

## Root Cause

The event detail page currently converts `video_path` into a protected
`/ingest/videos/<filename>` path. When a remote API token is present, the
frontend relies on a Service Worker to add the authorization header to video
requests. Browsers do not expose Service Workers on the production non-secure
LAN origin, so media transport setup fails and the hook returns an empty URL.
The player is therefore omitted even though the files still exist.

Production inspection found 197 event rows with `video_path`; every one maps by
filename to an existing file under the active ingest video directory. This fix
does not move, rewrite, or delete database records or media files.

## Selected Approach

Use a short-lived, stateless HMAC-signed playback URL for each event video.
The authenticated event-detail API returns the URL, and a dedicated media
endpoint validates it before serving the existing file with the current pinned
file response implementation.

The long-lived `KI_API_TOKEN` is never placed in the URL. It is used only as the
server-side HMAC key. The signature is scoped to one media kind, one filename,
and one expiry timestamp. Token rotation invalidates every outstanding URL.

## Alternatives Rejected

### HTTPS-only deployment

Serving the application through trusted HTTPS would enable the existing Service
Worker design, but it adds certificate distribution and reverse-proxy work to a
narrow playback repair. HTTPS remains a valid later infrastructure improvement.

### Whole-file Blob fallback

Fetching the video with an authorization header and creating an object URL is
small in code, but it buffers files that are often tens or hundreds of
megabytes, delays first playback, and weakens seeking behavior. Existing tests
explicitly prohibit this transport.

### Public ingest files

Removing authentication from `/ingest` would restore playback but expose all
ingested media to any LAN client. This is not acceptable.

## Backend Design

### Signing service

Add a focused media signing module with pure functions to:

- validate the requested media kind and safe filename;
- create an expiry timestamp with a fixed 30-minute lifetime;
- sign a versioned canonical message containing purpose, kind, filename, and
  expiry using HMAC-SHA256 and `KI_API_TOKEN`;
- verify expiry, reject timestamps outside the allowed lifetime, and compare the
  supplied signature in constant time.

The signature cannot authorize API, release, document, transcript, summary, or
audio routes. This repair signs only `videos` playback.

### Event detail response

`GET /api/events/{event_id}` remains protected by the existing API middleware.
When its row has a `video_path`, the backend derives only the basename, confirms
that it resolves to a regular file under the active ingest video directory, and
adds an optional `video_url` field. Missing or unsafe files produce no URL and
do not expose filesystem paths through a new error.

Existing response fields, including `video_path`, remain unchanged for
compatibility.

### Playback endpoint

Add `GET` and `HEAD` support at
`/media/videos/{filename}?expires=<unix>&signature=<hex>`. The endpoint:

1. validates the filename before filesystem access;
2. validates the numeric expiry and HMAC signature;
3. opens the file through the existing confined regular-file helper;
4. returns it through the existing pinned file response, preserving `Range`,
   conditional requests, content length, and seek behavior.

Invalid, expired, malformed, missing, or mismatched capabilities return a
generic `404` so callers cannot distinguish signature failure from file absence.
The endpoint does not redirect and does not accept credentials in query
parameters other than the short-lived expiry and signature.

The signing and verification paths use the same server token snapshot for one
operation. If no API token is configured, the event detail keeps using the
existing direct loopback media path and does not issue a signed URL.

## Frontend Design

Extend the event detail type with optional `video_url`. Prefer that value when
present and pass it directly to the `<video>` element. Retain the existing
authenticated Service Worker path as a compatibility fallback for secure or
loopback deployments whose backend does not yet return `video_url`.

No layout, tab, player controls, WebGL scene, navigation, or copy changes are
required. No Blob or object URL is created.

## Security And Logging

- Signatures are 30-minute, file-scoped capabilities and cannot be exchanged for
  the API token.
- The canonical message is versioned and delimited so fields cannot be
  reinterpreted.
- Verification rejects past expiries and expiries beyond the permitted clock
  window.
- Signature checks use `hmac.compare_digest`.
- The existing secure log redaction rules for `signature` query values remain
  mandatory; tests verify signatures do not appear in application logs.
- Browser history may retain the short-lived URL, but it expires independently
  and grants access only to one video.
- Database paths and production media are not migrated or rewritten.

## Error Handling

- No `video_path`: omit `video_url` and the player, preserving current behavior.
- Recorded legacy absolute path with a valid current basename: resolve the
  basename under the active ingest root and issue the URL.
- Missing current file: omit `video_url`.
- Invalid filename or unsupported kind: return generic `404` from playback.
- Expired or invalid signature: return generic `404`.
- Token rotation or backend restart: already-issued URLs remain valid only if
  the configured token is unchanged; refreshing event details issues a new URL.

## Test Strategy

- Unit tests first prove signing and verification for a valid filename, expiry,
  tampered filename, tampered expiry, wrong signature, missing token, and future
  expiry beyond the allowed window.
- Route tests prove valid `GET`, `HEAD`, and `Range` requests, plus generic
  rejection for invalid, expired, missing, and traversal-shaped requests.
- Event route tests prove a valid existing video produces `video_url`, a legacy
  absolute path resolves by safe basename, and a missing file does not produce a
  signed URL.
- Frontend tests prove `video_url` is preferred, the Service Worker path remains
  the fallback, and no Blob buffering is introduced.
- Run the focused backend security/media suites, frontend media transport suite,
  frontend build, and unified repository check.
- Production verification uses one known video event to confirm event-detail
  metadata, `HEAD`, an authenticated signed `Range` response, browser playback,
  seeking, one WebGL canvas, and zero console errors.

## Deployment And Rollback

Build and deploy the backend wheel with its bundled frontend through the existing
atomic deployment process. Do not touch `/Users/mrh/Documents/KI/data` except
for read-only verification. Keep the prior runtime target as the rollback.

After deployment, verify health, package version, SQLite `PRAGMA quick_check`,
launchd state, signed playback, and the normal protected API `401` boundary.
If playback or security checks fail, restore the previous runtime target; no data
rollback is required because this change has no database or file mutation.

## Non-Goals

- No TLS or reverse-proxy rollout.
- No API token rotation.
- No database migration or stored-path rewrite.
- No public media directory.
- No audio or document preview expansion.
- No redesign of content ingest or event detail pages.
