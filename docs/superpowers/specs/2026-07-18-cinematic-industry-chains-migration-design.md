# Cinematic Industry Chains Migration Design

## Goal

Move the industry-chain workspace onto the finalized KI navigation shell used by content ingest, series, toolbox, and system center. Preserve the complete legacy industry-chain workflow while replacing the retired beam-template composition and its fragile responsive geometry.

## Product Structure

- Keep the shared `KiNavigationShell` unchanged: cinematic background, pointer reveal, top brand and Gooey navigation, top accessory slot, global action Dock, and responsive workspace scale.
- Use the same transparent middle-stage hierarchy as content ingest and series: `ki-shell-content` -> `ki-shell-legacy-ingest` -> embedded root -> `ki-ingest-split-stage`.
- Put the industry-chain list in the left pane and the complete selected-chain detail in the right pane.
- Do not add an industry overview, dashboard, intermediate landing state, second detail layer, or central beam.
- Keep `/#/industry-chains-old` and `/#/chains-old` unchanged for comparison.
- Keep `/#/industry-flow` as the existing full-network view instead of embedding it into the primary workspace.

## Top Region

- Keep the shared brand and main navigation exactly aligned with the other migrated pages.
- Place the industry-chain search input in `KiNavigationShell`'s top accessory area, aligned with the right edge of the middle workspace.
- Search must match both chain names and node names.
- Do not add page-specific headings above the middle workspace.

## Left Pane

- Render one compact spotlight row per industry chain.
- Each row shows a semantic chain icon, chain name, node count, and a short summary of node types.
- Preserve the current selected chain when data refreshes if it still exists; otherwise select the first available chain.
- Filtering must not mutate source data or force selection to a different hidden chain while the user is reading its detail.
- Empty, loading, and error states remain inside the list pane without changing stage geometry.

## Right Pane

- Mount the existing `ChainDetailModal` directly in embedded mode as the right-pane content.
- Preserve all legacy detail capabilities:
  - ordered node flow and flow summary
  - node expansion and source inspection
  - production, supply, and demand share data
  - substitute-path details
  - node editing and deletion through the existing editor
  - per-node and full-chain AI collection
  - cached AI chain report with explicit reanalysis
  - chain question-and-answer history and input
- Keep the complete detail visible by default. Do not introduce page-level accordion states that hide report, flow, or question-and-answer areas.
- Restyle the embedded detail as one continuous reading surface. Reduce nested card borders and opaque backgrounds without changing the legacy modal presentation used by old routes.
- Keep the selected chain's scroll and local expansion state stable when unrelated list data refreshes.

## Actions And Dialogs

- Handle industry-specific global Dock actions in place without navigating away from the current page.
- Use three industry-specific modal actions:
  - `新建节点` opens the existing `EditModal` with the current chain preselected.
  - `更新提示` opens the existing `HintsReviewModal`.
  - `新链建议` opens the existing suggestion review dialog.
- Keep `刷新数据` and `全景关系` as compact icon actions near the right-pane title because they affect the current workspace rather than creating modal content.
- Continue to use the existing endpoints and payloads. The migration must not introduce parallel APIs or duplicate business state.

## Data And Request Lifecycle

- Load nodes, chain metadata, pending hints, and pending suggestions as one refresh snapshot.
- Abort an older snapshot request when a newer refresh begins or the page unmounts.
- Ignore stale responses so rapid refreshes cannot restore older chain data.
- Keep stable callbacks for detail operations and memoize derived chain groups, filtered groups, selected metadata, statistics, and node-type summaries.
- Preserve the embedded report rule: initial detail mount reads cached reports only; report generation occurs only after explicit reanalysis.
- Do not refetch the full industry-chain snapshot when the user only expands a node or switches report content.

## Visual Direction

- Match content ingest brightness, pointer reveal intensity, background scene profile, and transparent stage treatment.
- Use the existing industry palette as semantic accents rather than a single green theme:
  - amber for raw materials
  - blue for intermediate products
  - violet for components
  - emerald for terminals
  - cyan and violet for control and AI actions
- Keep typography compact and operational. Avoid decorative page cards, nested cards, incomplete borders, and large marketing headings.
- Use Lucide icons for chain rows, refresh, full-network view, editing, collection, review, and dialog controls.

## Responsive Behavior

- Use the shared continuous workspace scale instead of independent viewport transforms.
- At `2560x1440` and `1440x900`, preserve the content-ingest list/detail proportions and equal top/bottom workspace clearance.
- At `1180x820`, shrink the complete middle stage as one unit. The list must not cross into the detail pane, the detail header must remain visible, and the bottom Dock must not cover detail content.
- The right-pane detail must own its internal scrolling; the page body must remain fixed.
- Long country names, source URLs, report text, and chat content must wrap without changing pane width.

## Error And Empty States

- Show snapshot load failures inline while retaining the last successful data when available.
- Show an explicit no-chain state when the backend returns an empty node set.
- Keep node collection, chain collection, report, hint review, suggestion review, and editor failures local to their operation.
- Disabled and loading controls must keep stable dimensions to avoid layout shifts.

## Testing And QA

- Update composition tests to require `KiNavigationShell`, the shared split-stage hierarchy, one scene canvas, direct embedded legacy detail, top search, and preserved legacy routes.
- Add request-lifecycle tests for stale snapshot cancellation and selection preservation.
- Keep workspace tests for grouping, search matching, statistics, and non-mutating transforms.
- Extend the cinematic page performance baseline with industry-chain idle, chain switching, right-detail scrolling, node expansion, and report-tab interaction.
- Run the full cinematic test suite, focused chain tests, production Vite build, and `git diff --check`.
- Visually verify `2560x1440`, `1440x900`, and `1180x820` with real remote data after deployment.

## Non-Goals

- No redesign or replacement of the industry-flow graph engine.
- No backend schema or API changes.
- No removal of legacy comparison routes.
- No new statistics dashboard, overview tab, or duplicate report surface.
- No global navigation or Dock redesign.
- No accessibility expansion beyond preserving current semantic labels and keyboard behavior.
