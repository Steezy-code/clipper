# PLAN — clipper → premium portfolio project

Staged, reversible, approval-gated. **The AI pipeline (`transcribe`, `score`, `crop`,
`captions`) is protected. No stage below modifies engine logic.** Only Stage C touches a
file that *calls* the engine (`static/index.html`), and it preserves every `fetch()` call
verbatim — reskin is CSS/markup only.

Design language applied throughout:
- **Dark "asphalt" command rail** (charcoal ~`#14171E`) + **light "plan-sheet" workspace**
  (warm paper ~`#F5F3EE`).
- **One accent:** the existing signal orange `#FF5C38` (already the brand — keep it).
- **Tabular mono numerals** (e.g. IBM Plex Mono / JetBrains Mono) for every number:
  scores, durations, timestamps, percentages.
- **Signature element:** the **virality-score gauge** (semicircular meter + tabular-mono
  numeral). Hero on the landing page; per-clip score in the app.
- Explicitly reject: purple gradient blobs, glassmorphism, default-Tailwind hero.

---

## Stage 0 — Public-repo hygiene & scrub  *(do first)*

- [ ] Remove internal planning docs that embed the personal path:
      delete `docs/superpowers/` (plan + spec). *(They're process cruft, not portfolio
      material, and the only source of a personal filesystem path in the repo.)*
- [ ] Re-scan tracked files for the personal path, emails, absolute paths → confirm clean.
- [ ] Verify `.gitignore` still covers `.venv/`, `__pycache__/`, `uploads//work//clips/`,
      `clipper/models/`, `brand.json`, `.env` (already good — confirm only).
- [ ] Keep `FINDINGS.md` / `PLAN.md` out of the public tree? **Decision needed** (default:
      keep — they show process maturity; they contain no secrets after Stage 0).

**Files:** delete `docs/superpowers/**`. **Pipeline risk:** none. **Rollback:** `git revert`
the hygiene commit (files recoverable from history).

## Stage A — Premium README, ARCHITECTURE.md, LICENSE

- [ ] `LICENSE` — MIT (confirm license choice).
- [ ] `README.md` premium rewrite: one-line hook → pipeline diagram (demo GIF deferred,
      see Stage D) → "what it does" → mermaid architecture diagram → tech stack → feature list →
      quickstart (already solid, keep) → honest "why I built it."
- [ ] `ARCHITECTURE.md` at repo root: refresh the stale `docs/architecture.md` to the current
      pipeline (adds hook+score, silence trim, punch-zoom, split/stream layouts, B-roll,
      regenerate, incremental render) and promote it as the senior-signal doc. Keep it
      engine-accurate — describes, does not change, the pipeline.
- [ ] `.env.example` — already present and correct; confirm only.

**Files:** `README.md`, `ARCHITECTURE.md` (new), `LICENSE` (new), retire `docs/architecture.md`
(fold into root). **Pipeline risk:** none (docs only). **Rollback:** revert docs commit.

## Stage B — Landing page (the clickable resume artifact)

- [ ] New self-contained static site in `landing/` (`index.html` + inline CSS/JS, no build,
      no backend calls, no external hosts except fonts).
- [ ] Sections: hero with the **virality-score gauge** signature + one-line value prop and
      GitHub CTA → demo GIF/video → "how it works" pipeline visual (transcribe → score →
      reframe → caption) → feature highlights (trim, layouts, B-roll, brand kit) → footer CTA.
- [ ] House style: asphalt command rail + plan-sheet workspace; tabular-mono numerals;
      responsive (mobile → desktop); fast; accessible contrast.
- [ ] `netlify.toml` (publish dir `landing/`) + a `landing/README` note for drag-drop deploy.

**Files:** `landing/**`, `netlify.toml`. **Pipeline risk:** none (isolated static site).
**Rollback:** delete `landing/` + `netlify.toml`.

## Stage C — App UI reskin (in-place, non-breaking)

- [ ] Reskin `static/index.html` to the house style: dark command rail for brand/controls,
      light plan-sheet workspace for drop zone + results.
- [ ] Premium states: idle/upload, processing (reuse the **real** progress the API already
      emits), results, error, empty.
- [ ] Tabular-mono numerals for scores/durations/timestamps; the **gauge** as the per-clip
      score element in results.
- [ ] **Preserve exactly:** every `fetch()` call, endpoint path, form-field name, and the
      `poll()`/incremental-render logic. This is markup + CSS + presentational JS only.

**Files:** `static/index.html` only. **Pipeline risk:** none — no Python touched; all API
contracts unchanged. **Verification:** diff the `fetch`/FormData lines before/after to prove
they're identical; run one real job to confirm upload→status→clips still works. **Rollback:**
`git checkout` the previous `index.html`.

## Stage D — Demo assets *(skipped by request)*

Deferred indefinitely — requires a screen recording only the user can capture. The README
hero and landing page demo section were left graceful without it (no broken image links):
the README leads with the pipeline diagram instead of a GIF, and the landing page's demo
section already shows a styled placeholder frame, not a dead `<img>` tag.

To add it later: run a real clip through the app, screen-record drop → progress → results,
trim to ~8–12s, export an optimized GIF, drop it at `docs/media/demo.gif` (README) and
`landing/assets/demo.gif` (landing — swap the placeholder comment in `landing/index.html`'s
`.device-body` for `<img src="assets/demo.gif" alt="clipper demo">`).
**Pipeline risk:** none. **Rollback:** remove media + references.

## Stage E — Ship

- [x] Netlify deploy checklist (drag-drop `landing/` **or** connect the repo, publish dir
      `landing/`) — delivered in chat; steps also live in `landing/README.md`.
- [x] Final public-safety pass (re-scan, confirm gitignore, confirm no secrets) — clean;
      also caught and redacted a personal path that had leaked into this plan's own audit
      commentary (FINDINGS.md/PLAN.md quoting the Stage-0 finding verbatim).
- [x] Deliver a 2–3 line **resume blurb** for clipper — delivered in chat.

**Pipeline risk:** none.

---

## Sequencing & risk summary

| Stage | Touches engine? | Reversible |
|---|---|---|
| 0 Hygiene | No | Yes (history) |
| A Docs/License | No | Yes |
| B Landing page | No | Yes (isolated dir) |
| C App reskin | **No** (view layer of `index.html` only; API calls preserved) | Yes (checkout) |
| D Demo assets | No | Yes |
| E Ship | No | Yes |

Every stage is its own commit so any single stage can be reverted independently.

## Open decisions for you
1. **License:** MIT ok? (default assumption)
2. **Keep `FINDINGS.md` / `PLAN.md` in the public repo?** (default: keep)
3. **Landing copy — anonymity:** brand it plainly as "clipper" by you (Steezy-code), or keep
   it project-only with no personal handle? (default: your GitHub handle, since it's your
   portfolio)
4. **Signature gauge** confirmed as the one hero element? (default: yes)

**STOP — awaiting your explicit "approved" before any Phase 3 execution.**
