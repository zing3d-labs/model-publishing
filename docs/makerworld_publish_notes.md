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
  only the first is captured; see note in its config). *(All three basket ids
  are now captured — see "Update 2026-08-08" below.)*
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
0. (added 2026-08-12) `new-model` exists and works — see "Update 2026-08-12". Rehearsed by the
   script itself, end to end, but only ever as far as **`--draft`**: nothing has been published
   through it, so read that update's "what is still unexercised" list (the Publish path, `--scad`,
   the remix Model Origin path) before the first real use. Three throwaway drafts were left
   behind on purpose (`9196491`, `9196793`, `9196815`), same as the other rehearsal junk below.
1. Test fixture has accumulated throwaway junk from rehearsals (3 print
   profiles, 4 comments/replies) — deliberately left alone, Private and
   disposable, not worth the cleanup trip. Ignore.
2. ~~The `--scad` delete+reupload path in the `update` subcommand is written
   but not yet tested against the new connection approach.~~ **DONE — run live
   against `_test_fixture` on 2026-08-18 and verified byte-for-byte. Found and
   fixed a real locator bug in the process; see "Update 2026-08-18 — `--scad`
   live-tested" below.** Still worth knowing before using it on beam (241
   existing Customize uses at last check — see "Not tested" note further down
   about existing customizations).
3. ~~Basket (model `2505078`) needs the script extended for multiple print
   profiles before it can be used there — not started.~~ **Done.** The pipeline
   extension is built and verified (see "Update 2026-08-07" below), and all three
   profile ids are now recorded (see "Update 2026-08-08" below), so all three
   basket profiles are publishable via `makerworld_update.py update`.
   MakerWorld/Reddit comments already posted saying the beam is updated and
   basket will follow — the basket geometry update itself is still to be pushed.

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
update itself. — **Resolved 2026-08-08, see below.**

### Update 2026-08-08 — basket profile ids recorded, no publish needed

All three basket print profiles **already existed live** on model `2505078`; nothing had to be
published. `new-profile` was never run, and shouldn't be for these — the existing profiles have
real print photos, download counts and Customize history that a fresh profile would not.
Recorded in the configs:

| profile dir | live profile name | `makerworld_profile_id` |
| --- | --- | --- |
| `grid_basket/small` | 3x3x3 Bast | `2754279` (already set) |
| `grid_basket/medium` | 5x5x5 Basket | `2758823` |
| `grid_basket/large` | 7x7x7 Basket | `2758832` |

Ids read off the live listing's per-profile URL fragment
(`.../2505078-opengrid-basket#profileId-XXXXXXX`) — the same `#profileId-` fragment
`load_project_config`'s error message points at. Verified by loading all three configs through
`makerworld_update.load_project_config()`: each resolves its own `profile_id`, its own
`dist/grid_basket_{small,medium,large}` slug, and the shared `verify_name` "openGrid Basket".

Note the live profile names are `NxNxN`-style, not the `Small/Medium/Large Basket` names used
in `model.yaml`'s `profiles:` list and the variant names — ours are description copy, MakerWorld's
are the actual profile titles. That mismatch is expected and is exactly why `poll_verification`
matches on `makerworld_model_name` rather than `project.name`.

Pushing the basket geometry update is now unblocked: `makerworld_update.py update
grid_basket/<profile>` for each of the three.

**A full build was finally run** (all three basket profiles, non-`-d`), closing the "image
rendering still unexercised" caveat above — STL, packed `.3mf` and both PNG renders all produced
for each profile. That run immediately caught a bug the `-d` runs structurally could not:

#### Packed `.3mf` filename now comes from `project_slug`, not `project.name`

`scad_builder.pack_3mf()` named its output from `project.name`, while
`makerworld_update.resolve_dist_files()` looks for `dist/<slug>/<slug>.3mf`. Post-restructure
those stopped agreeing for **every multi-profile config** — all three baskets built to
`opengrid_basket.3mf` and both beams to `opengrid_beam.3mf`, so `update`/`new-profile` died with
"not found. Build it first" on a build that had just succeeded. Same
`project.name`-is-shared-across-profiles collision `project_slug()` was introduced to fix, just
left unfixed one layer down at the filename. The two flat models only worked by coincidence
(`opengrid_facade` slugifies to its own directory name).

Fixed by naming the packed file `{project_slug}.3mf` in `pack_3mf()`, so both scripts derive it
from the same function. Verified: all 8 configs agree, no duplicate slugs.

**Found twice, independently.** PR #10 (`b234b6d`) landed the same `pack_3mf()` fix while this
branch was open, and also caught a second call site this branch never touched:
`ci_output_dir.py` printed `dist/test_fixture/descriptions` for `_test_fixture`, failing the
Publish workflow's upload step (`if-no-files-found: error`) — which is why CI had been red on
`main` since PR #8 merged. Two sessions hitting the same bug from different directions is worth
noting: `project_slug()` was introduced for the *directory* name in PR #8 and every other place
deriving that path from `project.name` was left behind, so expect stragglers if a third turns up.

Deliberate consequence — this is the filename users see on the profile page, and per-profile
names are better than three identical `opengrid_basket.3mf` downloads:

| config | packed filename | vs live |
| --- | --- | --- |
| `grid_basket/{small,medium,large}` | `grid_basket_<size>.3mf` | new |
| `opengrid_beam/full` | `opengrid_beam_full.3mf` | live is `opengrid_beam.3mf` — **renames on next push** |
| `opengrid_beam/lite` | `opengrid_beam_lite.3mf` | matches live |
| `opengrid_facade`, `opengrid_dual_sided_snap` | unchanged | unchanged |

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

**Its first real use** is `new-model` (see "Update 2026-08-12"): the prebuilt fixture is what that
subcommand was rehearsed against, so `resolve_upload_files()`'s prebuilt branch has now driven a
real MakerWorld upload rather than only a resolved path.

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

### Update 2026-08-09 — `--scad` live test staged (loose end #2)

Everything up to the browser is done; the live run itself has **not happened yet** — it needs a
human at the keyboard to approve Chrome's remote-debugging popup.

> **Superseded 2026-08-18:** the run has since happened and passed. Keep reading for the fixture
> rationale, but see "Update 2026-08-18 — `--scad` live-tested end to end" below for the outcome
> (and the locator bug it caught).

**Fixture prepared:** `model_pages/_test_fixture/test_fixture.scad` gained a new `/* [Lid] */`
parameter group (`Lid_Thickness`, default `0`). The default of 0 is the point: geometry — and
therefore the packed `.3mf` — is unchanged, which isolates the customizer source. If the live
customizer shows a **Lid** section after the run, the raw `.scad` was genuinely replaced. Without
a marker like this a clean exit only proves the script didn't throw, not that the new file landed.

**Pre-flight done without a browser:** a full build of `_test_fixture` (flat) and
`grid_basket/small` (multi-profile) both succeed, and `resolve_upload_files(..., need_scad=True)`
resolves real on-disk files for each — `.3mf` plus the `_cpl`-stripped `.scad`. So the file
resolution half of `--scad` is confirmed; only the browser half is untested.

Watch out for a stale-branch trap here: this work started on the pre-PR-#10 main and
"discovered" the artifact-naming bug that PR #10 had *already* fixed upstream (in the producer,
`pack_3mf`, rather than the consumer). Two opposite fixes for one defect would have re-broken it.
Rebase before concluding that something in this pipeline is broken.

Side effect of PR #10 worth knowing before the next real upload: the packed `.3mf` is now named
from the config slug, so the file MakerWorld shows end users changes for multi-profile models —
beam Full uploads `opengrid_beam_full.3mf` where it previously uploaded `opengrid_beam.3mf`.
Cosmetic, and arguably clearer now that profiles are split, but it *will* be visible on the
listing the next time beam is updated.

**To finish loose end #2** — Chrome running, logged into MakerWorld,
`chrome://inspect/#remote-debugging` toggled on, and approve the popup when it appears:

```bash
python3 scripts/scad_builder.py model_pages/_test_fixture/build_config.yaml
python3 scripts/makerworld_update.py update _test_fixture --no-notify --scad
```

Then confirm on the live listing that Customize still works, the model id / `designId` is
unchanged, and the customizer shows the new **Lid** group.
### Update 2026-08-12 — `new-model`, the first-time publish subcommand

`makerworld_update.py` had two subcommands and **neither created a model**: `update` replaces an
existing profile's file, `new-profile` adds a profile to an already-published model. Creating the
listing itself was the by-hand flow documented under "Publish flow (first-time upload)" below.
`new-model` automates that flow.

**Where its values come from.** Not from the config directly — from the *built* description,
`dist/<slug>/descriptions/makerworld_description.txt`. That file is already a flat
`=== FIELD ===` document (see `templates/makerworld_base.md`) carrying every value the publish
form asks for: MODEL NAME, LICENSE, CATEGORY, TAGS, SOURCE MODEL URLS, DESCRIPTION, PRINT PROFILE
NAME/DESCRIPTION. So what gets published is exactly what the build produced — the same text
`copy_description.py` puts on the clipboard for a by-hand publish, and it fails loudly if the
description hasn't been built. The parsing lives in `scripts/description_fields.py`, shared by
both scripts so the format is read in one place.

**Guard:** a config that already has `project.makerworld_url` is refused (`--force` overrides) —
that field existing *means* the listing exists, and `new-model` would create a second one.

#### DOM mechanics of the publish wizard

Everything below was worked out by driving the **live** wizard (chrome-devtools MCP against the
real logged-in browser) from the first click through to a saved draft, dumping the DOM at each
step — not read off the rendered page or guessed.

Entry point is the navbar "Upload" menu → `/en/my/models/publish?type=original` (or
`?type=remix`; there's a separate `/en/my/laser-and-cut-models/publish` we don't use). The
`type` comes from `templates.sites.makerworld.model_type`. Three steps: **Upload → Model
Information → Print Profile Information**.

**Step 1 — Upload.** "Do you have a Bambu Studio file(.3mf) for this model?" → answer
**"Yes (earn extra points reward)"** and the dropzones appear: `input[type=file][accept=".3mf"]`
for the print profile, and a Raw Model Files input (long `accept` list including `.scad`) for the
customizer source. `new-model` uploads the `.scad` by default for a SCAD model, since a
first-time publish is the one moment that upload isn't a delete+reupload; `--no-scad` skips it,
and a prebuilt model has no source to upload at all. Two other required questions live here —
"Does this model include a Laser & Cut model?" and "Is the model you uploaded a CyberBrick
model?" — both of which **default to No**, so the script deliberately leaves them alone.

- **"Next Step" is never disabled.** It is clickable from the moment the page renders, with no
  file attached at all. An earlier draft of this script waited for it to *become* enabled as its
  "upload finished" signal, which would have clicked straight through with nothing uploaded —
  caught by watching the live button's `disabled` property, which read `false` at t=0. The real
  signal is the dropzone swapping its prompt for the file's own name plus size and a "Replace
  File" control (`wait_for_upload()`).
- **Leaving step 1 creates the draft immediately** — the URL becomes
  `/en/my/models/drafts/<id>/edit`. From that point there is a listing on the account whether or
  not anything is ever published; it shows up under Draft on `/en/@{username}/upload`.

**Step 2 — Model Information.** MakerWorld's own markup does the addressing work: every section
carries a semantic class next to its hashed emotion classes, and the photo sections carry
validation-anchor classes (the `js-scroll-*` ones are what its validator scrolls to).

| what | selector |
| --- | --- |
| Model Name | `.modelName input` (also `input[name="title"]`) |
| Category | `.modelCategory input[role="combobox"]` |
| Tags | `.modelTags input[role="combobox"]`, chips read back at `.modelTags .tagItem-content` |
| License | `.modelLicense` (radios + a text summary) |
| Description | `.modelDescription [contenteditable="true"]` |
| Visibility | `.submitPrivate` (Public/Private radios) |
| Model Covers | `.js-scroll-cover input[type="file"]` — two, 4:3 then 3:4 |
| Model Pictures | `.js-scroll-designPictures input[type="file"]` (multiple) |
| Model Origin (remix only) | `.modelOriginals` |

- **Step 2 has no "Next Step" button** — that only exists on step 1. Its forward button is
  **"Add Print Profile"**, which lands on `/en/my/models/drafts/<id>/createPrintProfile`.
- **A blocked step transition is silent.** "Add Print Profile" simply does nothing while a
  required field is missing; the complaint is inline `.Mui-error` helper text ("Please set the
  model cover"). The script scrapes those and fails with them rather than hanging.
- **There is no license picker.** MakerWorld derives the Creative Commons license from radio
  questions and echoes back a human-readable name. All six rows were confirmed by answering the
  live form and reading the result:

  | config license | "Allow adaptations…?" | "Allow commercial uses…?" | MakerWorld shows |
  | --- | --- | --- | --- |
  | CC BY | Yes | Yes | Creative Commons Attribution |
  | CC BY-NC | Yes | No | Creative Commons Attribution-Noncommercial |
  | CC BY-SA | …as long as others share in the same way | Yes | Creative Commons Attribution-Share Alike |
  | **CC BY-NC-SA** (what our models use) | …as long as others share in the same way | No | Creative Commons Attribution-Noncommercial-Share Alike |
  | CC BY-ND | No | Yes | Creative Commons Attribution-NoDerivatives |
  | CC BY-NC-ND | No | No | Creative Commons Attribution-Noncommercial-NoDerivatives |

  A **third** question, "Allow sharing or redistributing of your work or its derivatives?",
  appears only when adaptations is "No", and decides between a CC NoDerivatives license and
  MakerWorld's own Standard Digital File License — the wizard's default state (all three No) is
  SDFL, not CC. It's also worth knowing this form is *dynamic*: an existing model's edit page
  shows the settled license as a read-only input holding the short `BY-NC-SA` form instead of the
  long name, so the script reads whichever is present. Either way it **re-reads the summary and
  fails on a mismatch** rather than trusting that the clicks landed.
- The literal `Yes`/`No` labels appear in *both* license groups, so a page-wide role+name lookup
  is ambiguous. Each radio is addressed by the question it answers instead:
  `//*[text()="<question>"]/following::label[normalize-space(.)="<answer>"][1]`.
- **Category and Tags are MUI autocompletes — typing alone sets nothing**, the dropdown option
  (`li[role="option"]`) has to be clicked. Tags additionally commit on Enter, but an Enter landing
  while a suggestion is highlighted commits *MakerWorld's* word rather than the typed one, so the
  script reads the resulting chips back and warns on any mismatch.
- **A Model Cover upload opens a crop dialog** ("Web/App cover 4:3", one Submit button). Until
  Submit is clicked the cover is *not* set and the form keeps reporting "Please set the model
  cover" — a silent trap, since the file input accepted the file perfectly happily. Only the 4:3
  cover is required; the 3:4 App cover is optional, so the script fills it only when a second
  `--cover` is given rather than cropping the same photo twice. Model Pictures and Print Profile
  Pictures have **no** crop dialog.
- Photo sections title themselves with a live count — "Model Pictures ( 1 / 16 )", "Print Profile
  Pictures ( 2 / 37 )" — which is the only confirmation an image upload landed, so the script
  waits on that.
- **Model Origin (remix only)** is not a plain URL field: click "Add", paste the model URL, and
  MakerWorld resolves it to a suggestion that must be clicked. Verified live — pasting
  `.../1304337-opengrid-tile-generator` surfaced "openGrid - Tile Generator / BlackjackDuck".
- **Model Name is filled LAST**, same hazard as `new-profile`'s `--name`: MakerWorld autofills it
  from the uploaded file asynchronously and will overwrite an earlier value.

**Step 3 — Print Profile Information** (`/createPrintProfile`):

| what | selector |
| --- | --- |
| Print Profile Name | `input[name="profileTitle"]` (inside `.printProfileName`) |
| Print Profile Pictures | `.printProfilePicture input[type="file"]` |
| Print Profile Description | `.printProfileDescription [contenteditable="true"]` |
| Guidelines checkbox | `input[name="instanceSetting.isPrinterTested"]` |

- The name field arrives **already auto-filled** from the .3mf's slicer settings (it read "0.2mm
  layer, 2 walls, 15% infill" by the time the step opened), which is exactly the race
  `new-profile` was bitten by — so it's filled last here too.
- One Print Profile Picture is inherited from Model Pictures (the count opens at 1, not 0).
- Printer Compatibility arrives with **every** printer checked and Print Plates renders itself
  from the .3mf; both are left alone.

#### Descriptions: pasted as HTML, not typed

The description is markdown, and CKEditor ignores `fill()` — but *typing* it would publish
literal `##` and `**`. Instead the script converts the markdown to HTML (the same
`markdown.markdown(..., extensions=['sane_lists'])` call `copy_description.py` uses) and
dispatches a synthetic `paste` event carrying `text/html`:

```js
const data = new DataTransfer();
data.setData('text/html', html);
element.dispatchEvent(new ClipboardEvent('paste', {clipboardData: data, bubbles: true, cancelable: true}));
```

Verified against the live CKEditor on the test fixture's edit page: `<h2>`, `<strong>` and
`<ul><li>` all survive as real editor blocks, exactly as a human pasting from
`copy_description.py` would get. Two details that matter: paste inserts **at the cursor**, so the
editor is select-all'd first (otherwise a retry interleaves with the previous attempt), and the
script asserts a chunk of the description is actually present afterwards — a silently-empty
description would otherwise only surface once the model was published.

#### What `new-model` deliberately does not do

State this plainly rather than letting the next person discover it mid-publish:

- **It cannot make a model go live without real print photos.** MakerWorld's moderation rejects
  renders ("System detected no real life photo") — see the photo section below — and nothing in
  the automation changes that. `--cover`/`--photo` take paths to *your* photos; with none given
  the script warns and the publish is expected to land in verify-failed. A model with only
  OpenSCAD renders can be driven all the way to a filled-in draft, and no further.
- **It does not touch Model Videos, Documentation, the Exclusive Model Program, or Printer
  Compatibility.** Compatibility arrives fully checked and is left that way; the rest are
  optional and stay empty.
- **It sets one print profile** — the one in the uploaded `.3mf`. A multi-profile model's other
  profiles are still added afterwards with `new-profile`.
- **It doesn't write the ids back into the config.** It prints `makerworld_url` and
  `makerworld_profile_id` for you to paste in, the same as `new-profile` does.
- **It won't touch an already-published model.** A config with `project.makerworld_url` is
  refused unless `--force`, because a second run would create a duplicate listing rather than
  update the existing one.

#### `--draft`: stop one click short

`--draft` fills the entire wizard and clicks **"Save to draft"** instead of Publish. Nothing
enters the verification queue and nothing goes live; the draft is listed under
`/en/@{username}/upload` for a human to check over and publish by hand. This is the safe default
for a first real use, and it's how this subcommand was rehearsed.

#### How far this was actually rehearsed — and what is still unexercised

Jonathan's call (2026-08-12) was to go **no further than draft**, so the rehearsal stopped one
click short of Publish on purpose.

**Exercised for real, against live MakerWorld, on the disposable prebuilt fixture**
(`model_pages/_test_fixture_prebuilt/`, whose committed `.3mf` was the upload): the whole wizard
start to finish, ending in a saved draft, with `Published Models (8)`, `Verifying (0)` and
`Failed (0)` unchanged throughout. First by hand through chrome-devtools MCP — which is what
produced every selector, the license table, the crop dialog, the "Add Print Profile" transition,
the `profileTitle` autofill and the never-disabled "Next Step" above — and then **by the script
itself**, `new-model _test_fixture_prebuilt --private --draft --cover … --photo …`, in ~26s of
browser time with no warnings.

The saved draft was then re-opened and read back field by field: Model Name "Prebuilt Test
Fixture" (ours, not MakerWorld's autofill), Category Organizers, tag `test`, license "Creative
Commons Attribution-Noncommercial-Share Alike", Visibility Private, cover set, Model Pictures
1/16, Print Profile Pictures 2/37 with both thumbnails, guidelines checkbox ticked, Print Plates
(1), no validation errors — and the description present as real editor blocks (four `<h2>`s,
`<strong>`, 1300 chars).

Three bugs the live runs caught that reading the code would not have:

- `Locator.evaluate(fn, arg)` passes `(element, arg)`, not a single array — the paste helper's
  `([element, html]) => …` signature blew up with "object is not iterable" the first time it ran.
- Waiting for a photo section's count to be merely **non-zero** passes instantly on the wrong
  photo: Print Profile Pictures opens at 1, having inherited a Model Picture, so the check cleared
  before our upload landed. It now records the count first and waits for it to *rise*
  (`upload_photos()`), which the next run showed doing exactly that: `1 -> 2`.
- (Before those, the never-disabled "Next Step" described above.)

**One nuance worth knowing, not a bug:** bullet lists in a description don't survive as lists.
`markdown.markdown(..., extensions=['sane_lists'])` needs a blank line before a list that follows
a paragraph, and the section templates don't leave one, so `- item` lines render as plain text.
This is the *existing* behaviour of `copy_description.py`, shared through
`description_fields.markdown_to_html()` — i.e. publishing via `new-model` produces exactly what
pasting from the clipboard by hand produces. Fixing it means putting a blank line before lists in
`templates/sections/`, which changes every model's copy, so it's deliberately left alone here.

**Not exercised:**
- **The Publish path.** `poll_verification()`, `find_new_model_id()` and `find_new_profile_id()`
  are wired up for `new-model` but nothing has been published through it, so the
  verification-queue and id-scraping half is still unproven for this subcommand. (Both of those
  finders are shared with, and proven by, `new-profile`.)
- **The `--scad` raw-file upload.** Only a prebuilt model was rehearsed, and a prebuilt model has
  no customizer source. `wait_for_raw_file_upload()` is written against the observed DOM (an
  uploaded raw file becomes a renamable text input holding the stem) but has never run.
- **The remix path.** The fixture is `model_type: original`, so `add_model_origins()` hasn't run
  inside a real publish — only the underlying interaction was confirmed by hand on an existing
  model's edit page (paste URL → click the resolved suggestion).
- **Unattended running is not a thing.** Every run needs someone to click Chrome's "Allow remote
  debugging?" popup, same as `update`/`new-profile`.

### Update 2026-08-18 — `--scad` live-tested end to end (loose end #2 CLOSED)

Ran `python3 scripts/makerworld_update.py update _test_fixture --no-notify --scad` against the
disposable fixture (model `3055595`, profile `3437877`). The path now works and is verified.

Scope note, because two different things are spelled `--scad`: this is **`update --scad`**
(`update_raw_model_file`, delete the existing raw file then reupload). It is *not* `new-model`'s
raw-file upload (`wait_for_raw_file_upload`), which loose end #0 correctly still lists as
unexercised — that is a separate function on the first-time-publish path and nothing here
touches it.

**Found and fixed a real bug — the reason this test was worth running.** The first live run
died mid-flight with a Playwright strict-mode violation:

```
strict mode violation: get_by_role("button", name="Browse", exact=True) resolved to 2 elements
```

Two elements on the Edit Model page answer to the accessible name `Browse`: the dropzone
(`<div role="button">`, the whole "Drag your files here" area) and the real `<button>` inside it.
This had never fired before because the `--scad` path had only ever been driven by hand.

Watch out for the obvious-looking fix, which is wrong: `button:text-is("Browse")` matches
**nothing**, because `:text-is` matches the *smallest* element holding the text and MakerWorld
nests the label in a couple of divs under the button. The fix that works is tag-scoping:
`page.locator('button').filter(has_text='Browse')` — one match, the real button. Confirmed by
probing the live page rather than by guessing a second time.

Also worth knowing: that page has **8** `input[type=file]` elements, so "skip the click and
call `set_input_files` on the file input" is not the easy shortcut it looks like.

**The delete is edit-form state, not an immediate API call.** `update_raw_model_file` deletes the
existing raw file *before* uploading the replacement, so a crash in between looks alarming — the
screenshot shows an empty "Raw Model Files" dropzone. It is not: because `Publish` is never
clicked on that path, closing the tab discards the deletion. Confirmed by probing the live model
after two failed runs — the raw file was still there both times. So a mid-flight `--scad` failure
leaves the model intact, and re-running is safe.

**How this was verified** (do it this way, not by the script's exit status):

1. The fixture's `.scad` carries a `/* [Lid] */` parameter group with `Lid_Thickness = 0`, which
   changes no geometry. So the `.3mf` is unchanged and the *only* thing that can differ is the
   customizer source — which makes the check unambiguous.
2. Open the model page → `Customize` → the **Customizable** modal → `Customize` again. That
   second click is easy to miss; the first only opens a modal listing the source file. MakerLab
   then shows the parameter panel, which now reads `Dimensions` (Width, Depth, Height, Corner)
   **plus `Lid`**. The Lid group exists only in the newly uploaded source.
3. Best of all, the MakerLab URL carries a signed `scadUrl` query param pointing at the raw file
   on the CDN. `curl` it (the signature is good for ~300s) and diff against
   `dist/<model>/<stem>.scad`. It came back **byte-identical, same md5**.

Point 3 is a genuinely better verification route than the `.3mf` procedure, and the difference
matters: raw `.scad` files are stored as uploaded, so a **byte comparison is valid here**. That
is the opposite of the `.3mf` rule elsewhere in this file, where MakerWorld re-processes every
upload and adds slice previews, so bytes never match and only geometry can be compared.

Note that the model detail API (`/api/v1/design-service/design/{id}`) does **not** expose a raw
`.scad` download url — `designExtension.model_files[0]` gives the `modelName` and a thumbnail
only. The signed url off the MakerLab launch is the way in.

Neither `designId` nor the model id changed (`designId=3055595` in the customizer URL), and
`Customize` still works, so the delete+reupload does not orphan the customizer. What remains
genuinely untested is the thing the fixture cannot answer: what happens to the **241 existing
Customize uses** on beam when its raw `.scad` is replaced. The fixture has no meaningful
customization history, so that risk is unchanged by this test.

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

## Two hard limits on what can go in a packed `.3mf`

### 1. At most 36 plates

Building all 42 beam variants into one `.3mf` failed: **Bambu Studio
supports a maximum of 36 plates per `.3mf`** (`stls_to_3mf.py` raises
`ValueError` on pack, after all 42 STLs had already rendered fine
individually — it's purely a packing-step limit).

### 2. Nothing may touch the bed exclusion zone

Found the hard way on the facade republish (2026-08-14), which MakerWorld
rejected outright with:

> `[Plate 34]: Object conflicts were detected. Please verify the slicing of
> all plates in Bambu Studio before uploading.`

The P1S profile we embed in `Metadata/project_settings.config` declares a
dead corner the toolhead can't reach:

```
printable_area   = (0,0) (256,0) (256,256) (0,256)
bed_exclude_area = (0,0) (18,0) (18,28) (0,28)     # 18 x 28mm, front-left
```

`stls_to_3mf.py` centres each part in its plate cell, so a centred part
overlaps that corner as soon as it is **wider than 220 and deeper than
200** — and Bambu Studio then refuses the plate ("too close to exclusion
area"). The packer now offsets such parts clear of the zone (+x preferred,
since 18 < 28; +y as fallback) and raises at pack time if neither fits,
rather than emitting a plate that gets rejected after a full build has run.

Two traps worth knowing:

- **MakerWorld reports only the first offending plate**, so its error
  understates the problem. The facade upload named plate 34 while three
  plates (8x8, 8x9, 9x9) were actually bad. Open the `.3mf` in Bambu
  Studio to see them all.
- **Its plate numbering need not match the file's.** MakerWorld reorders
  plates — the previously published facade package starts at 3x7 — so
  "plate N" is not reliably the Nth `<plate>` in
  `Metadata/model_settings.config`.

Some sizes are simply impossible rather than misplaced: a 252 x 252mm part
needs 270mm in x or 280mm in y to clear the corner on a 256mm bed, so
`facade_lite_9x9` cannot be published at all. That is why the facade ships
35 plates, not 36 — a constraint that predates this repo and was rediscovered
here only because the config's header comment claimed otherwise.

## Splitting a model that exceeds the plate limit

Resolved by splitting along the grid-version axis,
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
- **A stale `DevToolsActivePort` is the confusing failure** (hit on 2026-08-12). Chrome does not
  rewrite that file when it restarts, and it reuses port 9222 — so the port in the file is still
  correct and the TCP connection succeeds, while the `/devtools/browser/{uuid}` path belongs to a
  long-dead session. The symptom is `connect_over_cdp` hanging until timeout rather than any
  useful error, and since this mode serves no `/json/version`, there's no way to discover the
  current uuid programmatically. Fix: un-check and re-check the box at
  `chrome://inspect/#remote-debugging`, which rewrites the file. `connect_chrome()` now says so
  in its error, and reports how old the file is.
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

*Automated as of 2026-08-12 — see "Update 2026-08-12" above for the `new-model` subcommand and
the DOM mechanics. What follows is the by-hand flow it drives.*

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

**…and that wait used to be capped too tightly.** On the facade republish
(2026-08-14) the enqueue lag was about 65s against a then-`ENQUEUE_TIMEOUT_S
= 60`, so the script raised *"'openGrid Facade' never showed up at
…/verifying within 60s of clicking Confirm"* on a publish that had in fact
submitted cleanly and went on to verify and go live — a hard cutoff sitting
right on top of the real figure. `ENQUEUE_TIMEOUT_S` is now **180s**, and
the error raised when the deadline does pass says the outcome is *unknown*
rather than failed.

That distinction still matters, because the timeout can never be conclusive:
**a raised `UpdateError` from that check does NOT mean the publish failed** —
it means the script stopped watching. Confirm the real outcome before
reacting, and never re-run the update on the strength of that error alone;
a blind retry risks a duplicate publish and a duplicate user notification.
The error text now points at the same three checks written up below, and the
debug screenshot saved on failure is the `/verifying` page as it looked at
the deadline — on the facade run that screenshot already showed the item
queued, so read it first.

### Establishing what actually happened after an ambiguous update

Reading the UI is not enough — the profile edit page shows the *uploaded*
file, which looks identical whether or not it ever published, and plate
count and rounded file size can match between old and new. Two checks
settle it:

1. `https://makerworld.com/en/@{username}/verify-failed` — the rejection
   queue, **with a stated reason**. Note the URL: `/failed` 404s.
2. Download what the site is actually serving and inspect the geometry.
   From inside the logged-in page (so cookies apply):

   ```js
   await fetch('/api/v1/design-service/instance/{profileId}/f3mf',
               {credentials: 'include'})   // -> {name, url}
   ```

   That returns a signed CDN URL, valid ~300s, which `curl` can fetch.
   (The sibling endpoints `/instance/{id}` and `/model/{id}/profiles` 404.)

   **Compare geometry, not bytes.** MakerWorld re-processes an upload and
   adds slice previews and pick images, so the served `.3mf` is never
   byte-identical to what was sent — the facade's was 5.08MB served against
   3.65MB uploaded. Plate count plus connected-body count per object is the
   check that actually discriminates. This is also the most reliable way to
   recover a model's *published* geometry as a baseline, and it beats a
   local `dist/` copy, which `clean_before_build` will happily wipe.

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
