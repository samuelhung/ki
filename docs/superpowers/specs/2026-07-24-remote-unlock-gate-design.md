# Remote Unlock Gate Design

## Goal

Prevent the production UI from silently rendering empty business views when a
browser opens the non-loopback backend without a `KI_API_TOKEN`. Preserve the
existing remote authentication boundary while providing a clear, recoverable
unlock flow.

## Scope

- Add a global unlock gate for non-loopback browser access when the current tab
  has no API token.
- Validate the submitted token against `GET /api/system/health` before storing
  it.
- Store the token only in `sessionStorage` and reload the current route after a
  successful unlock so existing data loaders run normally.
- Reopen the gate when a protected API request later returns `401`.
- Keep localhost, loopback, Vite proxy, HTTP APIs, database schema, business
  behavior, copy outside the gate, and existing page layout unchanged.

## Alternatives Considered

### 1. Global unlock gate (selected)

Block protected application views before their data loaders run. Show the
existing cinematic background with a focused Magic Bento-style unlock window.
This prevents misleading empty states and keeps authentication explicit.

### 2. Open the gate only after a `401`

Let pages mount and react to rejected requests. This has less startup logic but
briefly shows empty or error states and allows many parallel requests to fail
before the user sees the cause.

### 3. Restore an automatically issued session cookie

This gives direct access without user input, but any browser that can reach the
LAN service can obtain the cookie. It would undo the security boundary created
by the access hardening work and is rejected.

## Architecture

### Authentication state

Add a small frontend authentication module with pure helpers for:

- detecting loopback hosts;
- deciding whether the current runtime requires an unlock;
- publishing and subscribing to a single `ki-auth-required` browser event.

The module must not read or expose the token beyond the existing `getApiToken`
and `setApiToken` interfaces.

### Unlock gate

Mount one application-level gate above routed content. The gate has three
states:

- `locked`: token input and unlock command are available;
- `checking`: submission is disabled while validation is in flight;
- `error`: a concise authentication or connectivity message is shown and the
  input remains available.

The existing WebGL scene and navigation shell remain mounted as the visual
background, but protected page interaction is blocked until unlock succeeds.
The window reuses the existing Magic Bento modal visual language and does not
introduce a new page layout.

### Validation flow

1. On non-loopback production origins, detect a missing session token before
   protected route content mounts.
2. The user enters the server token and submits.
3. Request `GET /api/system/health` with `Authorization: Bearer <token>` and a
   10-second timeout.
4. On HTTP `200` with a healthy payload, save the token through `setApiToken`
   and reload the current URL once.
5. On `401`, show an invalid-token message without storing the value.
6. On timeout, network failure, invalid JSON, or unhealthy payload, show a
   classified connection message without storing the value.

No token is placed in URLs, logs, persistent local storage, HTML, or build-time
environment variables.

### Runtime `401` handling

`apiFetch` continues to return the raw `Response` and does not change existing
call-site status semantics. When a protected request returns `401`, it publishes
the authentication-required event. The global gate clears the invalid session
token and opens.

The request is not replayed. In particular, `POST`, `PUT`, `PATCH`, and
`DELETE` requests remain single-attempt operations. After a successful unlock,
the route reload restarts normal reads from a clean application state.

## Runtime Rules

The gate is enabled only when all conditions are true:

- the frontend is not running under Vite development mode;
- the browser origin is HTTP or HTTPS;
- the hostname is not `localhost`, `127.0.0.1`, or `::1`;
- no non-empty token exists in the current tab session.

Tauri origins and loopback deployments retain their existing behavior.

## Accessibility And Interaction

- Focus moves to the token field when the gate opens.
- The form supports Enter to submit.
- The input is a password field and is never echoed in an error.
- Checking and error states are announced through an `aria-live` region.
- The gate cannot be dismissed while authentication is required.

## Error Handling

- `401`: access token is invalid.
- Timeout or network failure: backend is unreachable.
- Non-`200` response: backend returned an unexpected response.
- Invalid or unhealthy JSON: backend health validation failed.

Errors remain local to the unlock window. They do not overwrite page business
state because protected content has not mounted.

## Test Strategy

- Pure runtime tests cover loopback, LAN IPv4, LAN hostname, Tauri, Vite, and
  existing-token decisions.
- Request tests prove successful validation stores the token only after a
  healthy protected response.
- Failure tests cover `401`, timeout, network error, invalid JSON, and unhealthy
  payload without token persistence.
- `apiFetch` tests prove a protected `401` publishes one auth-required event,
  preserves the raw response, and never replays the request.
- Component tests verify locked, checking, and error states plus keyboard and
  accessibility behavior.
- Existing frontend tests, typecheck, production build, backend tests, and the
  unified project check remain required.
- Browser smoke checks cover direct production access with an empty session,
  invalid-token feedback, successful unlock, populated ingest data, one WebGL
  canvas, and zero console errors.

## Non-Goals

- No automatic cookie issuance.
- No token persistence beyond the current browser tab.
- No authentication API or database schema change.
- No generic request retry or mutation replay.
- No redesign of navigation, pages, dock, or WebGL effects.
