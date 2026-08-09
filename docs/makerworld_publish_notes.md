# MakerWorld publish/update process notes

## STATUS (resume here) — as of 2026-08-07

(Previous status was 2026-07-16 night; the multi-profile work described in loose end #3 has
since been built. See "Update 2026-08-07" at the end of this section.)

**Goal:** script a repeatable MakerWorld update process, then use it to push
the real openGrid Beam geometry change live.

**Done:**
- All update mechanics validated by hand via chrome-devtools MCP on a
  disposable test model (`model_pages/_test_fixture/`, MakerWorld model
  `3055595`, Private): `.3mf` "Replace File", `.scad` delete+reupload, the
  "Model Data Changed?" notify dialog, filename conventions. Full writeup
  below in this file.
- Changelog-in-description plumbing built and validated (`scripts/scad_builder.py`
  canonical sections + both base templates render `sections.changelog` last).
  `model_pages/opengrid_beam/sections/changelog.md` now has a real entry.
- `makerworld_profile_id` added to all real model configs (beam=2633738,
  facade=2665104, snap=2688055, basket=2754279 — basket has 3 profiles total,
  only the first is captured; see note in its config).
- **`scripts/makerworld_update.py` written AND validated end-to-end**, both
  against the test fixture and for a real, live update: `opengrid_beam`'s
  Standard/Full print profile (`2633738`) was updated for real with 21 new
  variants (see "openGrid Beam: Full/Lite split" below) and confirmed live
  via chrome-devtools MCP (Verifying queue empty, Failed queue empty, the
  profile edit page shows the new `opengrid_beam.3mf`). `--scad`
  delete+reupload path is written but still untested through this script
  (was validated manually via chrome-devtools MCP only, pre-dating this
  script) — see "Not done" below.
- Fixed a real bug in `poll_verification`: it was declaring success ~8s
  after Publish because "model not found in the Verifying list" was treated
  as "already cleared" — but there's a lag before an item actually lands in
  that queue, so checking too early reads as a false positive. Caught this
  because after the live beam update the script reported success while
  Jonathan could still see it genuinely verifying in the UI minutes later.
  Fixed by waiting for the item to actually appear in the queue first, then
  polling for it to clear (see `poll_verification` in the script).
- Worked out the real browser-connection story, which turned out to be a
  significant departure from the original plan — see "Browser connection:
  what actually works" below. Short version: Playwright must attach to your
  **already-running main Chrome** via a WebSocket endpoint read out of
  Chrome's own `DevToolsActivePort` file, using the native
  `chrome://inspect/#remote-debugging` toggle (Chrome 144+). Launching Chrome
  yourself (Playwright's `launch_persistent_context`, or even manually with
  `--remote-debugging-port` against any profile) does not work — see that
  section for why.
- **openGrid Beam: Full/Lite split into two print profiles — DONE, both
  live.** See dedicated section below for the why. Short version: while
  rebuilding beam from current `models/` state to add new corner-end
  variants, hit Bambu Studio's 36-plate-per-3mf limit at 42 variants. Split
  into:
  - `model_pages/opengrid_beam/` — Full, 21 variants, profile `2633738`
    ("Standard Print Settings"), updated live via `update`.
  - `model_pages/opengrid_beam_lite/` — Lite, 21 variants, profile
    `3442733` ("Lite Print Settings"), published live via `new-profile`
    (first-time publish of this profile, 2026-07-16).
- **`scripts/makerworld_update.py new-profile` written and validated**,
  including a real live run. Restructured the script into `update` /
  `new-profile` subcommands to fit. Rehearsed twice for real against the
  disposable test fixture (profiles `3442701`, then `3442721`) before ever
  touching the live beam listing -- found and fixed three real bugs in the
  process, all confirmed via chrome-devtools MCP against the actual pages,
  not just by reading the script:
  - Print Profile Name has to be filled **last**, right before Publish --
    MakerWorld auto-populates it asynchronously once the 3mf finishes
    server-side processing, which silently overwrote an early `--name` fill
    (confirmed: first test run published with the auto-default name instead
    of the one passed in).
  - `find_new_profile_id` must match by **model URL**, not by profile name
    -- names like "0.2mm layer, 2 walls, 15% infill" are MakerWorld's own
    default and collide across many unrelated models on the same account's
    profile list, so name-matching could grab the wrong profile's id
    entirely. Matches `a[href*="/models/{model_id}-"]` on the (newest-first)
    Published Print Profiles list instead.
  - `poll_verification`'s match string must NOT be `cfg['project_name']` for
    `new-profile` -- confirmed broken for real on the beam Lite run:
    `opengrid_beam_lite`'s project name ("openGrid Beam Lite") is our own
    file-naming convention and doesn't exist on the actual MakerWorld model,
    which is titled plain "OpenGrid Beam" (same underlying model as Full).
    `run_new_profile` now matches on the `--name` value actually set
    instead (falls back to project_name with a warning if `--name` wasn't
    given, since MakerWorld's own auto-fill can't be predicted).
  - Also added `check_not_challenged()`: Cloudflare's interactive "Verify
    you are human" checkbox challenge appeared mid-run **three separate
    times** across this session's testing, even on an approved CDP session
    (during `poll_verification`'s repeated polling, and separately during
    plain chrome-devtools MCP navigation -- not specific to the script).
    Every time it happened, the underlying action had already succeeded
    (Publish went through fine; only the *next* navigation got challenged)
    -- confirmed by checking the Published Print Profiles list after
    solving the challenge by hand. So: expect this to happen periodically,
    the script fails loudly with "solve it by hand, then re-run" instead of
    misreporting, and the actual work is very likely already done when it
    does -- check the live listing before assuming a re-run is needed.
    Deliberately does not attempt to click through the challenge itself.

- **`scripts/makerworld_comments.py` written AND validated against the test
  fixture** (`list-comments`, `feed`, `reply`, `resolve` all confirmed live;
  `create-issue` reviewed but deliberately not live-tested — it's a thin
  `gh issue create` wrapper with no DOM risk, and Jonathan chose not to spam
  the real `zing3d-labs/openscad-models` repo just to rehearse it). Found
  and fixed four real bugs in the process, all root-caused via
  chrome-devtools MCP against the live page rather than guessed from error
  text — see "MakerWorld comment automation" section below for details.

**Loose ends / next steps, in order:**
1. Test fixture has accumulated throwaway junk from rehearsals (3 print
   profiles, 4 comments/replies) — deliberately left alone, Private and
   disposable, not worth the cleanup trip. Ignore.
2. The `--scad` delete+reupload path in the `update` subcommand is written
   but not yet tested against the new connection approach. Worth a test run
   against `_test_fixture --scad` before using it on beam (241 existing Customize
   uses at last check — see "Not tested" note further down about existing
   customizations).
3. ~~Basket (model `2505078`) needs the script extended for multiple print
   profiles before it can be used there — not started.~~ **The pipeline
   extension is now built and verified — see "Update 2026-08-07" below.**
   What still blocks the basket update is narrower than this item implied:
   only the medium/large `makerworld_profile_id`s are missing. MakerWorld/Reddit
   comments already posted saying the beam is updated and basket will follow.

**Everything from that session is committed** (`dfe66c1` and earlier). The
`models` submodule still shows as dirty (`external/QuackWorks` bump) — that
was already there at the start of that session, unrelated to this work.

### Update 2026-08-07 — multi-profile pipeline built and verified

Loose end #3 was written as "not started", but the work had in fact been started and was
sitting **uncommitted** in the `model-publishing` primary clone, on a stale reused branch
(`update-models-submodule`, whose remote had been deleted after PRs #4/#5 merged). It has
been committed and moved to its own worktree/branch.

**Built:**
- `scripts/model_config.py` — merges a model-level `model.yaml` into each profile's
  `build_config.yaml` (profile wins on collision), plus `project_slug()` so each profile gets
  its own `dist/` directory. Without that, profiles collide: every profile of a model shares
  the same `project.name`.
- `grid_basket` split into `small`/`medium`/`large`; `opengrid_beam` into `full`/`lite`. The
  old `model_pages/opengrid_beam_lite/` is folded into `opengrid_beam/lite/`, with shared
  images and sections de-duplicated up to the model level.
- **Backward compatible on purpose**: a model with no `model.yaml` loads flat, exactly as
  before. Single-profile models (`opengrid_facade`, `opengrid_dual_sided_snap`,
  `_test_fixture`) are deliberately *not* migrated. Don't "finish the migration" — there
  isn't one.

**Verified** (2026-08-07): `scad_builder.py <config> -d` run against all 7 configs — the 5
multi-profile ones and the 2 flat ones — all report success. Seven distinct `dist/`
directories, no collisions. `grid_basket_small`'s generated MakerWorld description renders all
three of Small/Medium/Large from `model.yaml`'s `profiles:` list. Caveat: `-d` skips OpenSCAD,
so **image rendering is still unexercised** — a full build has not been run.

**Still open:** `grid_basket/medium` and `grid_basket/large` have no `makerworld_profile_id`
(placeholder comments in each config), so they build and render locally but cannot be
published. `small` = `2754279` is set. Either look the ids up on the live listing or publish
them via `makerworld_update.py new-profile`. That is the only remaining blocker on the basket
update itself.

### Update 2026-08-09 — prebuilt models (no SCAD source)

Not every model we publish is authored in OpenSCAD. A build config can now declare a
`prebuilt:` block **instead of** `source:`, meaning "the `.3mf` already exists, there is
nothing to compile". See "Prebuilt models" below for the shape and the rules.

**Built:**
- `scripts/model_config.py` — `validate_geometry_source()` (exactly one of `source`/`prebuilt`,
  enforced on every config load), `is_prebuilt()`, `prebuilt_package_path()`.
- `scripts/scad_builder.py` — a prebuilt model skips compile, variant export, 3MF packing and
  image rendering, and generates descriptions, the one output that needs no source model.
  `variants:` is no longer required for such a config. `-i/--images-only` is a hard error.
- `scripts/makerworld_update.py` — `resolve_dist_files()` became `resolve_upload_files()` and
  takes a prebuilt branch that uploads the committed package **straight from `model_pages/`**.
  Deliberately not copied into `dist/`: that's gitignored and any `clean_before_build` wipes it.
  `--scad` is refused for a prebuilt model (there is no customizer source to upload).

**Verified** (2026-08-09) against `model_pages/_test_fixture_prebuilt/`, a disposable fixture
whose package is a copy of `_test_fixture`'s packed output: descriptions generate; the resolved
upload path is the committed `.3mf` and contains no `dist/` component; `--scad` and
`--images-only` both refuse. Malformed configs all fail loudly with actionable messages: package
loose beside the config, package escaping the config dir, package missing, package not a `.3mf`,
empty `prebuilt` block, both `source` and `prebuilt`, neither. All 7 pre-existing configs still
build descriptions unchanged.

**Not done:** no prebuilt model has been published to MakerWorld yet — the first real one is the
ScanSnap openGrid shelf. The upload path itself is shared with normal models from
`resolve_upload_files()` onward, so only the file-resolution half is new and unexercised live.

## openGrid Beam: Full/Lite split into two print profiles

The current `models/` submodule HEAD (`4b9e8ae` on `main`) includes beam
corner-end geometry merged via PR #6 ("Beam corner pieces (WIP)" — the WIP
label is the author's own, in the PR title itself, not just commit
messages). Checked with Jonathan before shipping anything: the geometry
itself is fine to ship, but two things needed care:

- The `.scad` file's customizer defaults are `Corner_1 = Corner_2 =
  "Extended"`, and `build_config.yaml` didn't override them — so rebuilding
  naively would've silently switched every standard variant's default
  corner style. Decision: pin the original 14 variants to explicit
  `Corner_1: Flush, Corner_2: Flush` so their geometry is unaffected
  regardless of what the `.scad` file's defaults do in the future.
- Decision: also publish the new corner options as pre-baked downloadable
  variants (not just reachable via the live Customizer), for both 1- and
  2-extended-end styles, across all 7 lengths (2-8u) and both grid versions
  (Full/Lite) — 28 new variants, 42 total with the original 14.

Building all 42 into one `.3mf` failed: **Bambu Studio supports a maximum
of 36 plates per `.3mf`** (`stls_to_3mf.py` raises `ValueError` on pack,
after all 42 STLs had already rendered fine individually — it's purely a
packing-step limit). Resolved by splitting along the grid-version axis,
which was already the natural print-profile boundary:

- `model_pages/opengrid_beam/build_config.yaml` — Full (6.8mm) only, 21
  variants (7 lengths × Flush/1-Extended/2-Extended). Existing live profile
  `2633738`. **Updated live** — see STATUS above.
- `model_pages/opengrid_beam_lite/build_config.yaml` — Lite (4mm) only, 21
  variants, same shape. Same `makerworld_url` (same underlying model,
  `2402751`) but a genuinely separate print profile. `makerworld_profile_id`
  is intentionally absent from this config until that profile exists.

Notify choice for the live Full update: **no-notify**, deliberately — the
original 14 variants are geometrically pinned to their old Flush look, so
existing print-profile users' downloads are unaffected; this is additive
(14 new plates), not a change to what anyone already has. See
`model_pages/opengrid_beam/sections/changelog.md` for the public-facing
description-page changelog entry (separate from the "Model Data Changed?"
notify text, which was skipped).

## Adding a new print profile to an existing model

Different from everything else in this file, which is either first-time
publish of a whole new model, or "Replace File" on a print profile that
already exists. This is: model already exists, want to add an *additional*
print profile to it (needed for the beam Full/Lite split above). Not
documented anywhere obvious -- found by exploring the model page's owner-
only UI via chrome-devtools MCP.

- Entry point: on the model's own page (`/en/models/{id}-{slug}`), the "⋮"
  menu next to the category breadcrumbs (owner-only) has an **"Add Print
  Profile"** item, alongside Remix/Edit/Report. Clicking it navigates to
  `/en/my/profiles/publish?designId={modelId}`.
- That page ("New Print Profile") is a strict subset of the first-time
  model+profile publish flow's "Print Profile Information" step -- same
  fields (Print Profile Name, Print Profile Pictures, Visibility, Print
  Profile Description, Printer Compatibility, Print Plates preview, "I've
  read Print Profile Guidelines" checkbox), just without the Model
  Information step since the model already exists.
- The .3mf dropzone accepts non-Bambu-Studio-produced 3mf files fine (same
  as the "Replace File" flow) despite the page saying "Only 3mf files
  produced by Bambu Studio are supported" -- that text is not enforced.
- **Print Profile Pictures upload has no accessible role/uid** -- MakerWorld
  renders the "Add Photo" button's actual `<input type="file">` as
  `display:none` with `tabindex="-1"`, so it's invisible to the DevTools
  accessibility tree entirely (not just hidden-but-reachable like the .3mf
  dropzone). chrome-devtools MCP's `upload_file` tool, which needs a uid,
  cannot reach it at all. Playwright doesn't have this limitation --
  `page.locator(...).set_input_files()` works on hidden inputs regardless.
  Found the right one by dumping all `input[type="file"]` on the page via
  `evaluate_script` (three total: `.3mf` dropzone, this one at
  `accept="image/jpeg, image/png, image/webp, image/gif"`, and an unrelated
  one for the top-nav "search by image" feature) and confirming by walking
  up each input's DOM ancestors for nearby text.
- No "Model Data Changed?" dialog on this flow (that's specific to
  *replacing* an existing profile's file) -- Publish submits straight into
  the same async Verifying queue as everything else.
- The new profile's id isn't shown anywhere on this page or in any redirect
  after Publish. Found after verification clears by going to
  `/en/@{username}/profile` (Published Print Profiles, sorted newest-first)
  and matching the first link pointing at `/models/{model_id}-` -- the id
  is the `#profileId-XXXXX` fragment on that link. See
  `find_new_profile_id()` in the script, and the name-collision gotcha
  logged in STATUS above (don't match by profile name).

## MakerWorld comment automation (scripts/makerworld_comments.py)

`list-comments`, `feed`, `reply`, and `resolve` were rehearsed against the
test fixture's one throwaway comment before any of this touched a real
model thread. Four real bugs found, all root-caused by reading the live DOM
via chrome-devtools MCP's `evaluate_script`/`take_snapshot` rather than by
guessing from Playwright's error text:

- **Comment timestamps render as relative text for anything recent** ("32
  seconds ago", "13 minutes ago") and only switch to the absolute
  `YYYY-MM-DD HH:MM` format once enough time has passed. A regex that only
  matched the absolute form silently found zero comments for anything
  posted in the current session — `list-comments` on a page with a real,
  visible comment returned `[]` with no error. Fixed by matching both forms
  (see `TS_RE` in `EXTRACT_COMMENTS_JS`).
- **The per-comment threaded "Reply" control is a different UI element from
  the top-level page composer.** The top-level composer's placeholder reads
  "Please fill in your opinion"; clicking *that* when you meant to reply to
  a specific comment fails with Playwright reporting the real
  `contenteditable="true"` div "intercepts pointer events" on the
  placeholder span. Fixed by locating the actual editable div via
  `reply_control.locator('xpath=following::*[@contenteditable="true"][1]')`
  instead of text-matching a placeholder.
- **`page.goto()` to a URL that only differs by query string does not
  remount MakerWorld's React app**, so state from a previous run/failed
  attempt in the same browser tab — e.g. a reply composer left open because
  an earlier step threw — is still open on the next invocation. This broke
  `find_comment_reply_control`'s `text()="Reply"` match entirely (zero
  matches, 30s timeout) because the toggle already read "Cancel the reply".
  Fixed by matching either state and only clicking to open when it's
  currently closed — see `find_comment_reply_control()`.
- **`page.keyboard.type()` sends to whatever currently has OS-level focus
  with no re-check**, and dispatching it immediately after
  `composer.click()` silently dropped every keystroke here — the composer
  stayed at `(0/1000)` chars and its submit button stayed disabled, with no
  error raised (the script just hung waiting for a submit button that could
  never become enabled). Confirmed by comparing against a manual
  chrome-devtools MCP click+type on the same element, which worked
  immediately. Fixed by using the locator-scoped `composer.type(reply_text)`
  instead (re-focuses right before typing), the same pattern already used
  for the rich-text description editor in `update_print_profile()` — plus
  an explicit `page.wait_for_timeout(1000)` after typing, before hitting
  submit, per the same "let React's state settle" lesson learned there.
- **The threaded reply composer's submit button is labeled "Reply", not
  "Post"** — "Post" is the top-level page composer's button only, and it
  stays permanently disabled since that composer is empty. Looking up
  `get_by_role('button', name='Post')` page-wide found that unrelated,
  always-disabled button and hung waiting for it to become enabled. Fixed
  by scoping the lookup to the reply composer's own `<form>` ancestor and
  matching "Reply" instead.

`create-issue` (a `subprocess.run(['gh', 'issue', 'create', ...])` wrapper,
no browser involved) was reviewed but not live-tested — low DOM/selector
risk, and Jonathan chose not to create a throwaway issue on the real
`zing3d-labs/openscad-models` repo just to rehearse it.

## Browser connection: what actually works

This took a long debugging session to nail down; recording it so it isn't
re-litigated. The script drives Playwright, but Playwright cannot simply
launch or attach to "a Chrome" — three approaches were tried and failed
before finding the one that works:

1. **`launch_persistent_context` against any profile (fresh, or the
   `~/.cache/chrome-devtools-mcp/chrome-profile` dir)** — fails. Playwright
   launching Chrome itself adds automation flags (`--enable-automation`,
   which sets `navigator.webdriver = true`), and MakerWorld's Cloudflare
   check flags that immediately regardless of which profile/cookies are
   used. Confirmed via debug screenshot: "Performing security verification".
2. **Manually launching Chrome with `--remote-debugging-port` against the
   main/default profile** (`open -a "Google Chrome" --args
   --remote-debugging-port=9223`) — fails silently. Chrome refuses to open a
   remote-debugging port on the default user-data-dir at all, for security
   reasons, regardless of how cleanly Chrome is quit/relaunched first.
   `~/Library/Application Support/Google/Chrome/DevToolsActivePort` never
   updates, the port never listens. This is not fixable by retrying the
   launch differently.
3. **Manually launching Chrome against a *custom* profile dir** (e.g. the
   chrome-devtools-mcp cache dir) with `--remote-debugging-port` — the port
   *does* open (custom dirs aren't restricted), but that profile is
   essentially fresh (prompts "Sign in to Chrome" on open) and Cloudflare
   rejects it outright ("Incorrect device time" — likely a generic
   fallback message for an untrusted fingerprint, not a literal clock
   issue). This profile is not, in fact, pre-authenticated to MakerWorld in
   any way that survives Cloudflare's check.

**What works:** Chrome 144+ ships a native toggle at
`chrome://inspect/#remote-debugging` ("Allow remote debugging for this
browser instance") that enables debugging on your **already-running** main
Chrome — no relaunching, no flags, no separate profile. This is what
chrome-devtools-mcp's `--auto-connect` uses internally (confirmed by reading
its source: `chrome-devtools-mcp/build/src/browser.js`). Important
mechanics:

- It does **not** expose the classic CDP HTTP JSON API (`/json/version`,
  `/json/list` all 404). Instead, read Chrome's own `DevToolsActivePort`
  file directly from the profile's user-data-dir (for the default profile:
  `~/Library/Application Support/Google/Chrome/DevToolsActivePort`) — two
  lines, port number and a `/devtools/browser/{uuid}` path — and build
  `ws://127.0.0.1:{port}{path}` by hand. Playwright's `connect_over_cdp`
  accepts this raw `ws://` endpoint directly (confirmed in Playwright's own
  docs/examples). `scripts/makerworld_update.py`'s `resolve_ws_endpoint()`
  does exactly this.
- Chrome pops up an **"Allow remote debugging?" permission dialog every
  time a client connects** — by design, not persisted across runs (there's
  an open chrome-devtools-mcp GitHub issue requesting persistence). Someone
  has to be at the keyboard to click Approve each time the script runs.
  There's also a persistent "automated test software" banner while
  connected — cosmetic only.
- The script only ever opens/closes its own new tab (`context.new_page()`
  / `page.close()`) — it must never call `context.close()` or
  `browser.close()`, since this is the user's real browser with their real
  tabs, not a process the script owns.


Notes from building and testing browser-driven MakerWorld automation (via
chrome-devtools MCP). Captures what the UI actually does, since none of this
is documented officially. See `model_pages/_test_fixture/` for the disposable
model used to rehearse these flows without touching real listings.

## Browser automation setup

- Use `chrome-devtools-mcp` with `--auto-connect` (requires remote debugging
  enabled in the real Chrome profile via `chrome://inspect/#remote-debugging`)
  so the session reuses your real, already-logged-in browser. A fresh/isolated
  profile trips Cloudflare's bot check almost immediately.
- `mcp__chrome-devtools__upload_file` sets a file input directly — no OS file
  picker dialog to fight with. Works on drag-and-drop zones and on cover-image
  "Change" buttons alike.
- Rich text editors (model/print-profile descriptions) don't respond to
  `fill()` — the value doesn't stick. Use `click()` to focus, then
  `type_text()` with real keystrokes.

## Two independent upload surfaces per model

1. **Model edit page** — `/en/my/models/{modelId}/edit` → "Raw Model Files".
   Holds the `.scad` customizer source (powers the "Customize" / Parametric
   Model Maker button). No "replace" — only a delete icon that opens a
   confirmation dialog; the implied update flow is delete-then-drag-in-new.
   **Not yet tested**: what happens to the "Customize" button, `designId`, or
   people's saved customizations when you do this on an already-published,
   publicly-used model.

2. **Print Profile edit page** — `/en/my/profiles/{profileId}/edit` →
   "Bambu Studio File (Print Profile)". Holds the packed `.3mf` with all
   pre-baked plates. Has a clean, non-destructive **"Replace File"** button.

## Filename convention

`scad_builder.py`'s `compile_scad()` names its output `<stem>_cpl.scad`
(e.g. `opengrid_beam_cpl.scad`) to distinguish the compiled/library-inlined
build artifact from the raw source. When uploading to MakerWorld, rename to
drop the `_cpl` suffix (copy to `<stem>.scad` before upload) — this is purely
a publish-time cosmetic choice; the internal build naming stays as-is.

## Prebuilt models (no SCAD source)

Some models aren't authored in OpenSCAD — a CAD export, a hand-assembled plate,
someone else's geometry we're republishing. Such a config declares `prebuilt:`
**instead of** `source:`; the two are mutually exclusive and one is required.

```yaml
prebuilt:
  package: "package/fujitsu_scansnap_opengrid_sturdy_shelf.3mf"
```

Rules, all enforced at config load with a specific error message:

- The path is relative to the config's **own** directory — for a multi-profile
  model that's the profile subdirectory, one level below `model.yaml`, same as
  every other path in a merged config.
- It must live in a **subdirectory** of that directory, not loose beside the
  config. That gives the committed binary one obvious home alongside whatever
  came with it (CAD export, source STLs), and keeps `model_pages/<model>/` readable.
- It must be a `.3mf` and it must exist. Nothing builds it — it's committed.

What changes downstream:

- `scad_builder.py` generates **descriptions only**. There's nothing to compile,
  no variants to export, no packing to do and nothing to render, so it does none
  of it and says so. `-i/--images-only` is an error, not a silent no-op — real
  photos go under the model's `images/` directory.
- `variants:` is not required in the config (a prebuilt package's plates are
  already fixed).
- `makerworld_update.py` uploads the committed `.3mf` from `model_pages/`
  directly. It is **not** copied into `dist/` first: `dist/` is gitignored and
  `clean_before_build` would wipe it out from under the upload.
- `--scad` is refused — a prebuilt model has no customizer source, so the
  "Raw Model Files" upload surface simply doesn't apply to it.

`model_pages/_test_fixture_prebuilt/` is a disposable example of the layout.

## Photo requirement — real photos only

MakerWorld's moderation **rejects synthetic/rendered photos** with reason
"System detected no real life photo." This applies to:
- Model Covers (Web/App 4:3 and 3:4) on the model edit page
- Model Pictures on the model edit page
- Print Profile Pictures on the profile edit page

All of these need at least one real print photo, not an OpenSCAD render.
Failing this doesn't block the initial "Publish" click — it fails silently
later in an async moderation pass (see below) and lands in "Failed", not
"Verifying" or "Published".

## Publish flow (first-time upload)

From the navbar "Upload" button → "3D remix model" (or "3D original model"):

1. **Upload step**: "Do you have a Bambu Studio file (.3mf)?" → Yes. Upload
   the `.3mf` (Print Profile) and the `.scad` (Raw Model Files) together.
   A draft model is created as soon as this step completes — subsequent
   navigation goes to `/en/my/models/drafts/{draftId}/edit` (or
   `/publish` if you back out and re-enter).
2. **Model Information step**: Model Origin (required for Remix — search by
   URL, e.g. `https://makerworld.com/models/{id}-{slug}`), Model Name,
   Category, License, **Visibility (set Private for test fixtures)**,
   Description (needs `type_text`, not `fill`), Model Covers + Model
   Pictures (real photos required, see above).
3. **Print Profile Information step**: mostly auto-populated from the `.3mf`
   metadata — Print Profile Name (from slicer settings), Print Plates preview
   thumbnails (auto-rendered), Printer Compatibility (all checked by
   default). Still need: Print Profile Pictures (real photo, required) and
   the "I've read Print Profile Guidelines" checkbox before Publish/Save
   is enabled.

## Updating an existing print profile (`.3mf` "Replace File")

On `/en/my/profiles/{profileId}/edit`, uploading via "Replace File" and
clicking "Publish" pops a **"Model Data Changed?"** confirmation dialog —
this is the key thing to automate around for real updates:

- **"Did you change the model geometry of any object?"** — three radios:
  - "Yes. Users must be notified about the change." (default-checked)
  - "Yes, but no need to notify other users."
  - "No"
- Choosing the first reveals **"Notification Content"** — a free-text
  textarea (2000 char limit) plus an optional "Add Photo" — sent to
  "Users who uploaded print profiles for this model" (i.e. people using
  this model's downloadable print profile, not just viewers).
- Confirming submits straight into the same async "Verifying" queue as a
  fresh publish (see below) — no separate step.

For real models with actual users (e.g. openGrid Beam has 1 print profile,
openGrid Facade/Snap similar), this means every geometry-changing update
needs a real changelog message written here — this field should NOT be
left blank or filled with a placeholder for real updates. The build
pipeline doesn't currently generate change-log text; that has to come from
the person doing the update (or be drafted from the git commit history of
the affected `.scad` source).

Tested on the test fixture with both notify paths (see git history of this
file) — both went through Verifying → Published cleanly, no different
handling observed between the "notify" and "no need to notify" choices
beyond whether the notification is actually sent.

## Async verification after Publish

Clicking "Publish" doesn't mean live — it goes into an async moderation
queue. Check `https://makerworld.com/en/@{username}/verifying` immediately
after publish, then poll (took ~60-90s in testing) until it moves to either
`/en/@{username}/upload` (Published Models count increments — success) or
`/en/@{username}/verify-failed` (with a stated reason, e.g. the photo
rejection above). The failed-state "Edit" link
(`/en/my/models/drafts/{draftId}/publish`) re-opens the same draft with all
prior field values intact — only the flagged content needs fixing before
resubmitting.

**Timing gotcha, confirmed in practice on the live beam update:** there's a
real lag between clicking Confirm/Publish and the item actually landing in
the `/verifying` list — checking immediately can find nothing there yet and
wrongly conclude verification already passed. `scripts/makerworld_update.py`'s
`poll_verification()` now waits for the item to actually appear in the
queue before polling for it to clear, specifically to avoid this. If you're
checking by hand (e.g. via chrome-devtools MCP) right after a Publish click,
give it a few seconds before trusting an empty Verifying list.

## Test fixture reference

- Model: `Automation Test Fixture (Private)` —
  https://makerworld.com/en/models/3055595-automation-test-fixture-private
  (model id `3055595`), Private visibility.
- Local source: `model_pages/_test_fixture/` (kept out of the `models/`
  submodule deliberately — see that dir's `build_config.yaml` header).
- Build with `python scripts/scad_builder.py model_pages/_test_fixture/build_config.yaml`.

## Updating the `.scad` raw model file (delete + reupload)

Tested end-to-end on the test fixture: delete the old file (confirmation
dialog), upload the new one, then Publish → same "Model Data Changed?"
dialog as the `.3mf` flow → async Verifying queue.

Result: **safe**. Confirmed via the live "Customize" button after the
update cleared verification:
- Same `designId` (the model id) — the Parametric Model Maker URL is keyed
  off the model, not the specific raw-file upload, so the "Customize"
  button and its usage count survive a delete+reupload.
- New customizer parameters (a new `/* [Section] */` group and variable
  added to the source) show up correctly in the live customizer UI.
- New geometry (a changed default shape) renders correctly in the
  customizer's 3D preview.
- Filename shown to end users in the "Customizable" confirmation dialog is
  the renamed one (no `_cpl` suffix), confirming that convention works
  end-to-end, not just at upload time.

Not tested: what a user who already has open/saved customizations from the
old file sees — the test fixture had 0 real customize-uses at the time.
Treat that as still open before doing this on a real model with existing
Customize usage (e.g. openGrid Beam, 240 uses).

## Updating an existing print profile (`.3mf` "Replace File")
