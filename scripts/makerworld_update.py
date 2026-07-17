#!/usr/bin/env python3
"""
MakerWorld update automation.

Two subcommands, both documented in docs/makerworld_publish_notes.md:

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

Requires the model to already be built (run scad_builder.py first).

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
    python3 scripts/makerworld_update.py update opengrid_beam --notify-message "..."
    python3 scripts/makerworld_update.py update opengrid_beam --no-notify
    python3 scripts/makerworld_update.py update opengrid_beam --no-notify --scad
    python3 scripts/makerworld_update.py new-profile opengrid_beam_lite \\
        --photo model_pages/opengrid_beam/images/opengrid_beam_wide_view.jpg \\
        --name "Lite Print Settings" --description "..."
"""

import argparse
import logging
import sys
import time
from pathlib import Path

import yaml

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DEFAULT_CHROME_USER_DATA_DIR = str(Path.home() / 'Library' / 'Application Support' / 'Google' / 'Chrome')
DEFAULT_USERNAME = 'jonnydev13'
VERIFY_POLL_INTERVAL_S = 10
VERIFY_TIMEOUT_S = 300
ENQUEUE_POLL_INTERVAL_S = 3
ENQUEUE_TIMEOUT_S = 60


class UpdateError(Exception):
    pass


def load_project_config(model_dir: Path, require_profile_id: bool = True) -> dict:
    config_path = model_dir / 'build_config.yaml'
    if not config_path.exists():
        raise UpdateError(f"No build_config.yaml found at {config_path}")
    with open(config_path) as f:
        config = yaml.safe_load(f)

    project = config.get('project', {})
    if require_profile_id and 'makerworld_profile_id' not in project:
        raise UpdateError(
            f"{config_path} is missing project.makerworld_profile_id. "
            "Look up the profile ID from the model's MakerWorld page URL "
            "(the #profileId-XXXXXXX fragment) and add it to the config."
        )

    source = config.get('source', {})
    if 'input_file' not in source:
        raise UpdateError(f"{config_path} is missing source.input_file")

    project_name = project['name'].lower().replace(' ', '_')
    source_stem = Path(source['input_file']).stem

    return {
        'project_name': project_name,
        'source_stem': source_stem,
        'profile_id': project.get('makerworld_profile_id'),
        'model_url': project.get('makerworld_url'),
    }


def model_id_from_url(url: str) -> str:
    # e.g. https://makerworld.com/en/models/2402751-opengrid-beam -> "2402751"
    slug = url.rstrip('/').split('/')[-1]
    return slug.split('-')[0]


def resolve_dist_files(root_dir: Path, project_name: str, source_stem: str, need_scad: bool) -> dict:
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
                f"'{model_name}' never showed up at {verifying_url} within "
                f"{ENQUEUE_TIMEOUT_S}s of clicking Confirm. Check manually -- Confirm may not "
                "have actually submitted, or the queue lag is longer than expected."
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
        raise UpdateError(
            f"Couldn't connect to Chrome via {ws_endpoint} -- make sure Chrome is running "
            "with chrome://inspect/#remote-debugging enabled, and approve the permission "
            f"popup if one appeared. ({e})"
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

    cfg = load_project_config(model_dir)
    files = resolve_dist_files(root_dir, cfg['project_name'], cfg['source_stem'], need_scad=args.scad)

    p, page = connect_chrome(args.chrome_user_data_dir)
    try:
        try:
            update_print_profile(page, cfg['profile_id'], files['mf3_path'], notify_message)
            poll_verification(page, args.username, cfg['project_name'].replace('_', ' '))

            if args.scad:
                if not cfg['model_url']:
                    raise UpdateError(
                        "--scad requires project.makerworld_url in the build config "
                        "to determine the model id"
                    )
                model_id = model_id_from_url(cfg['model_url'])
                update_raw_model_file(page, model_id, files['scad_path'], notify_message)
                poll_verification(page, args.username, cfg['project_name'].replace('_', ' '))
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

    cfg = load_project_config(model_dir, require_profile_id=False)
    if not cfg['model_url']:
        raise UpdateError(
            f"model_pages/{args.model}/build_config.yaml is missing project.makerworld_url "
            "-- needed to determine the model id to attach the new profile to."
        )
    files = resolve_dist_files(root_dir, cfg['project_name'], cfg['source_stem'], need_scad=False)
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
            # Match on the profile name we explicitly set, NOT
            # cfg['project_name'] -- confirmed broken in practice for
            # opengrid_beam_lite: project_name is "opengrid beam lite" (our
            # own file-naming convention to distinguish the Lite build
            # config) but the real MakerWorld model is just "OpenGrid Beam"
            # (same underlying model as the Full profile), so that search
            # string would never appear in the verifying-queue page at all.
            # If --name wasn't given, MakerWorld's own auto-fill applies and
            # we can't predict it, so fall back to project_name and warn.
            if args.name:
                verify_name = args.name
            else:
                verify_name = cfg['project_name'].replace('_', ' ')
                logger.warning(
                    "No --name given -- falling back to the project name to match the "
                    "verification queue, which may not be what MakerWorld auto-fills."
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
    update_parser.add_argument('model', help="Model directory name under model_pages/ (e.g. opengrid_beam)")
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
    new_profile_parser.add_argument('model', help="Model directory name under model_pages/ (e.g. opengrid_beam_lite)")
    new_profile_parser.add_argument(
        '--photo', action='append', required=True, metavar='PATH',
        help="Real print photo for Print Profile Pictures (repeatable, at least one required)"
    )
    new_profile_parser.add_argument('--name', metavar='TEXT', help="Print Profile Name (defaults to MakerWorld's own auto-fill)")
    new_profile_parser.add_argument('--description', metavar='TEXT', help="Print Profile Description")
    new_profile_parser.add_argument('--private', action='store_true', help="Publish as Private (default: Public)")

    args = parser.parse_args()

    if args.verbose:
        logger.setLevel(logging.DEBUG)

    root_dir = Path(__file__).parent.parent

    try:
        if args.command == 'update':
            run_update(args, root_dir)
        elif args.command == 'new-profile':
            run_new_profile(args, root_dir)
    except UpdateError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
