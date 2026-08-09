# README Redesign Design

## Objective

Rewrite the repository README as the canonical project landing page for both public GitHub visitors and internal maintainers. The document must explain the product before its implementation, provide an executable development path, and retain only stable production-operation contracts.

The rewrite replaces the current mixed product overview, production snapshot, migration narrative, and retired deployment manual. It does not change application code, deployment behavior, or production state.

## Audience And Information Boundary

The README serves two audiences in this order:

1. Public visitors evaluating what Zhiji is and how its workflow fits together.
2. Maintainers developing, verifying, and releasing the system.

The public document may describe the production mechanism, but it must not expose environment-specific hostnames, IP addresses, access URLs, absolute server paths, token locations, backup filenames, or secret values. Current production build numbers and runtime snapshots are excluded because they become stale immediately.

This revision will not add product screenshots. The repository currently has no maintained interface screenshots, and adding temporary captures would create a new asset-maintenance obligation outside the documentation rewrite.

## Information Architecture

The README follows a product-first, progressively disclosed structure:

1. Project name and concise product positioning.
2. Core capabilities organized by the real workflow: capture, organize, research, think, act, and review.
3. Current application shape and high-level architecture.
4. Local quick start with pinned prerequisites and commands that match current entrypoints.
5. Configuration names, responsibilities, and security rules without example credentials.
6. Repository layout and ownership boundaries.
7. Development checks and focused test commands.
8. Native production deployment mechanism and its two supported command entrypoints.
9. Data protection, authentication, and secret-handling constraints.
10. Versioning, release responsibilities, and links to maintained project documentation.

The opening must answer what the product is, what it does, and how it is delivered before showing engineering details. It must state that the project is under active development and does not promise a hosted public service.

## Product And Architecture Content

The capability overview reflects implemented navigation and workflows rather than historical plans:

- content ingestion, source collection, queue tracking, transcription, title editing, and content organization;
- series and industry-chain research;
- brainstorming and concept development;
- tasks and AI-assisted judgment;
- study materials and review;
- system health, configuration, logs, database, and API documentation.

The architecture is summarized as a Flutter desktop WebView shell over a React, Vite, and Tailwind frontend, backed by FastAPI, SQLite, and filesystem storage. The README identifies `src/zhiji_backend` as the only backend source root and does not recommend the stale `app/scripts/dev.sh` or `app/scripts/start.sh` entrypoints.

## Quick Start And Configuration

The quick start uses the repository's pinned toolchain expectations:

- Python 3.12;
- uv 0.11.31;
- Node.js 22.17.0;
- npm 10.9.2.

It starts the backend with `uv run --frozen zhiji serve` and the frontend with `npm run dev` after frozen dependency installation. The instructions make clear that development uses separate backend and frontend processes.

Configuration documentation lists only supported variable names and their purpose. It explains API authentication, allowed hosts and origins, AI endpoint policy, and server-side credentials without disclosing real values. Persistent SQLite and ingestion files are explicitly treated as business data that requires separate confirmation before deletion.

## Maintenance And Deployment Content

The repository map covers only stable top-level ownership boundaries: backend, frontend, desktop shell, scripts, tests, and docs.

`./scripts/check.sh` is the primary quality gate. Focused backend tests, frontend tests, type checking, and production builds may be listed as diagnostic or faster feedback commands, but they do not replace the unified gate.

Production documentation describes the implemented native deployment contract:

- a versioned wheel containing the Web frontend;
- systemd supervision;
- immutable release directories and atomic `current` switching;
- pre-deployment SQLite backup;
- health checks, stability observation, and automatic rollback;
- one-time initialization through `./scripts/provision-production --dry-run` and `./scripts/provision-production`;
- routine release through `./scripts/deploy-production`;
- deployment only from a clean commit already pushed and equal to `origin/main`.

The commands are identified as locked internal production automation, not generic third-party installers. Environment-specific target details remain in code or restricted operational records rather than the public README.

## Versioning And Historical Material

The README explains the stable version contract: backend and Web share the `2.0.0` product version, while desktop releases append a monotonically increasing build number. It does not hard-code the currently deployed build.

The following material is removed:

- the retired Intel Mac production procedure;
- migration status and temporary coexistence statements;
- current or rollback build snapshots and backup filenames;
- historical governance-stage summaries and frozen line-count tables;
- the `v1.3.9` repair summary;
- long manual release transcripts that duplicate executable scripts;
- stale remote QA URLs and commands.

Git history and `desktop/changelog.json` remain the sources for historical detail. Current source files, lock metadata, and executable scripts remain the sources for architecture and operational behavior; the rewrite must not link stale documentation as authoritative.

## Verification And Acceptance Criteria

The rewrite is complete when:

1. A new visitor can identify the product, its main workflow, and its application shape from the opening sections.
2. A maintainer can install dependencies, start both development processes, find subsystem ownership, and run the main checks using commands verified against the repository.
3. Production deployment is described accurately without environment-specific identifiers or a stale runtime snapshot.
4. No command references the retired `backend.main:app` entrypoint or the retired Mac deployment.
5. No secret value, private access endpoint, host alias, real server path, or token location appears in the README.
6. Product and tool versions agree with the tracked version files and lock metadata.
7. Markdown links and referenced commands resolve in the current checkout.
8. The change remains documentation-only apart from this approved design record.
