# AutoMeta Phase 1C React and Library Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the production React/Vite shell, Logo A, responsive design system, New Review flow, Library, and persisted Review workspace against the Phase 1B APIs.

**Architecture:** Keep `frontend/` as typed source and build committed assets into `autometa/static/`. React Router owns page navigation, TanStack Query owns server state, and components consume only `/api/v1` contracts. The branch is not merged until the later workflow-migration plan replaces all legacy stage screens.

**Tech Stack:** React 18, TypeScript 5, Vite, React Router 7, TanStack Query 5, TanStack Table 8, Vitest, Testing Library, CSS custom properties.

## Global Constraints

- English-only product UI using the manuscript's Logo A and editorial-precision visual language.
- No online fonts, CSS frameworks, CDN scripts, benchmark data, manuscript data, or example dataset.
- Every enabled action calls a real API or performs a real local state transition.
- Guided Review and independent Search, Screening, Extraction, and Meta-analysis entry modes are available.
- API keys never enter frontend state.
- Desktop and large-tablet support begins at 1024 px; phone support is out of scope.
- Compiled frontend assets are committed so runtime users do not need Node.js.
- Use test-first implementation and keep the backend suite green.

---

### Task 1: Scaffold the typed frontend and deterministic build

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/package-lock.json`
- Create: `frontend/tsconfig.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/index.html`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/App.tsx`
- Create: `frontend/src/test/setup.ts`
- Create: `frontend/src/App.test.tsx`
- Modify: `.gitignore`
- Modify: `.github/workflows/foundation.yml`
- Modify: `pyproject.toml`

**Interfaces:**
- Produces: `npm run build`, `npm test -- --run`, and committed assets under `autometa/static/`.

- [ ] Write an `App` smoke test asserting the AutoMeta brand and Library route.
- [ ] Run Vitest and confirm it fails before the frontend exists.
- [ ] Add React/Vite configuration with `build.outDir = "../autometa/static"`, `emptyOutDir = true`, and relative asset paths.
- [ ] Implement a minimal router with `/library`, `/reviews/new`, and `/reviews/:reviewId/*`.
- [ ] Run unit tests, typecheck, and build; verify `autometa/static/index.html` and hashed assets exist.
- [ ] Extend CI with Node 20, `npm ci`, frontend tests, typecheck, build, and a clean-build diff assertion.
- [ ] Commit as `build: add React frontend foundation`.

### Task 2: Implement design tokens and Logo A shell

**Files:**
- Create: `frontend/public/autometa-mark.svg`
- Create: `frontend/src/components/AutoMetaLogo.tsx`
- Create: `frontend/src/components/AppShell.tsx`
- Create: `frontend/src/components/StageRail.tsx`
- Create: `frontend/src/components/ProvenanceRail.tsx`
- Create: `frontend/src/styles/tokens.css`
- Create: `frontend/src/styles/global.css`
- Create: `frontend/src/components/AppShell.test.tsx`

**Interfaces:**
- Produces: reusable shell components and typed stage states `not_started | running | draft | awaiting_approval | approved | failed | interrupted | stale`.

- [ ] Write failing component tests for Logo A accessible text, top navigation, four agents, checkpoint labels, and active/done/stale states.
- [ ] Implement the exact Logo A geometry as a standalone SVG and React component.
- [ ] Port the approved navy/blue/teal/purple/ochre tokens without importing paper assets.
- [ ] Implement desktop/large-tablet shell and horizontal overflow protection below 1024 px.
- [ ] Run component tests, typecheck, and build.
- [ ] Commit as `feat: add AutoMeta application shell`.

### Task 3: Add typed API client and query infrastructure

**Files:**
- Create: `frontend/src/api/client.ts`
- Create: `frontend/src/api/types.ts`
- Create: `frontend/src/api/reviews.ts`
- Create: `frontend/src/api/system.ts`
- Create: `frontend/src/api/client.test.ts`
- Modify: `frontend/src/main.tsx`

**Interfaces:**
- Produces: `apiRequest<T>()`, Review CRUD hooks, System Status hook, and a shared `QueryClient`.

- [ ] Write failing tests for JSON success, 204 responses, structured API errors, and network failure.
- [ ] Implement an `/api/v1`-rooted fetch client that never reads credentials from browser storage.
- [ ] Define exact TypeScript models matching Review and System Status schemas.
- [ ] Add TanStack Query provider and stable query keys.
- [ ] Run tests and typecheck.
- [ ] Commit as `feat: add typed AutoMeta API client`.

### Task 4: Build the real Library page

**Files:**
- Create: `frontend/src/pages/LibraryPage.tsx`
- Create: `frontend/src/components/ReviewCard.tsx`
- Create: `frontend/src/components/DeleteReviewDialog.tsx`
- Create: `frontend/src/pages/LibraryPage.test.tsx`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: Review list/open/rename/delete APIs.
- Produces: searchable Library with exact-name deletion confirmation.

- [ ] Write failing tests for loading, empty, error, search, open, rename, and exact-name delete states.
- [ ] Implement the Library with real API mutations and cache invalidation.
- [ ] Require exact Review name before enabling permanent delete.
- [ ] Display entry mode, current stage, status, and modification time without fabricated metrics.
- [ ] Run tests, typecheck, and build.
- [ ] Commit as `feat: add persistent Review Library UI`.

### Task 5: Build New Review and all entry modes

**Files:**
- Create: `frontend/src/pages/NewReviewPage.tsx`
- Create: `frontend/src/components/EntryModeCard.tsx`
- Create: `frontend/src/pages/NewReviewPage.test.tsx`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `POST /api/v1/reviews`.
- Produces: Guided, Search, Screening, Extraction, and Meta-analysis Review creation.

- [ ] Write failing tests for trimmed names, required mode, all five choices, API error, and successful navigation.
- [ ] Implement the mode cards with concise descriptions of required inputs.
- [ ] Create the Review and navigate to `/reviews/:id/setup` for Guided or the selected stage route for independent modes.
- [ ] Do not include Load Example or benchmark controls.
- [ ] Run tests, typecheck, and build.
- [ ] Commit as `feat: add Review creation modes`.

### Task 6: Build the persisted Review workspace shell

**Files:**
- Create: `frontend/src/pages/ReviewWorkspace.tsx`
- Create: `frontend/src/pages/ReviewSetupPage.tsx`
- Create: `frontend/src/pages/StagePendingPage.tsx`
- Create: `frontend/src/hooks/useReviewArtifacts.ts`
- Create: `frontend/src/pages/ReviewWorkspace.test.tsx`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: Review detail and artifact list APIs.
- Produces: real Review header, stage rail, setup route, stage state derivation, and disabled unavailable actions.

- [ ] Write failing tests for Review loading/not-found, entry-mode route, artifact-derived stage states, and stale indicators.
- [ ] Implement the Review chip, four-agent rail, artifact handoff labels, and bottom provenance summary.
- [ ] Implement editable Review name and persisted Review metadata display.
- [ ] Render explicit disabled/pending stage content until each stage is migrated; do not render clickable controls without handlers.
- [ ] Run tests, typecheck, and build.
- [ ] Commit as `feat: add persisted Review workspace shell`.

### Task 7: Frontend integration and visual gate

**Files:**
- Modify as needed: files created in Tasks 1–6
- Create: `tests/api/test_frontend_build.py`
- Modify: `README.md`

**Interfaces:**
- Produces: FastAPI-served compiled React application and documented frontend contributor workflow.

- [ ] Write a failing backend test that asserts the packaged root references the Vite bundle and client-side routes fall back to `index.html` without intercepting `/api/v1`.
- [ ] Implement SPA fallback and cache rules: no-cache for HTML, long immutable cache for hashed assets.
- [ ] Run `npm test -- --run`, `npm run typecheck`, and `npm run build`.
- [ ] Run the complete Python suite and wheel-content check.
- [ ] Start Uvicorn and browser-test Library, New Review, Review Setup, navigation, delete confirmation, empty/error states, and 1024/1440/1920 widths.
- [ ] Verify no console errors, external font/CDN requests, dead enabled controls, or experiment content.
- [ ] Commit as `feat: serve the AutoMeta React workspace`.

## Completion Criteria

- React source and compiled assets are committed and reproducible.
- Ordinary users need only Python dependencies and `.env` to run the UI.
- Logo A matches the manuscript geometry.
- Library CRUD and all five Review entry modes use real APIs.
- Review workspace state derives from persisted Review and artifact data.
- No benchmark/example content or API key reaches the frontend.
- No enabled dead controls exist.
- Browser layouts pass at 1024, 1280, 1440, and 1920 px.
- Backend and frontend automated suites pass without warnings.
- The branch remains separate until four-stage React migration is complete.
