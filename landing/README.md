# Landing page

Static, self-contained, no build step. Showcases clipper — it doesn't process video and
makes no backend calls.

## Deploy (Netlify)

**Drag-and-drop:** [app.netlify.com/drop](https://app.netlify.com/drop), drop this `landing/`
folder.

**Git-connected:** point Netlify at this repo with publish directory `landing` (already
configured in the root `netlify.toml`), build command empty.

## Local preview

Just open `index.html` in a browser — no server needed.

## Assets

`assets/demo.gif` (added in the demo-assets pass) is this page's own copy of the capture used
in the root README, so the deployed site never depends on files outside `landing/`.
