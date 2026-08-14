#!/usr/bin/env python3
"""
MakerWorld update automation.

Three subcommands, all documented in docs/makerworld_publish_notes.md:

  update       Replace the .3mf on an EXISTING print profile ("Replace
               File"), optionally also delete+reupload the raw .scad
               customizer source (--scad). Requires
               project.makerworld_profile_id in the build config.

  new-profile  First-time publish of a NEW print profile onto an EXISTING
               model (reached via the model page's "..." menu -> "Add
               Print Profile"). Requires project.makerworld_url in the
               build config to find the model; makerworld_profile_id is
               not needed since it doesn't exist yet -- this command
               prints the resulting id for you to add afterward.

  new-model    First-time publish of a whole NEW model -- it creates the
               listing itself, so neither id is needed (and having
               makerworld_url set is an error without --force, since that
               means the listing already exists). Fills MakerWorld's
               3-step publish wizard from the BUILT description file, so
               the name/category/tags/license/description published are
               exactly what scad_builder.py generated. Prints both new ids
               for you to add to the config afterward.

Requires the model to already be built (run scad_builder.py first). The
exception is a prebuilt model (one declaring `prebuilt:` instead of
`source:`): its .3mf is committed under model_pages/ and is uploaded
straight from there, with no build step and no --scad support.

Attaches over CDP to your regular, already-running main Chrome browser --
launching a separate/isolated automation profile trips Cloudflare's bot
check, and Chrome refuses classic --remote-debugging-port on the default
profile outright. The only thing that actually works: Chrome 144+'s
native chrome://inspect/#remote-debugging toggle on your real, already
open browser.

Before running:
1. In your regular running Chrome, go to chrome://inspect/#remote-debugging
   and check "Allow remote debugging for this browser instance". Make sure
   you're logged into MakerWorld in that window.
2. Chrome does NOT expose the classic CDP HTTP JSON API in this mode
   (/json/version 404s) -- this script instead reads the WebSocket
   endpoint straight out of Chrome's own `DevToolsActivePort` file in the
   profile dir, same as chrome-devtools-mcp does internally.
3. Chrome will pop up an "Allow remote debugging?" dialog the moment this
   script connects -- click Approve. This happens every run, by design
   (Chrome does not persist the approval); there's nothing to script
   around it.

Usage:
    python3 scripts/makerworld_update.py update opengrid_beam/full --notify-message "..."
    python3 scripts/makerworld_update.py update opengrid_beam/full --no-notify
    python3 scripts/makerworld_update.py update opengrid_beam/full --no-notify --scad
    python3 scripts/makerworld_update.py new-profile opengrid_beam/lite \\
        --photo model_pages/opengrid_beam/images/opengrid_beam_wide_view.jpg \\
        --name "Lite Print Settings" --description "..."
    python3 scripts/makerworld_update.py new-model my_model --dry-run
    python3 scripts/makerworld_update.py new-model my_model --private \\
        --cover model_pages/my_model/images/cover.jpg \\
        --photo model_pages/my_model/images/print_photo.jpg
"""

import argparse
import logging
import re
import sys
import time
from pathlib import Path

from description_fields import markdown_to_html, parse_description_fields
from model_config import is_prebuilt, load_merged_config, prebuilt_package_path, project_slug

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DEFAULT_CHROME_USER_DATA_DIR = str(Path.home() / 'Library' / 'Application Support' / 'Google' / 'Chrome')
DEFAULT_USERNAME = 'jonnydev13'
VERIFY_POLL_INTERVAL_S = 10
VERIFY_TIMEOUT_S = 300
ENQUEUE_POLL_INTERVAL_S = 3
# Generous on purpose. Measured enqueue lag on the 2026-08-14 facade republish was
# ~65s against a then-60s cap, so the old value sat right on top of the real figure --
# the worst possible place for a hard cutoff, since it turns a normal publish into a
# reported failure. Giving up here is ambiguous rather than conclusive (see
# poll_verification), and the cost of a wrong "failure" is a retry that duplicates a
# publish, so buy the margin.
ENQUEUE_TIMEOUT_S = 180
UPLOAD_TIMEOUT_MS = 180_000

# MakerWorld has no license picker. It derives the Creative Commons license
# from two radio questions and echoes the result back as a human-readable
# name, so the config's license string has to be mapped onto those answers --
# and the echo re-read afterwards to prove the clicks landed on the intended
# combination. Every row below was confirmed by answering the live form and
# reading the resulting summary.
ADAPTATIONS_QUESTION = 'Allow adaptations of your work to be shared?'
COMMERCIAL_QUESTION = 'Allow commercial uses of your work?'
# Only shown when adaptations is "No"; answering it decides between a CC
# NoDerivatives license and MakerWorld's own Standard Digital File License.
SHARING_QUESTION = 'Allow sharing or redistributing of your work or its derivatives?'
LICENSE_SUMMARY_PREFIX = 'This user content is licensed under'
SHARE_ALIKE_ANSWER = 'Yes, as long as others share in the same way'
LICENSE_SPECS = {
    # token: (adaptations answer, commercial answer, the summary MakerWorld shows)
    'BY': ('Yes', 'Yes', 'Creative Commons Attribution'),
    'BY-SA': (SHARE_ALIKE_ANSWER, 'Yes', 'Creative Commons Attribution-Share Alike'),
    'BY-NC': ('Yes', 'No', 'Creative Commons Attribution-Noncommercial'),
    'BY-NC-SA': (SHARE_ALIKE_ANSWER, 'No', 'Creative Commons Attribution-Noncommercial-Share Alike'),
    'BY-ND': ('No', 'Yes', 'Creative Commons Attribution-NoDerivatives'),
    'BY-NC-ND': ('No', 'No', 'Creative Commons Attribution-Noncommercial-NoDerivatives'),
}


class UpdateError(Exception):
    pass


def load_project_config(model_dir: Path, root_dir: Path, require_profile_id: bool = True) -> dict:
    config_path = model_dir / 'build_config.yaml'
    if not config_path.exists():
        raise UpdateError(f"No build_config.yaml found at {config_path}")
    config, _ = load_merged_config(config_path)

    project = config.get('project', {})
    if require_profile_id and 'makerworld_profile_id' not in project:
        raise UpdateError(
            f"{config_path} is missing project.makerworld_profile_id. "
            "Look up the profile ID from the model's MakerWorld page URL "
            "(the #profileId-XXXXXXX fragment) and add it to the config."
        )

    # A prebuilt model ships a committed .3mf and has no SCAD source at all --
    # no input_file to name the raw customizer upload after, and nothing in
    # dist/ to look for (see resolve_upload_files).
    if is_prebuilt(config):
        prebuilt_package = prebuilt_package_path(config, config_path)
        source_stem = None
    else:
        source = config.get('source', {})
        if 'input_file' not in source:
            raise UpdateError(f"{config_path} is missing source.input_file")
        prebuilt_package = None
        source_stem = Path(source['input_file']).stem

    # Used to locate dist/<slug>/ -- derived from the config's own location
    # under model_pages/, not project.name, since project.name is shared
    # identically across every profile of a multi-profile model and would
    # collide (see scripts/model_config.py).
    project_name = project_slug(config_path, root_dir)

    return {
        'config': config,
        'config_path': config_path,
        'project_name': project_name,
        'source_stem': source_stem,
        'prebuilt_package': prebuilt_package,
        'profile_id': project.get('makerworld_profile_id'),
        'model_url': project.get('makerworld_url'),
        # The verifying-queue page shows the real MakerWorld model name, which
        # can differ from our own project_name (e.g. multiple print profiles
        # -- small/medium/large -- sharing one underlying MakerWorld model
        # named just "openGrid Basket"). Falls back to project.name for
        # configs where they happen to match (e.g. opengrid_beam's Full
        # profile).
        'verify_name': project.get('makerworld_model_name', project.get('name', project_name.replace('_', ' '))),
    }


def model_id_from_url(url: str) -> str:
    # e.g. https://makerworld.com/en/models/2402751-opengrid-beam -> "2402751"
    slug = url.rstrip('/').split('/')[-1]
    return slug.split('-')[0]


def resolve_upload_files(root_dir: Path, cfg: dict, need_scad: bool) -> dict:
    """Locate the files to upload. For a normal model these are build outputs
    under dist/; for a prebuilt model the .3mf is the committed package itself,
    used straight from model_pages/ -- deliberately NOT copied into dist/, which
    is gitignored and gets wiped by the next clean build."""
    if cfg['prebuilt_package']:
        if need_scad:
            raise UpdateError(
                "--scad is not available for a prebuilt model: its package is committed "
                "as a .3mf and there is no SCAD customizer source to upload."
            )
        logger.info(f"Prebuilt model -- uploading committed package {cfg['prebuilt_package']}")
        return {'mf3_path': cfg['prebuilt_package']}

    project_name, source_stem = cfg['project_name'], cfg['source_stem']
    dist_dir = root_dir / 'dist' / project_name
    mf3_path = dist_dir / f'{project_name}.3mf'
    if not mf3_path.exists():
        raise UpdateError(
            f"{mf3_path} not found. Build it first: "
            f"python3 scripts/scad_builder.py model_pages/<model>/build_config.yaml"
        )

    result = {'mf3_path': mf3_path}

    if need_scad:
        compiled_path = dist_dir / f'{source_stem}_cpl.scad'
        stripped_path = dist_dir / f'{source_stem}.scad'
        if not compiled_path.exists():
            raise UpdateError(
                f"{compiled_path} not found. Build it first: "
                f"python3 scripts/scad_builder.py model_pages/<model>/build_config.yaml"
            )
        # Strip the _cpl suffix for the MakerWorld-facing filename (see
        # docs/makerworld_publish_notes.md - the internal _cpl naming is
        # just for disambiguating our own build artifacts).
        stripped_path.write_text(compiled_path.read_text())
        logger.info(f"Prepared {stripped_path.name} for upload (stripped _cpl suffix)")
        result['scad_path'] = stripped_path

    return result


def resolve_description_file(config: dict, config_path: Path, root_dir: Path, site: str = 'makerworld') -> Path:
    """Locate the built description for a site, the same way copy_description.py
    does: <output_directory>/<project_slug>/<site's output_file>."""
    sites = config.get('templates', {}).get('sites', {})
    if site not in sites:
        available = ', '.join(sites) or 'none'
        raise UpdateError(
            f"{config_path} has no templates.sites.{site} block (available: {available}). "
            f"new-model publishes to MakerWorld and needs the {site} description to fill the form."
        )
    output_file = sites[site].get('output_file')
    if not output_file:
        raise UpdateError(f"{config_path}: templates.sites.{site} is missing output_file")

    output_dir = config.get('build', {}).get('output_directory', 'dist/')
    path = root_dir / output_dir / project_slug(config_path, root_dir) / output_file
    if not path.exists():
        raise UpdateError(
            f"{path} not found. Generate it first: "
            f"python3 scripts/scad_builder.py {config_path.relative_to(root_dir)} -d"
        )
    return path


def load_publish_fields(config: dict, config_path: Path, root_dir: Path) -> dict:
    """Read the built MakerWorld description into the fields the publish form needs."""
    description_path = resolve_description_file(config, config_path, root_dir)
    fields = parse_description_fields(description_path.read_text())

    missing = [f for f in ('MODEL NAME', 'CATEGORY', 'DESCRIPTION') if not fields.get(f)]
    if missing:
        raise UpdateError(
            f"{description_path} is missing required field(s): {', '.join(missing)}. "
            "Rebuild the description (scad_builder.py -d) and check the config's "
            "project/templates.sites.makerworld blocks."
        )

    # model_type decides which publish wizard to open: a remix additionally
    # requires at least one Model Origin URL, which the template only emits for
    # model_type: remix.
    site_config = config.get('templates', {}).get('sites', {}).get('makerworld', {})
    model_type = site_config.get('model_type', 'original')
    source_urls = [
        line.lstrip('- ').strip()
        for line in fields.get('SOURCE MODEL URLS', '').splitlines()
        if line.strip()
    ]
    if model_type == 'remix' and not source_urls:
        raise UpdateError(
            f"{config_path} declares model_type: remix but the built description has no "
            "SOURCE MODEL URLS. MakerWorld requires a Model Origin for a remix -- add "
            "templates.sites.makerworld.source_urls and rebuild the description."
        )

    return {
        'model_type': model_type,
        'name': fields['MODEL NAME'].strip(),
        'license': fields.get('LICENSE', '').strip(),
        'category': fields['CATEGORY'].strip(),
        'tags': [t.strip() for t in fields.get('TAGS', '').split(',') if t.strip()],
        'source_urls': source_urls,
        'description': fields['DESCRIPTION'].strip(),
        'profile_name': fields.get('PRINT PROFILE NAME', '').strip() or None,
        'profile_description': fields.get('PRINT PROFILE DESCRIPTION', '').strip() or None,
        'description_path': description_path,
    }


def resolve_ws_endpoint(user_data_dir: str) -> str:
    """Read Chrome's own DevToolsActivePort file to get the CDP WebSocket
    endpoint -- the classic HTTP JSON API (/json/version) is disabled under
    chrome://inspect/#remote-debugging, so this is the only way in."""
    port_path = Path(user_data_dir) / 'DevToolsActivePort'
    try:
        port_str, ws_path = port_path.read_text().splitlines()[:2]
    except (FileNotFoundError, ValueError):
        raise UpdateError(
            f"Couldn't read {port_path}. In your running Chrome, go to "
            "chrome://inspect/#remote-debugging and check 'Allow remote "
            "debugging for this browser instance', then re-run this script."
        )
    return f'ws://127.0.0.1:{port_str.strip()}{ws_path.strip()}'


def handle_model_data_changed_dialog(page, notify_message: str | None, timeout_ms: int = 5000):
    """Handle the 'Model Data Changed?' confirmation dialog if it appears.
    Returns True if the dialog was handled, False if it never appeared."""
    dialog = page.get_by_role('dialog', name='Model Data Changed?')
    try:
        dialog.wait_for(state='visible', timeout=timeout_ms)
    except Exception:
        return False

    if notify_message:
        dialog.get_by_role('radio', name='Yes. Users must be notified about the change.').check()
        dialog.get_by_role('textbox').fill(notify_message)
        logger.info("Selected 'notify users' with the provided message")
    else:
        dialog.get_by_role('radio', name='Yes, but no need to notify other users.').check()
        logger.info("Selected 'no need to notify other users'")

    dialog.get_by_role('button', name='Confirm').click()
    return True


def check_not_challenged(page):
    """Cloudflare occasionally throws an interactive 'Performing security
    verification' checkbox challenge at navigations, even on an approved
    CDP session -- confirmed happening mid-run against the live account.
    Detect it and fail loudly rather than either misreporting a timeout or
    (never) trying to click through it ourselves -- that's a human's call,
    done once in the actual browser window."""
    if 'Just a moment' in page.title():
        raise UpdateError(
            "Cloudflare is showing an interactive challenge in the browser window -- "
            "solve it by hand (click the checkbox), then re-run this script."
        )


def poll_verification(page, username: str, model_name: str):
    """Poll the Verifying/Failed queues until the model clears one way or the other."""
    verifying_url = f'https://makerworld.com/en/@{username}/verifying'
    failed_url = f'https://makerworld.com/en/@{username}/verify-failed'

    # There's a lag between clicking Confirm and the item actually landing in the
    # verifying queue -- checking too early reads "not there" as "already passed"
    # (a false positive, confirmed happening in practice: the script reported
    # success after ~8s while the item was still genuinely verifying minutes later).
    # Wait for it to actually show up before polling for it to clear.
    logger.info(f"Waiting for '{model_name}' to enter the verification queue...")
    enqueue_deadline = time.monotonic() + ENQUEUE_TIMEOUT_S
    while True:
        page.goto(verifying_url)
        page.wait_for_load_state('load')
        check_not_challenged(page)
        if model_name in page.content():
            logger.info(f"'{model_name}' is in the verification queue")
            break
        if time.monotonic() >= enqueue_deadline:
            raise UpdateError(
                f"UNKNOWN OUTCOME: '{model_name}' had not appeared at {verifying_url} "
                f"{ENQUEUE_TIMEOUT_S}s after clicking Confirm.\n"
                "This does NOT mean the publish failed -- it means the script stopped"
                " watching. Confirm may have submitted cleanly and the queue lag simply ran"
                " long, in which case the model verifies and goes live on its own.\n"
                "DO NOT re-run this script to 'retry' before establishing what happened: a"
                " second submit risks a duplicate publish and a duplicate notification to"
                " everyone using this model's print profiles, and neither can be taken back.\n"
                "To disambiguate:\n"
                "  0. Read the debug screenshot saved alongside this error first -- it is the"
                " Verifying page as it looked at the deadline, so the item may already be"
                " visible in it.\n"
                f"  1. {verifying_url} -- if it is queued there, it submitted fine; wait.\n"
                f"  2. {failed_url} -- a genuine rejection lands here"
                " with a stated reason (note the URL: /failed 404s).\n"
                "  3. Compare the geometry the site actually serves against what was sent:"
                " fetch /api/v1/design-service/instance/{profileId}/f3mf from inside the"
                " logged-in page for a signed CDN url, then compare plate count and connected"
                " bodies per object -- NOT bytes, MakerWorld re-processes every upload.\n"
                "Full procedure: docs/makerworld_publish_notes.md."
            )
        time.sleep(ENQUEUE_POLL_INTERVAL_S)

    logger.info(f"Polling verification status for '{model_name}'...")
    deadline = time.monotonic() + VERIFY_TIMEOUT_S
    while time.monotonic() < deadline:
        page.goto(verifying_url)
        page.wait_for_load_state('load')
        check_not_challenged(page)
        if model_name not in page.content():
            break
        logger.info(f"Still verifying, checking again in {VERIFY_POLL_INTERVAL_S}s...")
        time.sleep(VERIFY_POLL_INTERVAL_S)
    else:
        raise UpdateError(
            f"Timed out after {VERIFY_TIMEOUT_S}s waiting for verification to clear. "
            f"Check {verifying_url} manually."
        )

    page.goto(failed_url)
    page.wait_for_load_state('load')
    check_not_challenged(page)
    if model_name in page.content():
        raise UpdateError(
            f"Verification FAILED for '{model_name}'. Check {failed_url} for the reason."
        )

    logger.info(f"Verification passed for '{model_name}'")


def update_print_profile(page, profile_id, mf3_path: Path, notify_message: str | None):
    logger.info(f"Updating print profile {profile_id} with {mf3_path.name}")
    page.goto(f'https://makerworld.com/en/my/profiles/{profile_id}/edit')
    page.wait_for_load_state('load')
    check_not_challenged(page)

    page.locator('input[type="file"][accept=".3mf"]').set_input_files(str(mf3_path))
    # Wait for the upload/processing to finish and Publish to become enabled.
    publish_btn = page.get_by_role('button', name='Publish', exact=True)
    publish_btn.wait_for(state='visible')
    page.wait_for_timeout(2000)  # let the plate re-slice/preview finish generating
    publish_btn.click()

    handle_model_data_changed_dialog(page, notify_message)


def create_print_profile(
    page, model_id: str, mf3_path: Path, photo_paths: list[Path],
    profile_name: str | None, description: str | None, private: bool,
):
    """First-time publish of a NEW print profile onto an EXISTING model --
    a different flow from update_print_profile's 'Replace File' (that one
    requires an existing profile_id; this one only needs the model_id).
    Reached via the model page's '...' menu -> 'Add Print Profile', which
    resolves to this same publish URL."""
    logger.info(f"Creating new print profile for model {model_id} with {mf3_path.name}")
    page.goto(f'https://makerworld.com/en/my/profiles/publish?designId={model_id}')
    page.wait_for_load_state('load')
    check_not_challenged(page)

    page.locator('input[type="file"][accept=".3mf"]').set_input_files(str(mf3_path))

    # The rest of the form (name, photos, visibility, ...) only renders after
    # the 3mf finishes uploading/processing -- wait for it rather than racing.
    name_box = page.get_by_role(
        'textbox', name='Describe the main difference compared to the existing print profiles'
    )
    name_box.wait_for(state='visible')

    if not photo_paths:
        raise UpdateError(
            "At least one real print photo is required for Print Profile Pictures "
            "(MakerWorld rejects synthetic/rendered photos -- see docs)."
        )
    # This is the SECOND file input on the page (index 1) -- the first is the
    # .3mf dropzone above, confirmed by inspecting accept attrs + nearby DOM
    # text via evaluate_script. Not reachable by uid/role because it's a
    # display:none input MakerWorld's own "Add Photo" button click-forwards to.
    page.locator('input[type="file"][accept="image/jpeg, image/png, image/webp, image/gif"]') \
        .set_input_files([str(p) for p in photo_paths])

    page.get_by_role('radio', name='Private' if private else 'Public').check()

    if description:
        # Rich text editors on MakerWorld don't respond to fill() -- click to
        # focus, then type real keystrokes (same as other description fields).
        desc_area = page.get_by_role('textbox', name='Editor editing area: main. Press ⌥0 for help.')
        desc_area.click()
        desc_area.type(description)

    page.get_by_role(
        'checkbox',
        name="I've read Print Profile Guidelines and be sure my print profile meets the requirement."
    ).check()

    if profile_name:
        # MUST be last: MakerWorld auto-populates this field with a default
        # (e.g. "0.2mm layer, 2 walls, 15% infill") asynchronously once the
        # 3mf finishes server-side processing, which overwrites anything
        # typed earlier -- confirmed in practice, a --name value filled
        # right after the field appeared silently got clobbered by the time
        # Publish was clicked. Filling last, right before Publish, avoids
        # the race instead of guessing at a wait condition for "done".
        name_box.fill(profile_name)

    publish_btn = page.get_by_role('button', name='Publish', exact=True)
    publish_btn.wait_for(state='visible')
    page.wait_for_timeout(2000)  # let photo/plate previews finish generating
    publish_btn.click()


def find_new_profile_id(page, username: str, model_id: str) -> str | None:
    """After verification clears, the new profile doesn't announce its own id
    anywhere obvious -- find it on the Published Print Profiles list (newest
    first) by matching the model it belongs to (NOT by profile name -- names
    like "0.2mm layer, 2 walls, 15% infill" collide across many models) and
    pull the id out of the #profileId-XXXXX fragment on its link."""
    page.goto(f'https://makerworld.com/en/@{username}/profile')
    page.wait_for_load_state('load')
    check_not_challenged(page)
    match = page.locator(f'a[href*="/models/{model_id}-"]').first
    try:
        href = match.get_attribute('href', timeout=10000)
    except Exception:
        return None
    if not href or '#profileId-' not in href:
        return None
    return href.split('#profileId-')[-1]


# --- first-time model publish (the `new-model` subcommand) -------------------
#
# MakerWorld's own markup does most of the work here: every section of the
# Model Information form carries a semantic class (.modelName, .modelCategory,
# .modelTags, .modelLicense, .modelDescription, .modelOriginals,
# .submitPrivate) alongside the hashed emotion classes, and the photo sections
# carry validation-anchor classes (.js-scroll-cover, .js-scroll-designPictures).
# Those are what everything below scopes to -- confirmed by dumping the live
# DOM of an existing model's edit page, which renders the identical form.


def normalize_license(license_text: str) -> str:
    """'CC BY-NC-SA 4.0' -> 'BY-NC-SA', the token MakerWorld's own license
    summary field displays."""
    token = license_text.upper().replace('CREATIVE COMMONS', '').strip()
    token = re.sub(r'^CC[\s-]*', '', token)
    token = re.sub(r'\s*\d+(\.\d+)?\s*$', '', token)
    return token.strip()


def check_radio_under_question(page, question: str, answer: str):
    """Check a radio identified by the question it answers. The License block's
    options are literally 'Yes'/'No' in two different groups, so a page-wide
    role+name lookup would be ambiguous -- anchor on the question text and take
    the first matching label after it."""
    label = page.locator(
        f'xpath=//*[normalize-space(text())="{question}"]'
        f'/following::label[normalize-space(.)="{answer}"][1]'
    )
    label.locator('input[type="radio"]').check()


def read_license_summary(page) -> str:
    """The license MakerWorld says it derived, e.g. 'Creative Commons
    Attribution-Noncommercial-Share Alike'. It's a plain text node on the
    publish wizard (an existing model's edit page renders the same thing as a
    read-only input holding the short 'BY-NC-SA' form instead)."""
    block = page.locator('.modelLicense').inner_text()
    if LICENSE_SUMMARY_PREFIX in block:
        tail = block.split(LICENSE_SUMMARY_PREFIX, 1)[1].strip()
        return tail.splitlines()[0].strip() if tail else ''
    field = page.locator('.modelLicense input[type="text"]')
    return field.input_value() if field.count() else ''


def set_license(page, license_text: str):
    token = normalize_license(license_text)
    if token not in LICENSE_SPECS:
        raise UpdateError(
            f"Don't know how to set license '{license_text}' (read as '{token}'). "
            f"MakerWorld derives the license from radio questions; supported tokens: "
            f"{', '.join(LICENSE_SPECS)}."
        )
    adaptations, commercial, expected = LICENSE_SPECS[token]
    check_radio_under_question(page, ADAPTATIONS_QUESTION, adaptations)
    page.wait_for_timeout(500)
    check_radio_under_question(page, COMMERCIAL_QUESTION, commercial)
    page.wait_for_timeout(500)
    if adaptations == 'No':
        # Answering "No" reveals a third question, and leaving it unanswered is
        # what produces MakerWorld's Standard Digital File License instead of a
        # Creative Commons one.
        check_radio_under_question(page, SHARING_QUESTION, 'Yes')
        page.wait_for_timeout(500)

    # MakerWorld computes the license itself; read it back rather than assume
    # the clicks produced the one we meant.
    summary = read_license_summary(page)
    if summary.lower() != expected.lower():
        raise UpdateError(
            f"License mismatch: config says '{license_text}' ({token}, expected MakerWorld "
            f"to show '{expected}') but its license summary reads '{summary}'."
        )
    logger.info(f"License set to {token} ({summary})")


def choose_autocomplete_option(page, container_selector: str, value: str, label: str):
    """Fill one of MakerWorld's MUI autocompletes and pick from its dropdown.
    Typing alone doesn't register a value -- the option has to be clicked."""
    box = page.locator(f'{container_selector} input[role="combobox"]')
    box.click()
    box.fill('')
    box.type(value)

    # Wait for the dropdown before deciding which option to take -- checking
    # too early finds nothing and would silently fall through to "first".
    try:
        page.get_by_role('option').first.wait_for(state='visible', timeout=15000)
    except Exception:
        raise UpdateError(
            f"No {label} suggestion appeared for '{value}'. Check that it matches one of "
            "MakerWorld's own options."
        )
    exact = page.get_by_role('option').filter(has_text=re.compile(f'^{re.escape(value)}$', re.I))
    option = exact.first if exact.count() else page.get_by_role('option').first
    chosen = option.inner_text().strip()
    option.click()
    if chosen.lower() != value.lower():
        logger.warning(f"{label}: asked for '{value}', MakerWorld matched '{chosen}'")
    else:
        logger.info(f"{label} set to '{chosen}'")


def add_tags(page, tags: list[str]):
    """The Tags field is an autocomplete that also accepts free text, committed
    with Enter. Read the chips back afterwards -- a suggestion can be highlighted
    when Enter lands, which commits MakerWorld's word instead of ours."""
    if not tags:
        return
    box = page.locator('.modelTags input[role="combobox"]')
    for tag in tags:
        box.click()
        box.type(tag)
        page.wait_for_timeout(500)
        box.press('Enter')
        page.wait_for_timeout(300)
    added = [t.strip() for t in page.locator('.modelTags .tagItem-content').all_inner_texts()]
    logger.info(f"Tags set: {', '.join(added) or '(none)'}")
    unexpected = [t for t in added if t.lower() not in {tag.lower() for tag in tags}]
    if len(added) != len(tags) or unexpected:
        logger.warning(
            f"Asked for {len(tags)} tags, MakerWorld kept {len(added)}"
            + (f" (not asked for: {', '.join(unexpected)})" if unexpected else '')
            + " -- a highlighted suggestion can be committed instead of the typed text."
        )


def add_model_origins(page, urls: list[str]):
    """Model Origin (remix only): each source model is added by pasting its URL
    and clicking the suggestion MakerWorld resolves it to."""
    for url in urls:
        page.locator('.modelOriginals').get_by_role('button', name='Add', exact=True).click()
        box = page.locator('.modelOriginals input[role="combobox"]')
        box.click()
        box.fill(url)
        option = page.get_by_role('option').first
        try:
            title = option.inner_text(timeout=15000).strip().splitlines()[0]
        except Exception:
            raise UpdateError(
                f"MakerWorld didn't resolve the source model URL {url} to anything. "
                "Check the URL is a live MakerWorld model."
            )
        option.click()
        page.wait_for_timeout(500)
        logger.info(f"Model Origin added: {title}")


# CKEditor ignores fill(), and typing markdown literally would publish '##' as
# text. Dispatching a paste event carrying text/html is what the editor itself
# handles when a human pastes from copy_description.py's clipboard output -- so
# the published description matches the by-hand flow, headings and all.
PASTE_HTML_JS = """
(element, html) => {
  const data = new DataTransfer();
  data.setData('text/html', html);
  data.setData('text/plain', element.textContent || '');
  element.focus();
  element.dispatchEvent(new ClipboardEvent('paste', {
    clipboardData: data, bubbles: true, cancelable: true,
  }));
}
"""


def set_rich_description(page, markdown_text: str, container: str = '.modelDescription'):
    editor = page.locator(f'{container} [contenteditable="true"]')
    editor.wait_for(state='visible')
    editor.click()
    page.wait_for_timeout(500)
    # Paste inserts at the cursor, so clear first -- otherwise a retry, or a
    # description MakerWorld pre-filled, would end up interleaved with ours.
    editor.press('ControlOrMeta+a')
    editor.evaluate(PASTE_HTML_JS.strip(), markdown_to_html(markdown_text))
    page.wait_for_timeout(1000)

    # Prove the editor actually took it: a silently-empty description would
    # otherwise only surface after the model was published.
    probe = next(
        (line.strip() for line in markdown_text.splitlines() if len(line.strip()) > 25),
        markdown_text.strip(),
    )[:40]
    if probe and probe not in editor.inner_text():
        raise UpdateError(
            "The description didn't land in MakerWorld's editor (pasted HTML was ignored). "
            "Publish by hand this once -- scripts/copy_description.py puts the same content "
            "on the clipboard -- and check whether the editor markup changed."
        )
    logger.info(f"Description set ({len(markdown_text)} chars of markdown)")


def submit_crop_dialog(page):
    """A Model Cover upload opens a crop dialog ("Web/App cover 4:3") whose only
    control is Submit -- the cover is not actually set until it's clicked, and
    the form keeps reporting "Please set the model cover" until then. Model
    Pictures and Print Profile Pictures don't do this; only covers."""
    dialog = page.get_by_role('dialog')
    try:
        dialog.wait_for(state='visible', timeout=20000)
    except Exception:
        raise UpdateError(
            "The cover crop dialog never appeared after uploading the cover image. "
            "Check the browser window -- the cover may not have uploaded."
        )
    dialog.get_by_role('button', name='Submit').click()
    dialog.wait_for(state='hidden', timeout=30000)
    page.wait_for_timeout(1000)
    logger.info("Cover set (crop dialog submitted)")


PHOTO_COUNT_RE = re.compile(r'\(\s*(\d+)\s*/\s*\d+\s*\)')


def read_photo_count(page, container_selector: str) -> int:
    """Photo sections title themselves with a live count -- "Model Pictures
    ( 1 / 16 )" -- which is the only visible confirmation an upload landed."""
    match = PHOTO_COUNT_RE.search(page.locator(container_selector).inner_text())
    return int(match.group(1)) if match else 0


def upload_photos(page, container_selector: str, paths: list[Path], label: str):
    """Upload into a photo section and wait for its count to actually rise.

    Waiting for merely a non-zero count is not enough: Print Profile Pictures
    opens at 1, having inherited a Model Picture, so a non-zero check passes
    instantly on a photo that isn't ours and moves on mid-upload."""
    before = read_photo_count(page, container_selector)
    page.locator(f'{container_selector} input[type="file"]').set_input_files(
        [str(p) for p in paths]
    )
    try:
        page.wait_for_function(
            """([selector, before]) => {
                 const el = document.querySelector(selector);
                 const m = el && el.innerText.match(/\\(\\s*(\\d+)\\s*\\/\\s*\\d+\\s*\\)/);
                 return !!m && Number(m[1]) > before;
               }""",
            arg=[container_selector, before],
            timeout=UPLOAD_TIMEOUT_MS,
        )
    except Exception:
        raise UpdateError(
            f"{label}: the count never rose above {before} -- the photo(s) didn't upload."
        )
    after = read_photo_count(page, container_selector)
    logger.info(f"{label}: {before} -> {after}")
    if after - before < len(paths):
        logger.warning(
            f"{label}: uploaded {len(paths)} photo(s) but the count only rose by "
            f"{after - before} -- MakerWorld may have rejected one."
        )


def raise_on_form_errors(page, step: str):
    """MakerWorld blocks a step transition with inline helper text rather than a
    dialog, so a failed 'Add Print Profile' otherwise looks like a hang."""
    errors = [t.strip() for t in page.locator('.Mui-error').all_inner_texts() if t.strip()]
    if errors:
        raise UpdateError(
            f"MakerWorld rejected the {step} step: {'; '.join(dict.fromkeys(errors))}"
        )


def wait_for_upload(page, filename: str):
    """Wait for an uploaded file to actually land.

    NOT by waiting for 'Next Step' to enable -- confirmed against the live
    wizard, that button is enabled from the moment the page renders, with no
    file attached at all, so keying on it would click straight past the upload.
    The dropzone swapping its prompt for the file's own name (and a 'Replace
    File' control) is the real signal."""
    try:
        page.get_by_text(filename, exact=False).first.wait_for(
            state='visible', timeout=UPLOAD_TIMEOUT_MS
        )
    except Exception:
        raise UpdateError(
            f"{filename} never appeared in its dropzone after "
            f"{UPLOAD_TIMEOUT_MS // 1000}s -- the upload didn't complete. "
            "Check the browser window."
        )
    logger.info(f"Uploaded {filename}")


def wait_for_raw_file_upload(page, path: Path):
    """Raw Model Files needs its own wait: unlike the .3mf dropzone, which
    renders the filename as page text, an uploaded raw file becomes a *renamable
    text input* holding the stem (with the extension shown separately), and
    React-set values aren't reflected in the DOM attribute -- so neither a text
    match nor a [value=] selector sees it."""
    stem = path.stem
    try:
        page.wait_for_function(
            """stem => [...document.querySelectorAll('input[type="text"], input:not([type])')]
                 .some(i => i.value === stem)""",
            arg=stem,
            timeout=UPLOAD_TIMEOUT_MS,
        )
    except Exception:
        raise UpdateError(
            f"{path.name} never appeared under Raw Model Files after "
            f"{UPLOAD_TIMEOUT_MS // 1000}s -- the upload didn't complete."
        )
    logger.info(f"Uploaded {path.name} (Raw Model Files)")


def create_model(
    page, fields: dict, mf3_path: Path, scad_path: Path | None,
    covers: list[Path], photos: list[Path], private: bool, draft: bool = False,
) -> str | None:
    """First-time publish of a whole NEW model -- the flow that creates the
    listing itself, as opposed to `update` (replace an existing profile's file)
    or `new-profile` (add a profile to an existing model). Three wizard steps:
    Upload -> Model Information -> Print Profile Information."""
    model_type = fields['model_type']
    logger.info(f"Creating a new {model_type} model: {fields['name']}")
    page.goto(f'https://makerworld.com/en/my/models/publish?type={model_type}')
    page.wait_for_load_state('load')
    check_not_challenged(page)

    # --- step 1: upload ---
    page.get_by_role('radio', name='Yes (earn extra points reward)').check()
    page.locator('input[type="file"][accept=".3mf"]').set_input_files(str(mf3_path))
    wait_for_upload(page, mf3_path.name)
    if scad_path:
        page.locator('input[type="file"][accept*=".scad"]').first.set_input_files(str(scad_path))
        wait_for_raw_file_upload(page, scad_path)
    # The two other questions on this step -- "Does this model include a Laser
    # & Cut model?" and "Is the model you uploaded a CyberBrick model?" -- both
    # default to No, which is what we want; they're left alone deliberately.
    page.get_by_role('button', name='Next Step').click()

    # --- step 2: model information ---
    # Leaving step 1 creates the draft (the URL becomes
    # /en/my/models/drafts/<id>/edit), so from here on there is already a
    # listing on the account even if nothing is ever published.
    page.locator('.modelName input').wait_for(state='visible')
    logger.info(f"Draft created: {page.url}")

    if fields['source_urls']:
        add_model_origins(page, fields['source_urls'])
    choose_autocomplete_option(page, '.modelCategory', fields['category'], 'Category')
    add_tags(page, fields['tags'])
    if fields['license']:
        set_license(page, fields['license'])
    page.locator('.submitPrivate').get_by_role(
        'radio', name='Private' if private else 'Public'
    ).check()
    set_rich_description(page, fields['description'])

    # Only the 4:3 Web/App cover is required; the 3:4 App cover is optional and
    # only filled when a second --cover is given, since each one costs a crop
    # dialog and a 4:3 photo squeezed into a 3:4 slot is worse than none.
    for slot, cover in enumerate(covers[:2]):
        page.locator('.js-scroll-cover input[type="file"]').nth(slot).set_input_files(str(cover))
        submit_crop_dialog(page)
    if photos:
        upload_photos(page, '.js-scroll-designPictures', photos, 'Model Pictures')

    # Model Name goes LAST, for the same reason the print profile's does:
    # MakerWorld autofills it from the uploaded file asynchronously and will
    # happily overwrite an earlier value (see new-profile's --name gotcha).
    page.locator('.modelName input').fill(fields['name'])

    # Step 2's forward button is "Add Print Profile", NOT "Next Step" -- that
    # one only exists on step 1. It refuses to advance while anything required
    # is missing, reporting it as inline .Mui-error text rather than a dialog.
    page.get_by_role('button', name='Add Print Profile').click()
    page.wait_for_timeout(3000)
    raise_on_form_errors(page, 'Model Information')
    page.wait_for_url('**/createPrintProfile', timeout=30000)

    # --- step 3: print profile information ---
    page.locator('input[name="profileTitle"]').wait_for(state='visible')
    page.locator('input[name="instanceSetting.isPrinterTested"]').check()
    if photos:
        upload_photos(page, '.printProfilePicture', photos, 'Print Profile Pictures')
    if fields['profile_description']:
        set_rich_description(
            page, fields['profile_description'], container='.printProfileDescription'
        )
    # Printer Compatibility arrives with every printer checked, and Print
    # Plates renders itself from the .3mf -- both are left alone on purpose.
    if fields['profile_name']:
        # Filled last: MakerWorld auto-populates this from the slicer settings
        # in the .3mf (it already reads e.g. "0.2mm layer, 2 walls, 15% infill"
        # by the time this step opens) and would overwrite an earlier value.
        page.locator('input[name="profileTitle"]').fill(fields['profile_name'])

    page.wait_for_timeout(2000)  # let plate/photo previews finish generating
    if draft:
        # Stops one click short of publishing: the listing exists as a draft
        # with every field filled, for a human to eyeball and publish by hand.
        # Nothing enters the verification queue.
        save_btn = page.get_by_role('button', name='Save to draft', exact=True)
        save_btn.wait_for(state='visible')
        save_btn.click()
        page.wait_for_timeout(5000)
        logger.info(f"Saved as a draft. Current page: {page.url}")
        return page.url

    publish_btn = page.get_by_role('button', name='Publish', exact=True)
    publish_btn.wait_for(state='visible')
    publish_btn.click()
    return None


def find_new_model_id(page, username: str, model_name: str) -> str | None:
    """After verification clears, find the published model by name on the
    account's own Published Models list and pull its id out of the URL."""
    page.goto(f'https://makerworld.com/en/@{username}/upload')
    page.wait_for_load_state('load')
    check_not_challenged(page)
    link = page.locator('a[href*="/models/"]').filter(has_text=model_name).first
    try:
        href = link.get_attribute('href', timeout=10000)
    except Exception:
        return None
    return model_id_from_url(href) if href else None


def update_raw_model_file(page, model_id, scad_path: Path, notify_message: str | None):
    logger.info(f"Updating raw model file for model {model_id} with {scad_path.name}")
    page.goto(f'https://makerworld.com/en/my/models/{model_id}/edit')
    page.wait_for_load_state('load')
    check_not_challenged(page)

    delete_btn = page.locator('button:has(svg[data-testid="DeleteOutlinedIcon"])').first
    if delete_btn.count() > 0 and delete_btn.is_visible():
        delete_btn.click()
        confirm_dialog = page.get_by_role('dialog', name='Delete Raw model file')
        confirm_dialog.wait_for(state='visible')
        confirm_dialog.get_by_role('button', name='Delete', exact=True).click()
        page.wait_for_timeout(1000)
    else:
        logger.info("No existing raw model file found to delete -- this is a first-time upload")

    browse_btn = page.get_by_role('button', name='Browse', exact=True)
    with page.expect_file_chooser() as fc_info:
        browse_btn.click()
    fc_info.value.set_files(str(scad_path))

    publish_btn = page.get_by_role('button', name='Publish', exact=True)
    publish_btn.wait_for(state='visible')
    page.wait_for_timeout(2000)
    publish_btn.click()

    handle_model_data_changed_dialog(page, notify_message)


def connect_chrome(chrome_user_data_dir: str):
    """Context manager-ish helper: returns (playwright, page). Caller must
    close page (never context/browser -- see module docstring) and exit the
    playwright context."""
    ws_endpoint = resolve_ws_endpoint(chrome_user_data_dir)
    from playwright.sync_api import sync_playwright

    p = sync_playwright().start()
    logger.info("Connecting to Chrome -- approve the 'Allow remote debugging?' popup if it appears")
    try:
        browser = p.chromium.connect_over_cdp(ws_endpoint)
    except Exception as e:
        p.stop()
        # A *stale* DevToolsActivePort is the confusing case: the port in it is
        # still right (Chrome reuses 9222) so the socket connects, but the
        # /devtools/browser/<uuid> path belongs to a previous Chrome session and
        # the handshake just hangs until timeout. Chrome doesn't rewrite the file
        # on restart, and this mode serves no /json/version to discover the
        # current uuid from -- re-toggling the checkbox rewrites the file.
        port_file = Path(chrome_user_data_dir) / 'DevToolsActivePort'
        try:
            age_h = (time.time() - port_file.stat().st_mtime) / 3600
            staleness = f" ({port_file.name} was last written {age_h:.0f}h ago)"
        except OSError:
            staleness = ''
        raise UpdateError(
            f"Couldn't connect to Chrome via {ws_endpoint}{staleness} -- either approve the "
            "permission popup if one appeared, or the endpoint is stale: in Chrome go to "
            "chrome://inspect/#remote-debugging and un-check then re-check 'Allow remote "
            "debugging for this browser instance' (that rewrites the endpoint file), then "
            f"re-run. ({e})"
        )
    context = browser.contexts[0] if browser.contexts else browser.new_context()
    page = context.new_page()
    return p, page


def run_update(args, root_dir: Path):
    notify_message = args.notify_message  # None if --no-notify was passed

    model_dir = root_dir / 'model_pages' / args.model
    if not model_dir.exists():
        print(f"No such model: {model_dir}", file=sys.stderr)
        sys.exit(1)

    cfg = load_project_config(model_dir, root_dir)
    files = resolve_upload_files(root_dir, cfg, need_scad=args.scad)

    p, page = connect_chrome(args.chrome_user_data_dir)
    try:
        try:
            update_print_profile(page, cfg['profile_id'], files['mf3_path'], notify_message)
            poll_verification(page, args.username, cfg['verify_name'])

            if args.scad:
                if not cfg['model_url']:
                    raise UpdateError(
                        "--scad requires project.makerworld_url in the build config "
                        "to determine the model id"
                    )
                model_id = model_id_from_url(cfg['model_url'])
                update_raw_model_file(page, model_id, files['scad_path'], notify_message)
                poll_verification(page, args.username, cfg['verify_name'])
        except Exception:
            debug_path = root_dir / 'dist' / 'makerworld_update_debug.png'
            page.screenshot(path=str(debug_path))
            logger.error(f"Failed -- saved screenshot to {debug_path}")
            raise
    finally:
        page.close()
        p.stop()

    logger.info("Done.")


def run_new_profile(args, root_dir: Path):
    model_dir = root_dir / 'model_pages' / args.model
    if not model_dir.exists():
        print(f"No such model: {model_dir}", file=sys.stderr)
        sys.exit(1)

    cfg = load_project_config(model_dir, root_dir, require_profile_id=False)
    if not cfg['model_url']:
        raise UpdateError(
            f"model_pages/{args.model}/build_config.yaml is missing project.makerworld_url "
            "-- needed to determine the model id to attach the new profile to."
        )
    files = resolve_upload_files(root_dir, cfg, need_scad=False)
    model_id = model_id_from_url(cfg['model_url'])

    photo_paths = [Path(p) for p in args.photo]
    for photo in photo_paths:
        if not photo.exists():
            raise UpdateError(f"Photo not found: {photo}")

    p, page = connect_chrome(args.chrome_user_data_dir)
    try:
        try:
            create_print_profile(
                page, model_id, files['mf3_path'], photo_paths,
                args.name, args.description, args.private,
            )
            # Match on the profile name we explicitly set, NOT cfg['verify_name']
            # -- confirmed broken in practice for opengrid_beam_lite:
            # project_name is "opengrid beam lite" (our own file-naming
            # convention to distinguish the Lite build config) but the real
            # MakerWorld model is just "OpenGrid Beam" (same underlying model
            # as the Full profile). cfg['verify_name'] (from
            # project.makerworld_model_name, or project_name as a fallback)
            # fixes exactly this case when set correctly in the config, but
            # --name is still the most reliable match since it's the literal
            # text MakerWorld will render. If --name wasn't given, MakerWorld's
            # own auto-fill applies and we can't predict it, so fall back to
            # cfg['verify_name'] and warn.
            if args.name:
                verify_name = args.name
            else:
                verify_name = cfg['verify_name']
                logger.warning(
                    "No --name given -- falling back to project.makerworld_model_name "
                    "(or project name) to match the verification queue, which may not "
                    "be what MakerWorld auto-fills."
                )
            poll_verification(page, args.username, verify_name)

            new_id = find_new_profile_id(page, args.username, model_id)
            if new_id:
                logger.info(
                    f"New print profile id: {new_id} -- add this as "
                    f"project.makerworld_profile_id in model_pages/{args.model}/build_config.yaml"
                )
            else:
                logger.warning(
                    "Couldn't auto-detect the new profile's id -- check "
                    f"https://makerworld.com/en/@{args.username}/profile manually."
                )
        except Exception:
            debug_path = root_dir / 'dist' / 'makerworld_update_debug.png'
            page.screenshot(path=str(debug_path))
            logger.error(f"Failed -- saved screenshot to {debug_path}")
            raise
    finally:
        page.close()
        p.stop()

    logger.info("Done.")


def run_new_model(args, root_dir: Path):
    model_dir = root_dir / 'model_pages' / args.model
    if not model_dir.exists():
        print(f"No such model: {model_dir}", file=sys.stderr)
        sys.exit(1)

    cfg = load_project_config(model_dir, root_dir, require_profile_id=False)
    if cfg['model_url'] and not args.force:
        raise UpdateError(
            f"model_pages/{args.model}/build_config.yaml already has "
            f"project.makerworld_url ({cfg['model_url']}), so this model is already "
            "published -- new-model would create a SECOND listing. Use 'update' to "
            "replace its file, 'new-profile' to add a print profile, or --force if a "
            "duplicate listing really is what you want."
        )

    fields = load_publish_fields(cfg['config'], cfg['config_path'], root_dir)
    # A first-time publish is also the one chance to upload the customizer
    # source, so it's on by default for a SCAD model (a prebuilt one has none).
    want_scad = bool(cfg['source_stem']) and not args.no_scad
    files = resolve_upload_files(root_dir, cfg, need_scad=want_scad)

    covers = [Path(p) for p in args.cover]
    photos = [Path(p) for p in args.photo]
    for image in covers + photos:
        if not image.exists():
            raise UpdateError(f"Image not found: {image}")

    logger.info(
        "Publishing from %s\n"
        "  model type : %s%s\n"
        "  name       : %s\n"
        "  category   : %s\n"
        "  tags       : %s\n"
        "  license    : %s\n"
        "  visibility : %s\n"
        "  package    : %s\n"
        "  scad       : %s\n"
        "  covers     : %s\n"
        "  photos     : %s\n"
        "  profile    : %s",
        fields['description_path'].relative_to(root_dir),
        fields['model_type'],
        f" (origin: {', '.join(fields['source_urls'])})" if fields['source_urls'] else '',
        fields['name'], fields['category'], ', '.join(fields['tags']) or '(none)',
        fields['license'] or '(unset)', 'Private' if args.private else 'Public',
        files['mf3_path'].relative_to(root_dir),
        files['scad_path'].relative_to(root_dir) if files.get('scad_path') else '(none)',
        ', '.join(c.name for c in covers) or '(none)',
        ', '.join(p.name for p in photos) or '(none)',
        fields['profile_name'] or "(MakerWorld's own auto-fill)",
    )
    if args.dry_run:
        logger.info("--dry-run: stopping before touching the browser.")
        return

    if not photos and not args.draft:
        logger.warning(
            "No --photo given. MakerWorld's moderation requires at least one real print "
            "photo for Model Pictures and Print Profile Pictures; this publish is likely "
            "to land in the verify-failed queue."
        )

    p, page = connect_chrome(args.chrome_user_data_dir)
    try:
        try:
            draft_url = create_model(
                page, fields, files['mf3_path'], files.get('scad_path'),
                covers, photos, args.private, draft=args.draft,
            )
            if args.draft:
                logger.info(
                    "Draft saved -- nothing was published and nothing entered the "
                    "verification queue. Review it at %s (drafts are listed under "
                    "https://makerworld.com/en/@%s/upload), then publish by hand or "
                    "re-run without --draft.",
                    draft_url, args.username,
                )
                return

            poll_verification(page, args.username, fields['name'])

            model_id = find_new_model_id(page, args.username, fields['name'])
            if not model_id:
                logger.warning(
                    "Couldn't auto-detect the new model's id -- check "
                    f"https://makerworld.com/en/@{args.username}/upload manually."
                )
                return
            profile_id = find_new_profile_id(page, args.username, model_id)
            logger.info(
                "Published. Add to model_pages/%s/build_config.yaml (project:):\n"
                "  makerworld_url: \"https://makerworld.com/en/models/%s\"\n"
                "  makerworld_profile_id: %s",
                args.model, model_id, profile_id or '<look it up: the #profileId- fragment>',
            )
        except Exception:
            debug_path = root_dir / 'dist' / 'makerworld_update_debug.png'
            page.screenshot(path=str(debug_path))
            logger.error(f"Failed -- saved screenshot to {debug_path}")
            raise
    finally:
        page.close()
        p.stop()

    logger.info("Done.")


def main():
    parser = argparse.ArgumentParser(description="Update or extend a MakerWorld listing")
    parser.add_argument('--username', default=DEFAULT_USERNAME)
    parser.add_argument(
        '--chrome-user-data-dir', default=DEFAULT_CHROME_USER_DATA_DIR,
        help="Chrome profile dir to read the DevToolsActivePort file from (see module docstring)"
    )
    parser.add_argument('-v', '--verbose', action='store_true')
    subparsers = parser.add_subparsers(dest='command', required=True)

    update_parser = subparsers.add_parser(
        'update', help="Replace the .3mf on an existing print profile (optionally the raw .scad too)"
    )
    update_parser.add_argument('model', help="Model/profile directory under model_pages/ (e.g. opengrid_facade, or opengrid_beam/full for a multi-profile model)")
    notify_group = update_parser.add_mutually_exclusive_group(required=True)
    notify_group.add_argument(
        '--notify-message', metavar='TEXT',
        help="Geometry changed -- notify print-profile users with this message"
    )
    notify_group.add_argument(
        '--no-notify', action='store_true',
        help="Geometry changed (or this is cosmetic) but no user notification needed"
    )
    update_parser.add_argument('--scad', action='store_true', help="Also update the raw .scad customizer file")

    new_profile_parser = subparsers.add_parser(
        'new-profile', help="First-time publish of a new print profile onto an existing model"
    )
    new_profile_parser.add_argument('model', help="Model/profile directory under model_pages/ (e.g. opengrid_beam/lite)")
    new_profile_parser.add_argument(
        '--photo', action='append', required=True, metavar='PATH',
        help="Real print photo for Print Profile Pictures (repeatable, at least one required)"
    )
    new_profile_parser.add_argument('--name', metavar='TEXT', help="Print Profile Name (defaults to MakerWorld's own auto-fill)")
    new_profile_parser.add_argument('--description', metavar='TEXT', help="Print Profile Description")
    new_profile_parser.add_argument('--private', action='store_true', help="Publish as Private (default: Public)")

    new_model_parser = subparsers.add_parser(
        'new-model', help="First-time publish of a whole new model (creates the listing itself)"
    )
    new_model_parser.add_argument('model', help="Model/profile directory under model_pages/ (e.g. opengrid_facade)")
    new_model_parser.add_argument(
        '--photo', action='append', default=[], metavar='PATH',
        help="Real print photo for Model Pictures and Print Profile Pictures (repeatable)"
    )
    new_model_parser.add_argument(
        '--cover', action='append', default=[], metavar='PATH',
        help="Model Cover image; give it twice for the 4:3 and 3:4 slots separately"
    )
    new_model_parser.add_argument('--private', action='store_true', help="Publish as Private (default: Public)")
    new_model_parser.add_argument(
        '--draft', action='store_true',
        help="Fill the whole wizard but click 'Save to draft' instead of Publish, so the "
             "listing can be reviewed by hand first (nothing enters the verification queue)"
    )
    new_model_parser.add_argument(
        '--no-scad', action='store_true',
        help="Skip uploading the customizer .scad as a Raw Model File (on by default for a SCAD model)"
    )
    new_model_parser.add_argument(
        '--force', action='store_true',
        help="Publish even though the config already has makerworld_url (creates a duplicate listing)"
    )
    new_model_parser.add_argument(
        '--dry-run', action='store_true',
        help="Print everything that would be published and stop before opening the browser"
    )

    args = parser.parse_args()

    if args.verbose:
        logger.setLevel(logging.DEBUG)

    root_dir = Path(__file__).parent.parent

    try:
        if args.command == 'update':
            run_update(args, root_dir)
        elif args.command == 'new-profile':
            run_new_profile(args, root_dir)
        elif args.command == 'new-model':
            run_new_model(args, root_dir)
    except UpdateError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
