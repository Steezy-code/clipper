# Landing page

Static, self-contained, no build step. Showcases clipper — it doesn't process video and
makes no backend calls.

## Deploy (Netlify)

**Drag-and-drop:** [app.netlify.com/drop](https://app.netlify.com/drop), drop this `landing/`
folder.

**Git-connected:** point Netlify at this repo with publish directory `landing` (already
configured in the root `netlify.toml`), build command empty.

## Local preview

Just open `index.html` in a browser — no server needed. Or serve it:
`python -m http.server 8766 --directory landing`.

## Assets

`assets/favicon.svg`, `assets/screenshot-idle.png` and `assets/screenshot-results.png` live
inside `landing/`, so the deployed site never depends on files outside it.
