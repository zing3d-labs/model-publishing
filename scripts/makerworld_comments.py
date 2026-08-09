#!/usr/bin/env python3
"""
MakerWorld comment-management automation.

list-comments, feed, reply, and resolve are rehearsed and confirmed working
against model_pages/_test_fixture/ (MakerWorld model 3055595, Private) --
see the "MakerWorld comment automation" section in
docs/makerworld_publish_notes.md for the bugs found and fixed along the
way. create-issue is a thin `gh issue create` wrapper with no browser
involved and was reviewed but not live-tested (no need to create a
throwaway issue on a real repo just to rehearse a subprocess call).

Five subcommands:

  list-comments  List comments on one model's page. Prints JSON to stdout.
  feed           List recent comments across ALL your models, from
                 https://makerworld.com/en/my/notification/comments.
                 Prints JSON to stdout.
  reply          Post a threaded reply to a specific comment.
  create-issue   Create a GitHub issue from a comment's content (gh CLI,
                 no browser needed) and print the issue URL plus a
                 suggested `reply` command to link it back.
  resolve        Post a follow-up reply announcing a comment's underlying
                 issue is resolved, linking the issue and optionally a
                 commit/PR.

Shares the CDP browser-connection approach and Cloudflare-challenge
handling with scripts/makerworld_update.py (imported from there) -- see
that module's docstring for why this specific approach is required.

Usage:
    python3 scripts/makerworld_comments.py list-comments opengrid_beam
    python3 scripts/makerworld_comments.py feed --limit 10
    python3 scripts/makerworld_comments.py reply --model opengrid_beam \\
        --reply-id 6453122 --reply-type 1 \\
        --comment-text "do not have the holes for the connectors" \\
        --text "Thanks for the report -- tracking this in..."
    python3 scripts/makerworld_comments.py create-issue \\
        --repo zing3d-labs/openscad-models \\
        --title "Beam: corner pieces" \\
        --author caderoux --comment-text "..." \\
        --model-url https://makerworld.com/en/models/2402751-opengrid-beam \\
        --reply-id 6453122 --reply-type 1
    python3 scripts/makerworld_comments.py resolve --model opengrid_beam \\
        --reply-id 6453122 --reply-type 1 \\
        --comment-text "do not have the holes for the connectors" \\
        --issue-url https://github.com/zing3d-labs/openscad-models/issues/10 \\
        --commit-url https://github.com/zing3d-labs/openscad-models/commit/abc123
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from makerworld_update import (  # noqa: E402
    DEFAULT_CHROME_USER_DATA_DIR, DEFAULT_USERNAME, UpdateError,
    check_not_challenged, connect_chrome, load_project_config, model_id_from_url,
)

import logging  # noqa: E402
logger = logging.getLogger(__name__)


def model_url_for(model_arg: str, root_dir: Path) -> str:
    """model_arg is either a model_pages/<dir> name (resolved via its
    build_config.yaml, same convention as makerworld_update.py) or a raw
    MakerWorld model id/URL, for cases with no local build config (e.g.
    replying about someone else's model, or before a config exists)."""
    model_dir = root_dir / 'model_pages' / model_arg
    if model_dir.exists():
        cfg = load_project_config(model_dir, root_dir, require_profile_id=False)
        if not cfg['model_url']:
            raise UpdateError(f"model_pages/{model_arg}/build_config.yaml has no project.makerworld_url")
        return cfg['model_url']
    if model_arg.isdigit():
        return f'https://makerworld.com/en/models/{model_arg}'
    if model_arg.startswith('http'):
        return model_arg
    raise UpdateError(f"'{model_arg}' is not a model_pages/ dir, a model id, or a URL")


# The comment feed and model-page comment list are NOT documented by
# MakerWorld and were only inspected via chrome-devtools MCP's accessibility
# snapshot, which shows text/roles but not CSS classes or DOM structure --
# so this extraction walks by TEXT PATTERN (an "@username" link followed by
# comment text and a "YYYY-MM-DD HH:MM" timestamp) rather than by selector,
# since no reliable selector is known. CONFIRM AGAINST THE REAL PAGE before
# trusting this for anything beyond casual lookup.
EXTRACT_COMMENTS_JS = r"""
() => {
  const results = [];
  const authorLinks = Array.from(document.querySelectorAll('a[href*="/@"]'))
    .filter(a => /^@?[\w.-]+$/.test((a.textContent || '').trim().replace(/^@/, '')));
  const seen = new Set();
  // MakerWorld shows a RELATIVE timestamp ("32 seconds ago", "5 minutes ago")
  // for recent comments and only switches to absolute "YYYY-MM-DD HH:MM" once
  // enough time has passed -- confirmed live: a comment posted seconds earlier
  // showed "32 seconds ago" and was invisible to an absolute-only regex, while
  // older comments (days+) showed the absolute form. Match both.
  const TS_RE = /\d{4}-\d{2}-\d{2} \d{2}:\d{2}|\b(?:\d+\s+(?:second|minute|hour|day|week|month|year)s?\s+ago|just now)\b/i;
  for (const link of authorLinks) {
    const username = (link.textContent || '').trim().replace(/^@/, '');
    if (!username) continue;
    // Walk up to a container that also holds a timestamp-shaped text node --
    // comment cards are assumed to be a few levels up from the author link.
    let container = link;
    let text = '', timestamp = '';
    for (let depth = 0; depth < 6 && container; depth++) {
      container = container.parentElement;
      if (!container) break;
      const t = container.innerText || '';
      const tsMatch = t.match(TS_RE);
      if (tsMatch) { timestamp = tsMatch[0]; text = t; break; }
    }
    if (!timestamp) continue;
    const key = username + '|' + timestamp;
    if (seen.has(key)) continue;
    seen.add(key);
    results.push({ username, timestamp, raw_text: text.slice(0, 2000) });
  }
  return results;
}
"""


def list_model_comments(page, model_url: str) -> list[dict]:
    page.goto(model_url)
    page.wait_for_load_state('load')
    check_not_challenged(page)
    page.get_by_text('Comment & Rating', exact=False).wait_for(state='visible', timeout=15000)
    return page.evaluate(EXTRACT_COMMENTS_JS)


def list_feed(page, username: str) -> list[dict]:
    page.goto('https://makerworld.com/en/my/notification/comments')
    page.wait_for_load_state('load')
    check_not_challenged(page)
    # Each feed entry's "View Details" link is the reply-targeting URL --
    # extract those directly instead of guessing at card boundaries, since
    # they carry the model id + replyId + replyType we actually need.
    return page.evaluate(r"""
        () => Array.from(document.querySelectorAll('a[href*="replyId="]')).map(a => {
            const url = new URL(a.href);
            const modelId = url.pathname.match(/\/models\/(\d+)/)?.[1] || null;
            return {
                href: a.href,
                model_id: modelId,
                reply_id: url.searchParams.get('replyId'),
                reply_type: url.searchParams.get('replyType'),
            };
        })
    """)


def find_comment_reply_control(page, comment_text: str):
    """Locate the specific comment card by a unique substring of its text,
    then return its own 'Reply' toggle control -- clicking a specific
    comment's Reply (as opposed to the top composer) is what threads the
    response under it. Matches BOTH the closed state ("Reply") and the
    already-open state ("Cancel the reply"): page.goto() to a URL that only
    differs by query string does not force MakerWorld's React app to
    remount, so a composer left open by a prior failed run (or a prior
    invocation in the same browser tab) is still open on the next call --
    confirmed live via a stale debug screenshot where a retry hung for 30s
    because 'Reply' had zero matches (it already read 'Cancel the reply').
    ASSUMPTION, unverified live: 'Reply' renders as plain text (not a
    `button` role) in the comment list, based on the accessibility snapshot
    in docs/makerworld_publish_notes.md showing it as a StaticText sibling
    rather than a labeled button -- hence text-matching here rather than
    get_by_role('button', name='Reply')."""
    card = page.locator(f':has-text("{comment_text}")').last
    card.wait_for(state='visible', timeout=15000)
    reply_control = card.locator(
        'xpath=following::*[normalize-space(text())="Reply" or normalize-space(text())="Cancel the reply"][1]'
    )
    reply_control.wait_for(state='visible', timeout=15000)
    return reply_control


def post_reply(page, model_url: str, reply_id: str, reply_type: str, comment_text: str, reply_text: str):
    url = f'{model_url}?replyId={reply_id}&replyType={reply_type}'
    page.goto(url)
    page.wait_for_load_state('load')
    check_not_challenged(page)

    reply_control = find_comment_reply_control(page, comment_text)
    # Only click to open if it's currently closed ("Reply") -- clicking an
    # already-open composer's "Cancel the reply" toggle would close it.
    if reply_control.inner_text().strip() == 'Reply':
        reply_control.click()
        page.wait_for_timeout(500)

    # Confirmed live this is NOT 'Please fill in your opinion' -- that's the
    # placeholder for the top-level page composer only. Clicking a specific
    # comment's Reply opens a separate threaded composer labeled "Reply
    # @{username}", and clicking ITS placeholder span fails ("intercepts
    # pointer events") because the real contenteditable div sits on top of
    # it. Target the contenteditable div immediately following the Reply
    # control we just clicked, instead of guessing at placeholder text.
    composer = reply_control.locator('xpath=following::*[@contenteditable="true"][1]')
    composer.wait_for(state='visible', timeout=15000)
    # page.keyboard.type() sends to whatever currently has OS-level focus with
    # no re-check -- confirmed live this silently drops all keystrokes here
    # (composer stayed at 0/1000 chars, button stayed disabled) even though
    # the click succeeded. Locator.type() re-focuses the element itself right
    # before typing, closing that race -- same fix already used for the rich
    # text description editor in makerworld_update.py's update_print_profile().
    composer.click()
    composer.type(reply_text)
    page.wait_for_timeout(1000)  # let React's state settle before submitting

    # The threaded reply composer's submit button is labeled "Reply", not
    # "Post" -- "Post" is the TOP-LEVEL page composer's button only (which
    # stays permanently disabled/empty here), confirmed live via the debug
    # screenshot. Scope the lookup to this composer's own form, not the page,
    # since both buttons' accessible names exist simultaneously.
    reply_btn = composer.locator('xpath=ancestor::form[1]').get_by_role('button', name='Reply', exact=True)
    reply_btn.wait_for(state='visible')
    reply_btn.click()
    logger.info(f"Posted reply to replyId={reply_id} on {model_url}")


def run_list_comments(args, root_dir: Path):
    model_url = model_url_for(args.model, root_dir)
    p, page = connect_chrome(args.chrome_user_data_dir)
    try:
        comments = list_model_comments(page, model_url)
        if args.limit:
            comments = comments[:args.limit]
        print(json.dumps(comments, indent=2))
    finally:
        page.close()
        p.stop()


def run_feed(args, root_dir: Path):
    p, page = connect_chrome(args.chrome_user_data_dir)
    try:
        entries = list_feed(page, args.username)
        if args.limit:
            entries = entries[:args.limit]
        print(json.dumps(entries, indent=2))
    finally:
        page.close()
        p.stop()


def run_reply(args, root_dir: Path):
    model_url = model_url_for(args.model, root_dir)
    p, page = connect_chrome(args.chrome_user_data_dir)
    try:
        try:
            post_reply(page, model_url, args.reply_id, args.reply_type, args.comment_text, args.text)
        except Exception:
            debug_path = root_dir / 'dist' / 'makerworld_comments_debug.png'
            page.screenshot(path=str(debug_path))
            logger.error(f"Failed -- saved screenshot to {debug_path}")
            raise
    finally:
        page.close()
        p.stop()


def run_create_issue(args, root_dir: Path):
    comment_link = f'{args.model_url}?replyId={args.reply_id}&replyType={args.reply_type}'
    body = (
        f"Requested by @{args.author} on MakerWorld: {comment_link}\n\n"
        f"> {args.comment_text}\n"
    )
    result = subprocess.run(
        ['gh', 'issue', 'create', '--repo', args.repo, '--title', args.title, '--body', body],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise UpdateError(f"gh issue create failed: {result.stderr.strip()}")
    issue_url = result.stdout.strip()
    print(issue_url)
    logger.info(
        "Issue created. To link it back on MakerWorld:\n"
        f"  python3 {Path(__file__).name} reply --model <model> "
        f"--reply-id {args.reply_id} --reply-type {args.reply_type} "
        f"--comment-text \"{args.comment_text[:40]}...\" "
        f"--text \"Thanks for the report -- tracking it here: {issue_url}\""
    )


def run_resolve(args, root_dir: Path):
    message = f"This has been resolved: {args.issue_url}"
    if args.commit_url:
        message += f"\nFixed in: {args.commit_url}"
    model_url = model_url_for(args.model, root_dir)
    p, page = connect_chrome(args.chrome_user_data_dir)
    try:
        try:
            post_reply(page, model_url, args.reply_id, args.reply_type, args.comment_text, message)
        except Exception:
            debug_path = root_dir / 'dist' / 'makerworld_comments_debug.png'
            page.screenshot(path=str(debug_path))
            logger.error(f"Failed -- saved screenshot to {debug_path}")
            raise
    finally:
        page.close()
        p.stop()


def main():
    parser = argparse.ArgumentParser(description="MakerWorld comment lookup, reply, and issue tracking")
    parser.add_argument('--username', default=DEFAULT_USERNAME)
    parser.add_argument('--chrome-user-data-dir', default=DEFAULT_CHROME_USER_DATA_DIR)
    parser.add_argument('-v', '--verbose', action='store_true')
    subparsers = parser.add_subparsers(dest='command', required=True)

    lc = subparsers.add_parser('list-comments', help="List comments on one model")
    lc.add_argument('model', help="model_pages/ dir name, a model id, or a MakerWorld model URL")
    lc.add_argument('--limit', type=int)

    feed = subparsers.add_parser('feed', help="List recent comments across all your models")
    feed.add_argument('--limit', type=int)

    reply = subparsers.add_parser('reply', help="Post a threaded reply to a specific comment")
    reply.add_argument('--model', required=True, help="model_pages/ dir name, a model id, or a MakerWorld model URL")
    reply.add_argument('--reply-id', required=True)
    reply.add_argument('--reply-type', required=True)
    reply.add_argument('--comment-text', required=True, metavar='SNIPPET', help="Unique substring of the comment's text, used to locate its Reply control")
    reply.add_argument('--text', required=True, help="Reply text to post")

    ci = subparsers.add_parser('create-issue', help="Create a GitHub issue from a comment (no browser)")
    ci.add_argument('--repo', required=True, metavar='OWNER/REPO')
    ci.add_argument('--title', required=True)
    ci.add_argument('--author', required=True, help="MakerWorld username of the commenter")
    ci.add_argument('--comment-text', required=True, help="The comment's full text, included in the issue body")
    ci.add_argument('--model-url', required=True)
    ci.add_argument('--reply-id', required=True)
    ci.add_argument('--reply-type', required=True)

    resolve = subparsers.add_parser('resolve', help="Reply announcing a comment's issue is resolved")
    resolve.add_argument('--model', required=True, help="model_pages/ dir name, a model id, or a MakerWorld model URL")
    resolve.add_argument('--reply-id', required=True)
    resolve.add_argument('--reply-type', required=True)
    resolve.add_argument('--comment-text', required=True, metavar='SNIPPET')
    resolve.add_argument('--issue-url', required=True)
    resolve.add_argument('--commit-url')

    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    root_dir = Path(__file__).parent.parent

    try:
        if args.command == 'list-comments':
            run_list_comments(args, root_dir)
        elif args.command == 'feed':
            run_feed(args, root_dir)
        elif args.command == 'reply':
            run_reply(args, root_dir)
        elif args.command == 'create-issue':
            run_create_issue(args, root_dir)
        elif args.command == 'resolve':
            run_resolve(args, root_dir)
    except UpdateError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
