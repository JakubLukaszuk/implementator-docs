#!/usr/bin/env python3
"""Build the Implementator site into docs/, which Cloudflare Pages serves at implementator.io.

The prose lives in src/. The settings tables and the presets are generated from the implementator
repo itself, so a value on the Configuration page is the value the pack ships.

Usage:
  python build.py            build into docs/
  python build.py --check    build in memory and fail on anything below; writes nothing

--check fails when docs/ is stale, a setting has no text here (or the text names one that is gone), a
page links to a file or anchor that does not exist, a page uses a word that must not appear, or a page
breaks the search rules in search_problems(): title, description, one h1, valid JSON-LD, alt text.
Cloudflare Pages drops .html from every URL with a redirect, so pages link and canonicalise without it.
The source repo is ../implementator, or IMPLEMENTATOR_REPO.
"""
import html
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "src")
OUT = os.path.join(ROOT, "docs")
IMPL = os.environ.get("IMPLEMENTATOR_REPO") or os.path.join(os.path.dirname(ROOT), "implementator")

SITE = "https://implementator.io"
DOMAIN = "implementator.io"
CREATOR = "https://www.agensi.io/creators/nihillon"
PUBLISHED = "2026-11-06"
UPDATED = "2026-11-07"
UPDATED_TEXT = "7 November 2026"
SUMMARY = ("Implementator is a skill pack for Claude Code and Codex. Every change gets a plan you approve, "
           "real tests, independent review, your own manual test and a written record.")
INDEXNOW_KEY = "0bb402f061cb64e6ad7a05b5b72bf6ba"
# Ownership proof for Google Search Console (property https://implementator.io/). Removing it unverifies the site.
GOOGLE_SITE_VERIFICATION = "GseKEoAASbjK7dr1iqpz1V6n36PBJjY4VawsOpNJdLY"

PAGES = [("overview", "Overview"), ("get-started", "Get started"), ("first-project", "Your first project"),
         ("daily-use", "Daily use"), ("configuration", "Configuration"), ("videos", "Videos"),
         ("troubleshooting", "Troubleshooting")]

# Search title and description of each page.
META = {
    "index": ("Implementator: a process for Claude Code and Codex",
              "A skill pack that gives Claude Code and Codex one loop for every change: a plan you approve, tests, independent review, your manual test and a record."),
    "overview": ("What is Implementator? Skills, loop and limits",
                 "What Implementator is: the eight-stage loop, the thirteen skills in the pack, what stays yours, and what it cannot promise."),
    "get-started": ("Get started with Implementator in Claude Code or Codex",
                    "Connect Claude Code or Codex CLI to the store, run the setup, answer six questions and create your notes repo. Includes Codex on Windows."),
    "first-project": ("Your first project with Implementator, step by step",
                      "From a code repo to one finished change: connect the repo, approve its skills, run preflight, approve a plan, test by hand, commit and close."),
    "daily-use": ("Daily use: how to work with Implementator",
                  "What a normal day looks like with Implementator: resuming work, starting a change, tickets, mockups, reviews and what to say to your agent."),
    "configuration": ("Implementator configuration: every setting and preset",
                      "Every Implementator setting with its values and default, plus the presets, how a value is resolved and how to change one in plain language."),
    "videos": ("Implementator videos: real runs from ticket to merge",
               "Nine replays of real runs on a public demo repo: setup, one full change, Jira tickets, mockups, GitHub pull requests and Codex on Windows."),
    "troubleshooting": ("Implementator troubleshooting: common errors and fixes",
                        "Fixes for skipped stages, spawn EPERM, blocked commands, gh token warnings, Windows path limits and lost connections, as the pack reports them."),
}

# Written by hand and kept in docs/: the videos, their posters and the images.
ASSET_DIRS = ("videos", "img")
# Kept at the root of docs/ across builds.
KEEP = ("favicon.ico",)

SECURITY_HEADERS = """/*
  Strict-Transport-Security: max-age=31536000; includeSubDomains
  Content-Security-Policy: default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; media-src 'self'; font-src 'self'; connect-src 'self'; manifest-src 'self'; base-uri 'self'; form-action 'none'; frame-ancestors 'none'; upgrade-insecure-requests
  X-Content-Type-Options: nosniff
  X-Frame-Options: DENY
  Referrer-Policy: strict-origin-when-cross-origin
  Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=(), usb=(), browsing-topics=()
  Cross-Origin-Opener-Policy: same-origin

/img/*
  Cache-Control: public, max-age=604800

/videos/*
  Cache-Control: public, max-age=604800

https://:project.pages.dev/*
  X-Robots-Tag: noindex

https://:version.:project.pages.dev/*
  X-Robots-Tag: noindex
"""

# Search and answer engines named one by one, so a blanket rule elsewhere cannot be read as a refusal.
CRAWLERS = ("Googlebot", "Bingbot", "Google-Extended", "GPTBot", "OAI-SearchBot", "ChatGPT-User", "ClaudeBot",
            "Claude-SearchBot", "Claude-User", "PerplexityBot", "Perplexity-User", "Applebot", "Applebot-Extended",
            "Amazonbot", "DuckDuckBot", "DuckAssistBot", "Meta-ExternalAgent", "MistralAI-User", "cohere-ai")

VIDEOS = {
    "v1-what-it-does": ("What Implementator does", "A real change, from a Jira ticket to a merged pull request.", 61),
    "v2-set-it-up": ("Set it up", "The notes repo, the pointer file and the six questions.", 95),
    "v3-connect-a-repo": ("Connect a repo", "What the agent detects, and the skills it proposes.", 111),
    "v4-one-change": ("One change, start to finish", "Plan, code, tests, review, manual test, pull request, close.", 190),
    "v5-change-a-setting": ("Change a setting", "A plain request, a diff, a yes, and a gate that will not switch off.", 54),
    "v6-codex-on-windows": ("Codex on Windows", "The sandbox, and what the agent does when Node cannot run there.", 84),
    "v8-jira-ticket": ("Work from a Jira ticket", "The ticket is read, saved unchanged, and planned from.", 81),
    "v9-mockup-to-code": ("From a mockup to shipped code", "Options on the running page, a pick, then the whole loop.", 201),
    "v10-github": ("GitHub, from branch to merge", "A real draft pull request, CI, your merge, and the close.", 109),
}


sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.join(IMPL, "scripts"))
import cfg_core                                                # noqa: E402
from impl_schema import load_schemas                           # noqa: E402


def read(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as f:
        return f.read()


def forbidden_words():
    """Words that must never reach a public page, one per line. The list names them, so it stays on
    the owner's machine and out of this public repo."""
    path = os.path.join(ROOT, "forbidden-words.txt")
    if not os.path.isfile(path):
        return []
    return [w.strip().lower() for w in read(path).splitlines() if w.strip()]


def code(value):
    return "<code>" + html.escape(value if isinstance(value, str) else json.dumps(value)) + "</code>"


def values_cell(rule):
    if rule.get("enum"):
        return " ".join(code(v) for v in rule["enum"])
    return {"boolean": "<code>true</code> <code>false</code>", "integer": "a whole number",
            "array": "a list", "string": "text"}.get(rule.get("type"), "")


def default_cell(rule):
    return code(rule["default"]) if "default" in rule else "not set"


def example(key, rule):
    """The setting as it looks in a config file, built from its real default."""
    value = rule.get("default")
    if value is None:
        value = rule["enum"][0] if rule.get("enum") else "..."
    for part in reversed(key.split(".")):
        value = {part: value}
    return json.dumps(value)


def settings_tables(spec, text):
    out = []
    for group in text["groups"]:
        out.append('<h3 id="' + group["id"] + '">' + group["title"] + "</h3>")
        if group.get("intro"):
            out.append("<p>" + group["intro"] + "</p>")
        for key, entry in group["keys"].items():
            rule = spec[key]
            scope = "each project" if rule.get("s") == "p" else "all projects, or one"
            out.append(
                '<article class="setting" id="' + key + '"><h4>' + code(key) + "</h4>"
                "<p>" + entry["what"] + "</p>"
                + ("<p><b>Change it when:</b> " + entry["when"] + "</p>" if entry.get("when") else "")
                + '<dl><dt>Values</dt><dd>' + values_cell(rule) + "</dd>"
                "<dt>Default</dt><dd>" + default_cell(rule) + "</dd>"
                "<dt>Applies to</dt><dd>" + scope + "</dd></dl>"
                "<pre><code>" + html.escape(example(key, rule)) + "</code></pre></article>")
    return "\n".join(out)


def stage_table(spec, text):
    rows = []
    for stage, what in text["stages"].items():
        pre = "orchestration.stages." + stage + "."
        rows.append("<tr><td>" + code(stage) + "</td><td>" + what + "</td><td>"
                    + code(spec[pre + "model"]["default"]) + "</td><td>" + code(spec[pre + "effort"]["default"])
                    + "</td><td>" + ("yes" if spec[pre + "isolate"].get("default") else "no") + "</td></tr>")
    return ('<div class="wide"><table><thead><tr><th>Stage</th><th>What runs</th><th>Tier</th><th>Effort</th>'
            "<th>Own subagent</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>")


def presets_table():
    d = os.path.join(IMPL, ".claude", "skills", "configure", "presets")
    rows = []
    for fn in sorted(os.listdir(d)):
        if fn.endswith(".json"):
            rows.append("<tr><td>" + code(fn[:-5]) + "</td><td>"
                        + html.escape(json.loads(read(d, fn))["summary"]) + "</td></tr>")
    return ('<div class="wide"><table><thead><tr><th>Preset</th><th>What it sets up</th></tr></thead><tbody>'
            + "".join(rows) + "</tbody></table></div>")


def film(key, autoplay=False):
    title, note, _ = VIDEOS[key]
    return ('<figure class="film"><video controls preload="none" playsinline poster="img/posters/' + key
            + '.jpg" src="videos/' + key + '.webm" aria-label="' + html.escape(title) + '"></video>'
            '<figcaption><b>' + html.escape(title) + "</b> " + html.escape(note) + "</figcaption></figure>")


def films(text):
    text = re.sub(r"\{\{film:([a-z0-9-]+)\}\}", lambda m: film(m.group(1)), text)
    return text.replace("{{all-films}}", "\n".join(film(k) for k in VIDEOS))


def stamp():
    rev = subprocess.run(["git", "-C", IMPL, "rev-parse", "--short", "HEAD"], capture_output=True, text=True)
    return rev.stdout.strip() or "unknown"


def nav(current):
    items = []
    for slug, title in PAGES:
        here = ' aria-current="page"' if slug == current else ""
        items.append('<li><a href="' + slug + '.html"' + here + ">" + title + "</a></li>")
    return "\n".join(items)


def pager(current):
    """Links to the page before and after this one, so the docs read through in order."""
    slugs = [s for s, _ in PAGES]
    i = slugs.index(current)
    out = []
    if i > 0:
        out.append('<a class="prev" href="' + PAGES[i - 1][0] + '.html"><span>Previous</span>' + PAGES[i - 1][1] + "</a>")
    if i < len(PAGES) - 1:
        out.append('<a class="next" href="' + PAGES[i + 1][0] + '.html"><span>Next</span>' + PAGES[i + 1][1] + "</a>")
    return '<nav class="pager" aria-label="Pages">' + "".join(out) + "</nav>"


def page_url(slug):
    return SITE + "/" + ("" if slug == "index" else slug)


def rooted(page):
    """Every local link as a root path with no .html, the form Cloudflare Pages serves it in."""
    def fix(m):
        attr, value = m.group(1), m.group(2)
        if re.match(r"https?:|mailto:|data:|#|/", value):
            return m.group(0)
        path, sep, anchor = value.partition("#")
        path = "" if path == "index.html" else re.sub(r"\.html$", "", path)
        return attr + '="/' + path + sep + anchor + '"'
    return re.sub(r'\b(data-src|href|src|poster)="([^"]*)"', fix, page)


def plain(fragment):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", fragment))).strip()


def faq_ld(pattern, page):
    return {"@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": plain(q), "acceptedAnswer": {"@type": "Answer", "text": plain(a)}}
        for q, a in re.findall(pattern, page)]}


ORG = {"@type": "Organization", "@id": SITE + "/#org", "name": "Implementator", "url": SITE + "/",
       "logo": {"@type": "ImageObject", "url": SITE + "/img/logo.png", "width": 512, "height": 512},
       "sameAs": [CREATOR]}
ORG_REF = {"@id": SITE + "/#org"}


def home_ld(page):
    return [ORG,
            {"@type": "WebSite", "@id": SITE + "/#site", "url": SITE + "/", "name": "Implementator",
             "description": SUMMARY, "inLanguage": "en", "publisher": ORG_REF},
            {"@type": "SoftwareApplication", "@id": SITE + "/#app", "name": "Implementator", "url": SITE + "/",
             "description": SUMMARY, "applicationCategory": "DeveloperApplication",
             "applicationSubCategory": "AI coding agent skill pack", "operatingSystem": "Windows",
             "softwareVersion": "1.0", "softwareRequirements": "Claude Code or Codex CLI, Python 3.8 or newer, git",
             "image": SITE + "/img/og.png", "publisher": ORG_REF,
             "featureList": ["A plan you approve before any code", "Skills generated for each repo",
                             "Tests and a self-test on the real app", "Independent review by separate subagents",
                             "A manual test you run", "A written record in a notes repo you own"]},
            faq_ld(r'<article class="q"><h3>(.*?)</h3>(.*?)</article>', page)]


def doc_ld(slug, body):
    url = page_url(slug)
    graph = [{"@type": "TechArticle", "@id": url + "#article", "headline": META[slug][0], "description": META[slug][1],
              "url": url, "mainEntityOfPage": url, "inLanguage": "en", "image": SITE + "/img/og.png",
              "datePublished": PUBLISHED, "dateModified": UPDATED, "author": ORG_REF, "publisher": ORG_REF,
              "about": {"@id": SITE + "/#app"}, "isPartOf": {"@id": SITE + "/#site"}},
             {"@type": "BreadcrumbList", "itemListElement": [
                 {"@type": "ListItem", "position": 1, "name": "Implementator", "item": SITE + "/"},
                 {"@type": "ListItem", "position": 2, "name": dict(PAGES)[slug], "item": url}]}]
    if slug == "troubleshooting":
        graph.append(faq_ld(r'<div class="qa"[^>]*>\s*<h2>(.*?)</h2>([\s\S]*?)</div>', body))
    if slug == "videos":
        graph += [{"@type": "VideoObject", "name": t, "description": n, "duration": "PT%dM%dS" % (s // 60, s % 60),
                   "uploadDate": PUBLISHED + "T12:00:00+00:00", "thumbnailUrl": SITE + "/img/posters/" + k + ".jpg",
                   "contentUrl": SITE + "/videos/" + k + ".webm", "publisher": ORG_REF}
                  for k, (t, n, s) in VIDEOS.items()]
    return graph


def head(slug, graph, meta=None):
    title, description = meta or META[slug]
    url = page_url(slug)
    lines = ['<meta charset="utf-8">',
             '<meta name="viewport" content="width=device-width, initial-scale=1">',
             "<title>" + html.escape(title) + "</title>",
             '<meta name="description" content="' + html.escape(description) + '">']
    if graph:
        lines += ['<meta name="robots" content="index, follow, max-image-preview:large, max-snippet:-1, max-video-preview:-1">',
                  '<link rel="canonical" href="' + url + '">']
    else:
        lines.append('<meta name="robots" content="noindex">')
    lines += ['<meta name="google-site-verification" content="' + GOOGLE_SITE_VERIFICATION + '">',
              '<meta name="theme-color" content="#0b0d12">',
              '<meta property="og:type" content="' + ("website" if slug == "index" else "article") + '">',
              '<meta property="og:site_name" content="Implementator">',
              '<meta property="og:title" content="' + html.escape(title) + '">',
              '<meta property="og:description" content="' + html.escape(description) + '">',
              '<meta property="og:url" content="' + url + '">',
              '<meta property="og:image" content="' + SITE + '/img/og.png">',
              '<meta property="og:image:width" content="1200">',
              '<meta property="og:image:height" content="630">',
              '<meta property="og:image:alt" content="Implementator: your coding agent, with a process.">',
              '<meta property="og:locale" content="en_US">',
              '<meta name="twitter:card" content="summary_large_image">',
              '<link rel="icon" href="/favicon.ico" sizes="48x48">',
              '<link rel="icon" type="image/png" href="/img/icon-192.png" sizes="192x192">',
              '<link rel="apple-touch-icon" href="/img/apple-touch-icon.png">',
              '<link rel="manifest" href="/site.webmanifest">',
              '<link rel="stylesheet" href="/base.css">']
    if graph:
        ld = json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False).replace("</", "<\\/")
        lines.append('<script type="application/ld+json">' + ld + "</script>")
    return "\n".join(lines)


def to_text(fragment):
    """A page as plain Markdown, for readers that do not render HTML."""
    s = re.sub(r"<(script|style|video)\b[\s\S]*?</\1>", "", fragment)
    s = re.sub(r"<pre><code>([\s\S]*?)</code></pre>", lambda m: "\n```\n" + m.group(1) + "\n```\n", s)
    for n in range(1, 5):
        s = re.sub(r"<h%d\b[^>]*>([\s\S]*?)</h%d>" % (n, n), lambda m: "\n\n" + "#" * n + " " + m.group(1) + "\n", s)
    s = re.sub(r'<a\b[^>]*href="([^"]+)"[^>]*>([\s\S]*?)</a>',
               lambda m: "[" + m.group(2) + "](" + (SITE + m.group(1) if m.group(1).startswith("/") else m.group(1)) + ")", s)
    s = re.sub(r"<code>(.*?)</code>", r"`\1`", s)
    s = re.sub(r"<(?:b|strong)>(.*?)</(?:b|strong)>", r"**\1**", s)
    s = s.replace("<li", "\n- <li").replace("<tr", "\n| <tr")
    s = re.sub(r"</t[dh]>", " | ", s)
    s = re.sub(r"</(?:p|div|figure|ul|ol|table|section)>", "\n\n", s)
    s = html.unescape(re.sub(r"<[^>]+>", "", s))
    # Markup indentation goes; code blocks, the odd parts of the split, keep theirs.
    parts = s.split("```")
    parts[::2] = [re.sub(r"^[ \t]+|[ \t]+$", "", part, flags=re.M) for part in parts[::2]]
    return re.sub(r"\n{3,}", "\n\n", "```".join(parts)).strip()


def llms(pages):
    lines = ["# Implementator", "", "> " + SUMMARY, "",
             "It runs in Claude Code and Codex CLI and is delivered through the Agensi store over MCP, so nothing is "
             "installed. Everything it writes goes into a separate notes repo that belongs to the user. Tested on "
             "Windows on a small Node project; Linux, macOS and other agents are not tested yet.", "", "## Docs", ""]
    lines += ["- [" + title + "](" + page_url(slug) + "): " + META[slug][1] for slug, title in PAGES]
    lines += ["", "## Optional", "", "- [Full text of the site](" + SITE + "/llms-full.txt)",
              "- [Agensi store](" + CREATOR + ")", ""]
    full = ["# Implementator", "", "> " + SUMMARY, ""]
    for slug in ["index"] + [s for s, _ in PAGES]:
        full += ["", "---", "", "Source: " + page_url(slug), "", to_text(pages[slug])]
    return "\n".join(lines), "\n".join(full) + "\n"


def sitemap():
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
           'xmlns:video="http://www.google.com/schemas/sitemap-video/1.1">']
    for slug in ["index"] + [s for s, _ in PAGES]:
        out.append("<url><loc>" + page_url(slug) + "</loc><lastmod>" + UPDATED + "</lastmod>")
        if slug == "videos":
            for k, (t, n, s) in VIDEOS.items():
                out.append("<video:video><video:thumbnail_loc>" + SITE + "/img/posters/" + k + ".jpg</video:thumbnail_loc>"
                           "<video:title>" + html.escape(t) + "</video:title><video:description>" + html.escape(n)
                           + "</video:description><video:content_loc>" + SITE + "/videos/" + k
                           + ".webm</video:content_loc><video:duration>" + str(s) + "</video:duration></video:video>")
        out.append("</url>")
    out.append("</urlset>")
    return "\n".join(out) + "\n"


def robots():
    lines = ["# Search engines and AI answer engines are welcome here.", ""]
    lines += ["User-agent: " + bot for bot in CRAWLERS]
    lines += ["Allow: /", "", "User-agent: *", "Allow: /", "", "Sitemap: " + SITE + "/sitemap.xml", ""]
    return "\n".join(lines)


def build():
    schemas, errors = load_schemas(IMPL)
    if errors:
        raise SystemExit("cannot read the schema: " + "; ".join(errors))
    spec = cfg_core.settings_spec(schemas)
    text = json.loads(read(SRC, "settings.json"))
    layout = read(SRC, "layout.html")
    rev = stamp()
    files = {"base.css": read(SRC, "base.css"), "style.css": read(SRC, "style.css"), "home.css": read(SRC, "home.css"),
             "home.js": read(SRC, "home.js"),
             ".nojekyll": "", "_headers": SECURITY_HEADERS, "CNAME": DOMAIN + "\n", "robots.txt": robots(),
             "sitemap.xml": sitemap(), INDEXNOW_KEY + ".txt": INDEXNOW_KEY + "\n",
             ".well-known/security.txt": "Contact: " + CREATOR + "\nExpires: 2027-11-07T00:00:00.000Z\n"
             "Preferred-Languages: en, pl\nCanonical: " + SITE + "/.well-known/security.txt\n",
             "site.webmanifest": json.dumps({"name": "Implementator", "short_name": "Implementator", "start_url": "/",
                                             "display": "standalone", "background_color": "#0b0d12",
                                             "theme_color": "#0b0d12", "icons": [
                                                 {"src": "/img/icon-192.png", "sizes": "192x192", "type": "image/png"},
                                                 {"src": "/img/icon-512.png", "sizes": "512x512", "type": "image/png"}]},
                                            indent=1) + "\n"}
    pages = {}
    counts = {"{{n-settings}}": str(len(spec)),
              "{{n-presets}}": str(len([f for f in os.listdir(os.path.join(IMPL, ".claude", "skills", "configure", "presets"))
                                        if f.endswith(".json")]))}
    home = read(SRC, "home.html").replace("{{rev}}", rev)
    for k, v in counts.items():
        home = home.replace(k, v)
    files["index.html"] = rooted(home.replace("{{updated}}", UPDATED_TEXT).replace("{{updated-iso}}", UPDATED)
                                 .replace("{{head}}", head("index", home_ld(home))))
    pages["index"] = re.search(r"<main[\s\S]*</main>", files["index.html"]).group(0)
    for slug, title in PAGES:
        body = read(SRC, "pages", slug + ".html")
        body = films(body.replace("{{settings}}", settings_tables(spec, text))
                     .replace("{{stages}}", stage_table(spec, text))
                     .replace("{{presets}}", presets_table()))
        current = ' aria-current="page"'
        pages[slug] = rooted(body)
        files[slug + ".html"] = rooted(layout.replace("{{head}}", head(slug, doc_ld(slug, body))).replace("{{nav}}", nav(slug))
                                       .replace("{{body}}", body).replace("{{pager}}", pager(slug)).replace("{{rev}}", rev)
                                       .replace("{{updated}}", UPDATED_TEXT).replace("{{updated-iso}}", UPDATED)
                                       .replace("{{bar-videos}}", current if slug == "videos" else "")
                                       .replace("{{bar-docs}}", "" if slug == "videos" else current))
    files["404.html"] = rooted(read(SRC, "404.html").replace("{{head}}", head(
        "index", [], ("Page not found - Implementator", "This page does not exist. Start from the Implementator home page."))))
    files["llms.txt"], files["llms-full.txt"] = llms(pages)
    return files, spec, text


def search_problems(name, page):
    out = []
    title = re.search(r"<title>(.*?)</title>", page).group(1)
    description = re.search(r'<meta name="description" content="([^"]*)"', page).group(1)
    if len(html.unescape(title)) > 60:
        out.append(name + " title is over 60 characters: " + title)
    if name != "404.html" and not 90 <= len(html.unescape(description)) <= 160:
        out.append(name + " description is " + str(len(html.unescape(description))) + " characters, not 90-160")
    if len(re.findall(r"<h1\b", page)) != 1:
        out.append(name + " does not have exactly one h1")
    if re.search(r"<h[1-6]\b[^>]*></h[1-6]>", page):
        out.append(name + " has an empty heading")
    out += [name + " has an image with no alt: " + i for i in re.findall(r"<img\b(?![^>]*\balt=)[^>]*>", page)]
    out += [name + " has an image with no size: " + i for i in re.findall(r"<img\b(?![^>]*\bwidth=)[^>]*>", page)]
    if re.search(r'\sstyle="|\son[a-z]+="', page):
        out.append(name + " has inline style or script, which the CSP refuses")
    if re.search(r"<script(?![^>]*(?:\bsrc=|application/ld\+json))", page):
        out.append(name + " has an inline script, which the CSP refuses")
    for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>', page, re.S):
        try:
            json.loads(block)
        except ValueError as e:
            out.append(name + " has invalid JSON-LD: " + str(e))
    return out


def problems(files, spec, text):
    out = []
    forbidden = forbidden_words()
    covered = {k for g in text["groups"] for k in g["keys"]}
    for key in covered - set(spec):
        out.append("settings.json describes a setting that no longer exists: " + key)
    missing = [k for k in spec if k not in covered and not k.startswith("orchestration.stages.")]
    out += ["no text for setting: " + k for k in missing]
    stages = {k.split(".")[2] for k in spec if k.startswith("orchestration.stages.")}
    out += ["no text for stage: " + s for s in stages ^ set(text["stages"])]
    for name, content in files.items():
        low = content.lower()
        out += [name + " uses a forbidden word: " + w for w in forbidden if w in low]
        if not name.endswith(".html"):
            continue
        for src in re.findall(r'(?:src|poster)="([^"]+)"', content):
            src = src.lstrip("/")
            if not re.match(r"https?:|data:", src) and src not in files and not os.path.isfile(os.path.join(OUT, src)):
                out.append(name + " uses a missing file: " + src)
        for href in re.findall(r'href="([^"]+)"', content):
            if re.match(r"https?:|mailto:", href):
                continue
            target, _, anchor = href.partition("#")
            target = name if href.startswith("#") else target.lstrip("/") or "index.html"
            if target + ".html" in files:
                target += ".html"
            if target not in files and not os.path.isfile(os.path.join(OUT, target)):
                out.append(name + " links to a missing file: " + href)
            elif anchor and target in files and 'id="' + anchor + '"' not in files[target]:
                out.append(name + " links to a missing anchor: " + href)
        out += search_problems(name, content)
    titles = [re.search(r"<title>(.*?)</title>", c).group(1) for n, c in files.items() if n.endswith(".html")]
    out += ["two pages share the title: " + t for t in set(titles) if titles.count(t) > 1]
    for name, content in files.items():
        path = os.path.join(OUT, name)
        if not os.path.isfile(path) or read(path) != content:
            out.append("docs/ is stale: " + name)
    return out


def main(argv):
    files, spec, text = build()
    if "--check" in argv:
        found = problems(files, spec, text)
        for p in found:
            print("FAIL " + p)
        print(("FAIL " if found else "PASS ") + str(len(files)) + " files, " + str(len(spec)) + " settings")
        return 1 if found else 0
    os.makedirs(OUT, exist_ok=True)
    for name in os.listdir(OUT):
        path = os.path.join(OUT, name)
        if os.path.isfile(path) and name not in KEEP:
            os.remove(path)
    for name, content in files.items():
        path = os.path.join(OUT, *name.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
    print("built " + str(len(files)) + " files into docs/")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
