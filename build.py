#!/usr/bin/env python3
"""Build the Implementator documentation into docs/, which GitHub Pages serves.

The prose lives in src/. The settings tables and the presets are generated from the implementator
repo itself, so a value on the Configuration page is the value the pack ships.

Usage:
  python build.py            build into docs/
  python build.py --check    build in memory and fail on anything below; writes nothing

--check fails when docs/ is stale, a setting has no text here (or the text names one that is gone), a
page links to a file or anchor that does not exist, or a page uses a word that must not appear.
The source repo is ../implementator, or IMPLEMENTATOR_REPO.
"""
import html
import json
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "src")
OUT = os.path.join(ROOT, "docs")
IMPL = os.environ.get("IMPLEMENTATOR_REPO") or os.path.join(os.path.dirname(ROOT), "implementator")

PAGES = [("index", "Overview"), ("get-started", "Get started"), ("first-project", "Your first project"),
         ("configuration", "Configuration"), ("daily-use", "Daily use"), ("troubleshooting", "Troubleshooting")]


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


def stamp():
    rev = subprocess.run(["git", "-C", IMPL, "rev-parse", "--short", "HEAD"], capture_output=True, text=True)
    return rev.stdout.strip() or "unknown"


def nav(current):
    items = []
    for slug, title in PAGES:
        here = ' aria-current="page"' if slug == current else ""
        items.append('<li><a href="' + slug + '.html"' + here + ">" + title + "</a></li>")
    return "\n".join(items)


def build():
    schemas, errors = load_schemas(IMPL)
    if errors:
        raise SystemExit("cannot read the schema: " + "; ".join(errors))
    spec = cfg_core.settings_spec(schemas)
    text = json.loads(read(SRC, "settings.json"))
    layout = read(SRC, "layout.html")
    rev = stamp()
    files = {"style.css": read(SRC, "style.css"), ".nojekyll": ""}
    for slug, title in PAGES:
        body = read(SRC, "pages", slug + ".html")
        body = (body.replace("{{settings}}", settings_tables(spec, text))
                .replace("{{stages}}", stage_table(spec, text))
                .replace("{{presets}}", presets_table()))
        page_title = "Implementator" if slug == "index" else title + " - Implementator"
        files[slug + ".html"] = (layout.replace("{{title}}", page_title).replace("{{nav}}", nav(slug))
                                 .replace("{{body}}", body).replace("{{rev}}", rev))
    return files, spec, text


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
        if not name.endswith(".html"):
            continue
        low = content.lower()
        out += [name + " uses a forbidden word: " + w for w in forbidden if w in low]
        for href in re.findall(r'href="([^"]+)"', content):
            if re.match(r"https?:|mailto:", href):
                continue
            target, _, anchor = href.partition("#")
            target = target or name
            if target not in files:
                out.append(name + " links to a missing file: " + href)
            elif anchor and 'id="' + anchor + '"' not in files[target]:
                out.append(name + " links to a missing anchor: " + href)
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
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT)
    for name, content in files.items():
        with open(os.path.join(OUT, name), "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
    print("built " + str(len(files)) + " files into docs/")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
