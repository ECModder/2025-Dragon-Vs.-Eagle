#!/usr/bin/env python3
# DvE - party names of every country, for the politics panel.
#
# The game has no loc command for "the name of the party of ideology X of this
# country", so this script collects the names and writes two files:
#   common/scripted_localisation/DVE_party_names.txt
#       [DVE_PN_<group>]  name of that party for the current country scope
#       [DVE_PR1..5]      name of the k-th most popular party (DVE_pt_r<k>)
#   localisation/english/DVE_party_names_l_english.yml
#       the texts: DVE_PN_<TAG>_<group> and DVE_PN_generic_<group>
#
# Sources, for the 14 DvE ideology groups only (first one that has a usable
# name wins):
#   1. history/countries/*.txt   set_party_name = { ideology = G name = ... }
#      (a bare name is a loc key and is looked up in the mod, then in vanilla)
#   2. localisation/english/*.yml   <TAG>_<group>_party
#   3. a generic name of the group ("Liberals")
# Empty names and "no_party" are skipped. Every name is cleaned so that it
# cannot break a loc file (quotes, $, [ ], colour codes, ...).
#
#   python3 tools/dve_party_names.py            write both files, print a report
#   python3 tools/dve_party_names.py --check    write nothing, exit 1 if they are stale
#   python3 tools/dve_party_names.py --show ITA print the 14 names of one tag
#   options: --quiet (summary only), --mod DIR, --vanilla DIR|none
#
# Run it again after editing set_party_name lines or <TAG>_<group>_party keys.
# Names set at run time (set_party_name in focuses, events, decisions) are not
# seen: the panel shows the names of the start of the game.
import argparse, difflib, glob, os, re, sys, unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VANILLA = "/Volumes/SSD GAL/SteamLibrary/steamapps/common/Hearts of Iron IV"

HISTORY = "history/countries"
LOC_DIR = "localisation/english"
OUT_SLOC = "common/scripted_localisation/DVE_party_names.txt"
OUT_LOC = "localisation/english/DVE_party_names_l_english.yml"

# Fixed order: index 0..13 is the index used by DVE_pt_r<k>.
GROUPS = [
    "totalitarian_socialism", "authoritarian_socialism", "vanguard_socialism",
    "revolutionary_socialism", "progressive", "liberal", "centrist",
    "conservative", "reactionary", "authoritarianism", "autocracy",
    "absolutism", "ultranationalism", "fundamentalism",
]
# Plural nouns of the ideology names in DVE_ideology_groups_l_english.yml
# (progressive is shown as Reformist Socialism in this mod).
GENERIC = {
    "totalitarian_socialism": "Totalitarian Socialists",
    "authoritarian_socialism": "Authoritarian Socialists",
    "vanguard_socialism": "Vanguard Socialists",
    "revolutionary_socialism": "Revolutionary Socialists",
    "progressive": "Reformist Socialists",
    "liberal": "Liberals",
    "centrist": "Centrists",
    "conservative": "Conservatives",
    "reactionary": "Reactionaries",
    "authoritarianism": "Authoritarians",
    "autocracy": "Autocrats",
    "absolutism": "Absolutists",
    "ultranationalism": "Ultranationalists",
    "fundamentalism": "Fundamentalists",
}
VANILLA_GROUPS = {"fascism", "communism", "democratic", "neutrality"}
RANKS = 5               # DVE_PR1 .. DVE_PR5
MAXLEN = 64             # longest name kept (the longest real one is 47)
PREFIX = "DVE_PN_"

TAG_RE = re.compile(r"^[A-Z0-9]{3}$")
FILE_TAG_RE = re.compile(r"^([A-Z0-9]{3})(?=[\s\-.]|$)")
LOC_LINE_RE = re.compile(r"^[ \t]*([^\s:#\"]+):\d*[ \t]*(.*?)[ \t]*$")
PARTY_KEY_RE = re.compile(r"^([A-Z0-9]{3})_(.+)_party$")
FIELD_RE = re.compile(r'(\w+)\s*=\s*(?:"([^"]*)"|([^\s{}"]+))')


# ---------------------------------------------------------------- cleaning

def sanitize(raw):
    """Make a party name safe for a loc value. Returns (text, reasons)."""
    why = []

    def sub(pattern, repl, s, reason, flags=0):
        t = re.sub(pattern, repl, s, flags=flags)
        if t != s and reason not in why:
            why.append(reason)
        return t

    s = unicodedata.normalize("NFC", raw)
    out = []
    for c in s:
        cat = unicodedata.category(c)
        if cat in ("Zs", "Zl", "Zp") or c in "\t\r\n":
            out.append(" ")
        elif cat in ("Cc", "Cf", "Cs", "Co", "Cn") or c == "\ufffd":
            if "control character" not in why:
                why.append("control character")
        else:
            out.append(c)
    s = "".join(out)
    s = sub(r"\\[nrt]", " ", s, "escape sequence")
    s = sub("\u00a7.?", "", s, "colour code")          # section sign + 1 char
    s = sub("\u00a3\\S*", "", s, "icon")                # pound sign + name
    s = sub(r"\[\s*", "(", s, "square brackets")
    s = sub(r"\s*\]\s*", ") ", s, "square brackets")
    s = sub('"', "'", s, "double quote")
    s = sub(r"[\\$%#{}\u00a7\u00a3]", "", s, "special character")
    t = re.sub(r"\s+", " ", s).strip()
    if t != s and not why:
        why.append("whitespace")
    s = t
    if len(s) > MAXLEN:
        cut = s[:MAXLEN]
        if " " in cut:
            cut = cut[:cut.rfind(" ")]
        s = cut.rstrip(" ,;:-(")
        why.append("too long")
    if s != raw and not why:
        why.append("normalised")
    return s, why


def usable(text):
    """A name is usable if it has a letter or digit and is not no_party."""
    t = text.strip()
    if not t or t.lower() == "no_party":
        return False
    return any(c.isalnum() for c in t)


def mixed_script(text):
    """True if one word mixes Latin and Cyrillic/Greek letters."""
    for word in re.findall(r"\w+", text):
        scripts = set()
        for c in word:
            if c.isalpha():
                n = unicodedata.name(c, "")
                scripts.add(n.split(" ")[0])
        if len(scripts & {"LATIN", "CYRILLIC", "GREEK"}) > 1:
            return True
    return False


# ----------------------------------------------------------------- sources

def read_text(path):
    with open(path, encoding="utf-8-sig", errors="replace") as f:
        return f.read()


def strip_comments(text):
    """Remove # comments that are outside of double quotes."""
    lines = []
    for line in text.split("\n"):
        res, q = [], False
        for ch in line:
            if ch == '"':
                q = not q
            if ch == "#" and not q:
                break
            res.append(ch)
        lines.append("".join(res))
    return "\n".join(lines)


def party_blocks(text):
    """Yield the body of every set_party_name = { ... } (quote aware)."""
    for m in re.finditer(r"\bset_party_name\s*=\s*\{", text):
        i, depth, q = m.end(), 1, False
        while i < len(text) and depth:
            c = text[i]
            if c == '"':
                q = not q
            elif not q:
                if c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
            i += 1
        yield text[m.end():i - 1]


def loc_value(rest):
    """Text between the first and the last double quote, or None."""
    a, b = rest.find('"'), rest.rfind('"')
    if a < 0 or b <= a:
        return None
    return rest[a + 1:b]


class Sources:
    pass


def scan(mod):
    src = Sources()
    src.warn = []
    # history: (tag, group) -> dict(name=(quoted, text) or None, long=...)
    src.declared = {}
    src.tags = {}               # tag -> file name
    src.ignored = {}            # group -> count (not one of the 14)
    src.suspect_groups = {}     # spelling near one of the 14
    src.duplicates = []
    files = sorted(glob.glob(os.path.join(mod, HISTORY, "*.txt")))
    for path in files:
        base = os.path.basename(path)
        m = FILE_TAG_RE.match(base)
        if not m:
            src.warn.append("history file without a tag: " + base)
            continue
        tag = m.group(1)
        if not re.match(r"^[A-Z0-9]{3} - .+\.txt$", base):
            src.warn.append("history file name is not 'TAG - Name.txt': " + base)
        src.tags[tag] = base
        text = strip_comments(read_text(path))
        for body in party_blocks(text):
            f = {}
            for km in FIELD_RE.finditer(body):
                key = km.group(1)
                if key in f:
                    continue
                if km.group(2) is not None:
                    f[key] = (True, km.group(2))
                else:
                    f[key] = (False, km.group(3))
            if "ideology" not in f:
                src.warn.append("%s: set_party_name without ideology" % tag)
                continue
            g = f["ideology"][1]
            if g not in GROUPS:
                src.ignored[g] = src.ignored.get(g, 0) + 1
                if g not in VANILLA_GROUPS:
                    near = difflib.get_close_matches(g, GROUPS, 1, 0.8)
                    if near:
                        src.suspect_groups[(tag, g)] = near[0]
                continue
            if (tag, g) in src.declared:
                src.duplicates.append((tag, g))
            src.declared[(tag, g)] = {"name": f.get("name"), "long": f.get("long_name")}

    # localisation: every key (for lookups) and the <TAG>_<group>_party keys
    src.loc_all = {}            # key -> raw text after the colon
    src.loc_party = {}          # (tag, group) -> (file, raw rest)
    src.loc_files = 0
    src.loc_tag_not_in_history = set()
    mine = os.path.basename(OUT_LOC)
    for path in sorted(glob.glob(os.path.join(mod, LOC_DIR, "*.yml"))):
        base = os.path.basename(path)
        if base == mine:
            continue                    # never read our own output
        src.loc_files += 1
        for n, line in enumerate(read_text(path).split("\n"), 1):
            if not line.strip() or line.lstrip().startswith("#") or line.strip() == "l_english:":
                continue
            m = LOC_LINE_RE.match(line)
            if not m:
                continue
            key, rest = m.group(1), m.group(2)
            src.loc_all.setdefault(key, rest)
            pm = PARTY_KEY_RE.match(key)
            if not pm:
                continue
            tag, g = pm.group(1), pm.group(2)
            if g not in GROUPS:
                near = difflib.get_close_matches(g, GROUPS, 1, 0.8)
                if near:
                    src.suspect_groups[(tag, g + " (loc key %s)" % key)] = near[0]
                continue
            if (tag, g) in src.loc_party:
                src.warn.append("duplicate loc key %s (%s:%d), first one kept" % (key, base, n))
                continue
            src.loc_party[(tag, g)] = (base, rest)
    return src


def vanilla_lookup(vanilla, wanted):
    """Values of some keys in the vanilla english loc: key -> raw rest."""
    found = {}
    if not vanilla or not wanted:
        return found
    for path in sorted(glob.glob(os.path.join(vanilla, "localisation", "english", "*.yml"))):
        for line in read_text(path).split("\n"):
            if ":" not in line:
                continue
            key = line.split(":", 1)[0].strip()
            if key in wanted and key not in found:
                m = LOC_LINE_RE.match(line)
                if m:
                    found[key] = m.group(2)
    return found


# ----------------------------------------------------------------- resolve

def resolve(src, vanilla):
    """Decide the name of every (tag, group). Fills src.names and the report."""
    rep = Sources()
    rep.changed = []            # (tag, group, raw, clean, why)
    rep.refs = []               # (tag, group, key, text)
    rep.unresolved = []         # (tag, group, key)
    rep.skipped = []            # (tag, group, why)
    rep.long_only = []
    rep.mixed = []
    rep.lookalike = []          # literal name that is also a loc key
    rep.from_history = 0
    rep.from_loc = 0
    rep.loc_overridden = []     # loc name hidden by a different history name
    names = {}                  # (tag, group) -> clean text

    # pass 1: unquoted names are loc keys
    refs = {}
    need = set()
    for (tag, g), d in src.declared.items():
        n = d["name"]
        if n and not n[0]:
            refs[(tag, g)] = n[1]
            if n[1] not in src.loc_all:
                need.add(n[1])
    vloc = vanilla_lookup(vanilla, need)
    # literal names that are also loc keys (the game may show the loc text)
    lits = {d["name"][1] for d in src.declared.values() if d["name"] and d["name"][0]}
    vlit = vanilla_lookup(vanilla, lits - set(src.loc_all))

    all_tags = sorted(set(t for t, _ in src.declared) | set(t for t, _ in src.loc_party) | set(src.tags))
    for tag in all_tags:
        if tag not in src.tags:
            src.loc_tag_not_in_history.add(tag)
        for g in GROUPS:
            chosen = None
            d = src.declared.get((tag, g))
            if d:
                n, ln = d["name"], d["long"]
                raw = None
                if n is None:
                    rep.skipped.append((tag, g, "set_party_name without name"))
                elif n[0]:
                    raw = n[1]
                    if raw in src.loc_all or raw in vlit:
                        rep.lookalike.append((tag, g, raw))
                else:
                    ref = n[1]
                    rest = src.loc_all.get(ref, vloc.get(ref))
                    val = loc_value(rest) if rest is not None else None
                    if val is None:
                        rep.unresolved.append((tag, g, ref))
                    else:
                        raw = val
                        rep.refs.append((tag, g, ref, val))
                if raw is not None:
                    if mixed_script(raw):
                        rep.mixed.append((tag, g, raw))
                    text, why = sanitize(raw)
                    if usable(raw) and usable(text):
                        if why:
                            rep.changed.append((tag, g, raw, text, why))
                        chosen = text
                        rep.from_history += 1
                    else:
                        rep.skipped.append((tag, g, "history name '%s'" % raw.strip()))
                        if ln and ln[0] and usable(sanitize(ln[1])[0]):
                            rep.long_only.append((tag, g, ln[1]))
            lp = src.loc_party.get((tag, g))
            if lp:
                val = loc_value(lp[1])
                if val is None:
                    src.warn.append("%s_%s_party in %s: no closing quote, ignored" % (tag, g, lp[0]))
                else:
                    text, why = sanitize(val)
                    if usable(val) and usable(text):
                        if chosen is None:
                            if mixed_script(val):
                                rep.mixed.append((tag, g, val))
                            if why:
                                rep.changed.append((tag, g, val, text, why))
                            chosen = text
                            rep.from_loc += 1
                        elif chosen != text:
                            rep.loc_overridden.append((tag, g, text, chosen))
                    elif val.strip():
                        rep.skipped.append((tag, g, "loc name '%s'" % val.strip()))
            if chosen is not None:
                names[(tag, g)] = chosen
    src.names = names
    src.tag_list = all_tags
    return rep


# ------------------------------------------------------------------ output

def build_sloc(names, tags):
    out = [
        "# DvE - party names for the politics panel.",
        "# Generated by tools/dve_party_names.py from history/countries and the party loc keys.",
        "# Do not edit by hand: run the script again.",
        "#   [DVE_PN_<group>]   name of that party for the country scope it is called from",
        "#   [DVE_PR1] .. [DVE_PR5]   name of the k-th most popular party (variable DVE_pt_r<k>)",
        "",
    ]
    for g in GROUPS:
        out.append("defined_text = {")
        out.append("\tname = %s%s" % (PREFIX, g))
        for tag in tags:
            if (tag, g) in names:
                out.append("\ttext = { trigger = { tag = %s } localization_key = %s%s_%s }" % (tag, PREFIX, tag, g))
        out.append("\ttext = { localization_key = %sgeneric_%s }" % (PREFIX, g))
        out.append("}")
        out.append("")
    for k in range(1, RANKS + 1):
        out.append("defined_text = {")
        out.append("\tname = DVE_PR%d" % k)
        for i, g in enumerate(GROUPS):
            out.append("\ttext = { trigger = { check_variable = { DVE_pt_r%d = %d } } localization_key = \"[%s%s]\" }" % (k, i, PREFIX, g))
        out.append("}")
        out.append("")
    return "\n".join(out)


def build_yml(names, tags):
    out = ["l_english:"]
    for g in GROUPS:
        out.append(' %sgeneric_%s:0 "%s"' % (PREFIX, g, GENERIC[g]))
    for tag in tags:
        for g in GROUPS:
            if (tag, g) in names:
                out.append(' %s%s_%s:0 "%s"' % (PREFIX, tag, g, names[(tag, g)]))
    return "\ufeff" + "\n".join(out) + "\n"


# ------------------------------------------------------------------ verify

BAD_CHARS = set('"\\$%#[]{}\u00a7\u00a3\ufffd')


def verify(sloc, yml):
    """Self-check of the generated texts. Returns a list of problems."""
    bad = []
    if not yml.startswith("\ufeffl_english:\n"):
        bad.append("yml: BOM / l_english: header missing")
    lines = yml.split("\n")
    if lines[-1] != "":
        bad.append("yml: no final newline")
    keys = {}
    line_re = re.compile(r'^ (%s[A-Za-z0-9_]+):0 "([^"]+)"$' % PREFIX)
    for n, line in enumerate(lines[1:-1], 2):
        m = line_re.match(line)
        if not m or line.count('"') != 2:
            bad.append("yml line %d has a wrong shape: %r" % (n, line[:80]))
            continue
        key, val = m.group(1), m.group(2)
        if key in keys:
            bad.append("yml: duplicate key " + key)
        keys[key] = val
        if any(c in BAD_CHARS for c in val):
            bad.append("yml line %d: forbidden character in %r" % (n, val))
        if val != val.strip() or "  " in val or not usable(val):
            bad.append("yml line %d: bad spacing or empty name %r" % (n, val))
        if len(val) > MAXLEN:
            bad.append("yml line %d: name too long" % n)
    for g in GROUPS:
        if "%sgeneric_%s" % (PREFIX, g) not in keys:
            bad.append("yml: generic key missing for " + g)
    # scripted loc
    depth = 0
    for ch in sloc:
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth < 0:
                bad.append("sloc: closing brace without opening one")
                break
    if depth != 0:
        bad.append("sloc: braces are not balanced (%d)" % depth)
    if sloc.count('"') % 2:
        bad.append("sloc: odd number of double quotes")
    defs = re.findall(r"^\tname = (\S+)$", sloc, re.M)
    want = [PREFIX + g for g in GROUPS] + ["DVE_PR%d" % k for k in range(1, RANKS + 1)]
    if defs != want:
        bad.append("sloc: defined_text names are not the expected ones")
    if sloc.count("defined_text = {") != len(want):
        bad.append("sloc: wrong number of defined_text")
    used = re.findall(r"localization_key = (\S+) }", sloc)
    for k in used:
        if k.startswith('"[') and k.endswith(']"'):
            if k[2:-2] not in want:
                bad.append("sloc: nested call to unknown text " + k)
        elif k not in keys:
            bad.append("sloc: localization_key without loc text: " + k)
    unused = set(keys) - set(used)
    if unused:
        bad.append("sloc: %d loc keys are never used (first: %s)" % (len(unused), sorted(unused)[0]))
    for k in range(1, RANKS + 1):
        blk = re.search(r"name = DVE_PR%d\n(.*?)\n}" % k, sloc, re.S)
        if not blk or blk.group(1).count("check_variable") != len(GROUPS):
            bad.append("sloc: DVE_PR%d does not have %d blocks" % (k, len(GROUPS)))
    return bad


# ------------------------------------------------------------------ report

def report(src, rep, names, sloc, yml, quiet):
    p = print
    ngroups = {g: sum(1 for (t, gg) in names if gg == g) for g in GROUPS}
    tags_named = {t for (t, g) in names}
    p("Sources: %d history files (%d tags), %d loc files scanned" % (len(src.tags), len(src.tags), src.loc_files))
    p("  set_party_name of the 14 groups: %d, other groups ignored: %s" % (
        len(src.declared), ", ".join("%s %d" % kv for kv in sorted(src.ignored.items())) or "none"))
    p("  <TAG>_<group>_party loc keys: %d" % len(src.loc_party))
    p("Names: %d (tag, group) pairs = %d from history + %d from loc keys; "
      "%d tags with at least one name" % (len(names), rep.from_history, rep.from_loc, len(tags_named)))
    p("  skipped (empty / no_party / unusable): %d, bare loc-key names resolved: %d, unresolved: %d" % (
        len(rep.skipped), len(rep.refs), len(rep.unresolved)))
    p("  per group: " + ", ".join("%s %d" % (g.split("_")[0][:6], ngroups[g]) for g in GROUPS))
    longest = sorted(names.items(), key=lambda kv: -len(kv[1]))[:3]
    p("  longest names: " + "; ".join("%s %s '%s' (%d)" % (k[0], k[1], v, len(v)) for k, v in longest))

    nblocks = sum(ngroups.values())
    worst_pn = max(ngroups.values()) + 1
    panel = sum(n + 1 for n in ngroups.values())
    top5 = RANKS * (len(GROUPS) + worst_pn)
    p("Output: %s %d bytes (%d name blocks + %d fallbacks + %d dispatch blocks), %s %d bytes" % (
        OUT_SLOC, len(sloc.encode("utf-8")), nblocks, len(GROUPS), RANKS * len(GROUPS),
        OUT_LOC, len(yml.encode("utf-8"))))
    p("Cost: one [DVE_PN_<group>] scans at most %d `tag =` tests; the panel (14 names) at most %d, "
      "the top 5 box at most %d, per redraw of the text" % (worst_pn, panel, top5))

    p("Names changed by cleaning: %d" % len(rep.changed))
    shown = rep.changed if not quiet else rep.changed[:0]
    kinds = {}
    for t, g, raw, text, why in rep.changed:
        kinds[", ".join(why)] = kinds.get(", ".join(why), 0) + 1
    for k, v in sorted(kinds.items()):
        p("  %-40s %d" % (k, v))
    if not quiet:
        for t, g, raw, text, why in shown:
            p("    %s %-24s %r -> %r" % (t, g, raw, text))
    if rep.refs:
        p("Bare loc-key names resolved:")
        for t, g, ref, val in rep.refs:
            p("    %s %-24s %s -> %r" % (t, g, ref, val))
    if rep.unresolved:
        p("Bare loc-key names NOT found (mod or vanilla loc), generic/loc name used:")
        for t, g, ref in rep.unresolved:
            p("    %s %-24s %s" % (t, g, ref))
    if rep.long_only:
        p("Pairs whose name is unusable but long_name is (not used): %d" % len(rep.long_only))
    if rep.mixed:
        p("Names that mix Latin and Cyrillic/Greek letters in one word (kept):")
        for t, g, raw in rep.mixed:
            p("    %s %-24s %r" % (t, g, raw))
    if src.suspect_groups:
        p("Group names that look like a misspelling of one of the 14 (ignored):")
        for (t, g), near in sorted(src.suspect_groups.items()):
            p("    %s %s -> did you mean %s?" % (t, g, near))
    if src.duplicates:
        p("Declared twice in the same history file (last one used): %s" % ", ".join("%s/%s" % d for d in src.duplicates))
    if rep.loc_overridden and not quiet:
        p("Loc key names hidden by a different history name: %d" % len(rep.loc_overridden))
    if rep.lookalike:
        ex = ", ".join("%s %s '%s'" % x for x in rep.lookalike[:4])
        p("Note: %d literal history names are also loc keys (the game UI may show the loc text, the panel shows the literal): %s%s" % (
            len(rep.lookalike), ex, " ..." if len(rep.lookalike) > 4 else ""))
    nameless = [t for t in src.tag_list if t not in tags_named]
    p("Tags without any name (all 14 use the generic names): %d" % len(nameless))
    if nameless and not quiet:
        p("    " + " ".join(nameless))
    if src.loc_tag_not_in_history:
        p("Tags with loc names but no history file: " + " ".join(sorted(src.loc_tag_not_in_history)))
    for w in src.warn:
        p("Warning: " + w)


# -------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description="DvE party names generator")
    ap.add_argument("--check", action="store_true", help="write nothing; exit 1 if the files are stale")
    ap.add_argument("--show", metavar="TAG", help="print the names of one tag")
    ap.add_argument("--quiet", action="store_true", help="short report")
    ap.add_argument("--mod", default=ROOT, help="mod folder (default: this repository)")
    ap.add_argument("--vanilla", default=VANILLA, help="vanilla game folder, or 'none'")
    a = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")

    mod = os.path.abspath(a.mod)
    vanilla = None if a.vanilla.lower() == "none" or not os.path.isdir(a.vanilla) else a.vanilla
    src = scan(mod)
    rep = resolve(src, vanilla)
    if rep.unresolved and vanilla is None:
        src.warn.append("vanilla localisation not available: %d bare loc-key names could not be resolved, "
                        "the output can differ from a run with the game folder" % len(rep.unresolved))
    names = src.names
    tags = sorted({t for (t, g) in names})
    sloc = build_sloc(names, tags)
    yml = build_yml(names, tags)

    problems = verify(sloc, yml)
    if problems:
        print("SELF-CHECK FAILED, nothing written:")
        for b in problems[:40]:
            print("  " + b)
        return 2

    if a.show:
        t = a.show.upper()
        for g in GROUPS:
            n = names.get((t, g))
            print("%-24s %s" % (g, n if n else "[generic] " + GENERIC[g]))
        return 0

    targets = [(OUT_SLOC, sloc), (OUT_LOC, yml)]
    stale = []
    for rel, text in targets:
        path = os.path.join(mod, rel)
        data = text.encode("utf-8")
        old = open(path, "rb").read() if os.path.exists(path) else None
        if old != data:
            stale.append(rel)
            if not a.check:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "wb") as f:
                    f.write(data)
    if a.check:
        if stale:
            report(src, rep, names, sloc, yml, True)
            print("STALE (run tools/dve_party_names.py): " + ", ".join(stale))
            return 1
        print("Up to date (%d names, %d tags)." % (len(names), len(tags)))
        for w in src.warn:
            print("Warning: " + w)
        return 0
    report(src, rep, names, sloc, yml, a.quiet)
    print(("Written: " + ", ".join(stale)) if stale else "Both files were already up to date.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
