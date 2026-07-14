#!/usr/bin/env python3
"""Export a Google AI Studio chat ("Playground" prompt) to a Markdown file.

Usage:
    python3 aistudio_chat_export.py <AI_STUDIO_URL> [-o output.md] [--thoughts]

Setup (one-time):
    pip install playwright browser_cookie3
    python3 -m playwright install chromium

How it works:
    AI Studio requires a logged-in Google session, and its chat list is
    virtualized (only turns scrolled into view exist in the DOM). Rather
    than touching your real Chrome window or asking you to log in again,
    this script:

      1. Reads your existing Google session cookies straight out of
         Chrome's cookie store (via browser_cookie3, which decrypts them
         using your macOS Keychain -- you may see a one-time Keychain
         permission prompt).
      2. Injects those cookies into a fresh, separate, headless Chromium
         instance (launched by Playwright; your real Chrome is never
         opened, touched, or restarted).
      3. Scrolls through each chat turn in that headless page (which has
         a normal "visible" document state, unlike a backgrounded real
         browser tab, so AI Studio's virtual scroll renders correctly)
         and converts each turn's HTML to Markdown.

    This means: no new login, no relaunching your browser, no extra
    windows on screen.
"""
import argparse
import re
import sys
from pathlib import Path

import browser_cookie3
from playwright.sync_api import sync_playwright, Page

# Converts a DOM subtree to Markdown from inside the page (JS, not Python),
# since the browser has already parsed the HTML for us.
DOM_TO_MD_JS = r"""
(rootEl) => {
  function walk(node) {
    if (node.nodeType === Node.TEXT_NODE) {
      return node.textContent.replace(/ /g, ' ');
    }
    if (node.nodeType !== Node.ELEMENT_NODE) return '';
    const tag = node.tagName.toLowerCase();
    const cls = node.className || '';
    if (['button', 'mat-icon', 'svg', 'path', 'mat-ripple'].includes(tag)) return '';
    if (node.getAttribute && node.getAttribute('aria-hidden') === 'true') return '';
    if (/turn-footer|turn-information/.test(cls)) return '';
    const children = Array.from(node.childNodes).map(walk).join('');
    switch (tag) {
      case 'h1': return `\n# ${children.trim()}\n`;
      case 'h2': return `\n## ${children.trim()}\n`;
      case 'h3': return `\n### ${children.trim()}\n`;
      case 'h4': return `\n#### ${children.trim()}\n`;
      case 'strong': case 'b': return `**${children}**`;
      case 'em': case 'i': return `*${children}*`;
      case 'code': return node.closest('pre') ? children : `\`${children}\``;
      case 'pre': return `\n\`\`\`\n${node.innerText}\n\`\`\`\n`;
      case 'a': {
        let href = node.getAttribute('href') || '';
        href = href.split('?')[0];
        return href ? `[${children}](${href})` : children;
      }
      case 'li': {
        const parent = node.parentElement ? node.parentElement.tagName.toLowerCase() : 'ul';
        const prefix = parent === 'ol' ? '1.' : '-';
        return `${prefix} ${children.trim()}\n`;
      }
      case 'ul': case 'ol': return `\n${children}\n`;
      case 'p': case 'div': return `${children}\n`;
      case 'br': return '\n';
      case 'blockquote': return `\n> ${children.trim()}\n`;
      default: return children;
    }
  }
  return walk(rootEl).replace(/\n{3,}/g, '\n\n').trim();
}
"""


def load_google_cookies():
    print("Reading Google session cookies from Chrome...", file=sys.stderr)
    cj = browser_cookie3.chrome(domain_name=".google.com")
    cookies = [
        {
            "name": c.name,
            "value": c.value,
            "domain": c.domain,
            "path": c.path,
            "secure": bool(c.secure),
        }
        for c in cj
    ]
    print(f"  loaded {len(cookies)} cookies", file=sys.stderr)
    return cookies


def export_chat(page: Page, include_thoughts: bool) -> str:
    container = page.locator("ms-autoscroll-container").first
    container.wait_for(state="visible", timeout=30000)

    turns = page.locator(".chat-turn-container")
    count = turns.count()
    print(f"Found {count} turns", file=sys.stderr)

    parsed = []
    for i in range(count):
        turn = turns.nth(i)
        turn.scroll_into_view_if_needed()
        page.wait_for_timeout(150)

        class_attr = turn.get_attribute("class") or ""
        role = "User" if "user" in class_attr.split() else "Model"

        content_el = turn.locator(".turn-content").first
        if content_el.count() == 0:
            content_el = turn

        md = content_el.evaluate(DOM_TO_MD_JS)
        md = re.sub(r"\n?Expand to view model thoughts\n?", "\n", md).strip()

        ts_match = re.match(r"^(?:User|Model)\s+(\d{1,2}:\d{2}\s*[AP]M)\s*\n?", md)
        ts = ts_match.group(1) if ts_match else None
        if ts_match:
            md = md[ts_match.end():].lstrip()
        is_thoughts = md.startswith("Thoughts")
        if is_thoughts and not include_thoughts:
            md = ""

        label = f"{role} (thoughts)" if is_thoughts else role
        print(f"  [{i + 1}/{count}] {label}: {len(md)} chars", file=sys.stderr)
        parsed.append((label, ts, md))

    # Adjacent DOM turns of the same role are fragments of one logical
    # message (e.g. an attachment chip turn followed by the text turn).
    merged = []
    for label, ts, md in parsed:
        if merged and merged[-1][0] == label:
            prev_ts, prev_md = merged[-1][1], merged[-1][2]
            new_md = (prev_md + "\n\n" + md).strip() if md else prev_md
            merged[-1] = (label, prev_ts or ts, new_md)
        else:
            merged.append((label, ts, md))

    sections = []
    for label, ts, md in merged:
        if not md:
            continue
        header = f"## {label}" + (f" — {ts}" if ts else "")
        sections.append(f"{header}\n\n{md}\n")
    return "\n".join(sections)


def main():
    parser = argparse.ArgumentParser(description="Export a Google AI Studio chat to Markdown")
    parser.add_argument("url", help="AI Studio prompt URL")
    parser.add_argument("-o", "--output", default=None,
                         help="Output .md path (default: derived from the page title)")
    parser.add_argument("--thoughts", action="store_true",
                         help="Also expand and include the model's 'Thoughts' panels")
    parser.add_argument("--headed", action="store_true",
                         help="Show the browser window (debugging only)")
    args = parser.parse_args()

    cookies = load_google_cookies()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.headed)
        context = browser.new_context(viewport={"width": 1400, "height": 900})
        context.add_cookies(cookies)
        page = context.new_page()

        print(f"Navigating to {args.url}...", file=sys.stderr)
        page.goto(args.url, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)

        if "accounts.google.com" in page.url:
            print("ERROR: redirected to a Google login page -- the cookies "
                  "from Chrome didn't authenticate. Make sure you're logged "
                  "into AI Studio in Chrome and try again.", file=sys.stderr)
            sys.exit(1)

        body = export_chat(page, include_thoughts=args.thoughts)

        title = "aistudio_chat"
        try:
            raw_title = page.title().split(" | ")[0].strip()
            if raw_title:
                title = raw_title
        except Exception:
            pass

        safe_title = re.sub(r"[^\w\- ]", "", title).strip() or "aistudio_chat"
        out_path = Path(args.output) if args.output else Path(f"{safe_title}.md")
        out_path.write_text(f"# {title}\n\n{body}\n", encoding="utf-8")
        print(f"Wrote {out_path}", file=sys.stderr)

        browser.close()


if __name__ == "__main__":
    main()
