#!/usr/bin/env python3
"""
SML Page Builder tool (skill v1.0.0, registry schema 3.0). Site-agnostic.

Registry (per site, in Webflow Agent Instructions):
  sml-page-builder-registry/SKILL.md            root (generated)
  sml-page-builder-registry/data/selection.md   component catalogue (generated)
  sml-page-builder-registry/data/knowledge.md   site knowledge (curated by the agent)
Legacy `sml-marketer-registry/` (schema 2.x) is readable and migrated on refresh.

Subcommands
  registry-build  --components F --site-id ID --site-name N --mcp-version X --out-dir D
                  [--existing-paths P,...]           -> selection + write/cleanup calls
  selection-load  --readback F [--site-id ID]        validate a saved read of selection.md
  registry-verify --readback F --expected out/selection.json   stored == generated (digest + every entry)
  knowledge-build --in F --site-id ID --out F [--exists] [--selection F] [--reviewed IDS]
  starter         --pages F...                       Starter page candidates
  starter-check   --tree F                           wrapper / navigation / hero / footer of a Starter tree
  links           --pages F... --locales JSON --href H [H...]   (--out F saves the map for writes-build)
  select-context  --selection F --knowledge F [--ids IDS]   merged selection cards + knowledge health
  exec-needs      --selected IDS --details F... [--trees F...] [--variants F] [--resolve PROPIDS]
  exec-build      --selected IDS --details F... [--trees F...] [--variants F] [--resolve PROPIDS|all] --out F
  writes-build    --exec F --spec F --out F [--links F] [--report F] [--plan]
                  (--plan: before any Webflow change; no call, elements optional, per-section status)
                  validated set_component_instance_prop_values actions + review checks
                  (leftover default text, copy lint, card balance) + editorial report
  ids             --result F                         element IDs / errors from insertion results
  verify-page     --tree F --call F [--expect JSON] [--exec F]  order, singletons, every written value,
                  and (with --exec) default text still visible on the live page

MCP results are read from files saved by the harness (large results) or written
verbatim by the agent (small inline results). Files may hold concatenated JSON
objects or the harness [{"type":"text","text":...}] wrapper.
"""

import argparse
import collections
import datetime
import difflib
import hashlib
import json
import os
import re
import sys

SKILL_NAME = "sml-page-builder"
SKILL_VERSION = "1.0.0"
REGISTRY = "sml-page-builder-registry"
REGISTRY_NAME = "SML Page Builder Registry"   # display name (root title and descriptions)
LEGACY_REGISTRIES = ("sml-marketer-registry",)
SCHEMA = "3.0"
READABLE_MAJORS = (2, 3)
MAX_BODY = 256 * 1024

def paths(reg):
    return {"root": f"{reg}/SKILL.md", "selection": f"{reg}/data/selection.md",
            "knowledge": f"{reg}/data/knowledge.md"}

P = paths(REGISTRY)

# `Section — X` / `Item — X`; tolerant of NBSP and missing space after the em dash.
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
NAME = re.compile(r"^(Section|Item)\s+—\s*\S")
NEAR = re.compile(r"^(Section|Item)\s*[–‒−-]+\s*\S|^(Section|Item)—", re.I)
CONTENT_TYPES = {"textContent", "string", "richText", "image", "video", "link",
                 "selectedItems", "filter", "number", "headingTag"}
CMS_TYPES = {"selectedItems", "filter"}
TEXT_TYPES = {"textContent", "string", "richText"}
NUMBERED = re.compile(r"^(.*?\S)\s*(\d+)$")
VIS = re.compile(r"\s*—\s*Visibility$|^Visibility$|^Show$", re.I)


# ------------------------------------------------------------------- io

def load_objects(path):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    try:
        data = json.loads(text)
        if isinstance(data, list) and data and isinstance(data[0], dict) \
                and set(data[0]) == {"type", "text"}:
            texts = [d["text"] for d in data]
        else:
            return data if isinstance(data, list) else [data]
    except json.JSONDecodeError:
        texts = [text]
    out, dec = [], json.JSONDecoder()
    for t in texts:
        i = 0
        while i < len(t):
            while i < len(t) and t[i].isspace():
                i += 1
            if i >= len(t):
                break
            if t[i] not in "[{":          # "[session_id issued ...]" style preambles
                nl = t.find("\n", i)
                i = len(t) if nl < 0 else nl + 1
                continue
            try:
                obj, i = dec.raw_decode(t, i)
            except json.JSONDecodeError:
                nl = t.find("\n", i)
                i = len(t) if nl < 0 else nl + 1
                continue
            out.append(obj)
    return out


def walk(node):
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from walk(v)


def components_from(paths_):
    out = {}
    for p in paths_ or []:
        for d in walk(load_objects(p)):
            if isinstance(d.get("id"), str) and isinstance(d.get("name"), str) \
                    and (isinstance(d.get("props"), list) or isinstance(d.get("variants"), list)) \
                    and "propId" not in d:
                prev = out.get(d["id"], {})
                out[d["id"]] = {**prev, **d}
    return out


def trees_from(paths_):
    trees = {}
    for p in paths_ or []:
        for d in walk(load_objects(p)):
            if d.get("action") == "get_all_elements" and isinstance(d.get("label"), str):
                res = d.get("result") or []
                ok = res and isinstance(res[0], dict) and res[0].get("status") == "success"
                data = res[0].get("data") if ok else None
                # key by the tree's own component id (labels are free text); fall back to a
                # component id found in the label or message for failed reads
                cid = ((data or {}).get("id") or {}).get("component")
                if not cid:
                    m = UUID.search(d["label"] + " " + str((res[0] if res else {}).get("message", "")))
                    cid = m.group(0) if m else d["label"]
                trees[cid] = data
    return trees


def kind_of(name):
    m = NAME.match(name)
    return m.group(1).lower() if m else None


def key_of(p):
    return f'{p["group"]}.{p["name"]}' if p.get("group") else p["name"]


def split_ids(s):
    return [x for x in re.split(r"[,\s]+", s or "") if x]


def now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def dump(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=1))


# ------------------------------------------------------------ registry

def label(name):
    n = VIS.sub("", name).strip(" —")
    return re.sub(r"\s*—\s*", " ", n).lower()


def summarize(comp):
    groups = collections.OrderedDict()
    for p in comp.get("props") or []:
        groups.setdefault(p.get("group") or "", []).append(p)

    def fields(props):
        seen = collections.OrderedDict()
        for p in props:
            t = p.get("type")
            if (t in CONTENT_TYPES or t == "slot") and (p.get("group") or t != "string"):
                n = re.sub(r"\b\d+\b", "N", label(p["name"]) or t)
                if t == "number":
                    n += f" (number, default {p.get('defaultValue')})"
                seen[n] = seen.get(n, 0) + 1
        return [f"{n} ×{k}" if "N" in n.split() and k > 1 else n for n, k in seen.items()]

    content, repeat = [], collections.OrderedDict()
    for g, props in groups.items():
        m = NUMBERED.match(g) if g else None
        if m:
            repeat.setdefault(m.group(1), []).append((int(m.group(2)), props))
            continue
        f = fields(props)
        if f:
            content.append(f"{g or 'Main'}: {', '.join(f)}")
    capacity, fixed = {}, []
    for base, members in repeat.items():
        f = []
        for _, props in members:
            for x in fields(props):
                if x not in f:
                    f.append(x)
        own_vis = lambda p: p["name"] in ("Visibility", "Show") and p.get("type") == "boolean"
        hideable = sum(1 for _, props in members if any(own_vis(p) for p in props))
        hidden = sum(1 for _, props in members
                     if any(own_vis(p) and p.get("defaultValue") is False for p in props))
        n = len(members)
        cap = {"max": n}
        if hidden:
            cap["shownByDefault"] = n - hidden
        capacity[base] = cap
        if n > 1 and not hideable and not any(p.get("type") == "number" for p in comp.get("props") or []):
            cond = any(p["name"] in ("Visibility", "Show") and p.get("type") == "visibility"
                       for _, props in members for p in props)
            fixed.append((base, cond))
        if f:
            content.append(f"{base} ×{n}: {', '.join(f)}")

    toggles = sorted({label(p["name"]) or p["group"].lower() for p in comp.get("props") or []
                      if p.get("type") in ("boolean", "visibility") and VIS.search(p["name"])
                      and p.get("group") and not NUMBERED.match(p["group"])} - {""})
    options = []
    for p in comp.get("props") or []:
        if p.get("type") == "variant" and not NUMBERED.match(p.get("group") or ""):
            n = label(p["name"])
            if n not in options:
                options.append(n)
    cms_n = sum(1 for p in comp.get("props") or [] if p.get("type") in CMS_TYPES)
    slot_props = [p for p in comp.get("props") or [] if p.get("type") == "slot"]
    slots = sorted((p.get("group") or p["name"] for p in slot_props),
                   key=lambda g: [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", g)])
    warnings = []
    names = collections.Counter(p["name"] for p in slot_props)
    dup = [n for n, k in names.items() if k > 1]
    if dup:
        warnings.append(f"ambiguous-slots: {sum(names[n] for n in dup)} slots share the name "
                        f"{', '.join(repr(n) for n in dup)}; insert_in_slot only reaches the first")
    writable = [p for p in comp.get("props") or [] if p.get("type") in ("textContent", "richText", "string", "link")
                and (p.get("group") or p.get("type") != "string")]
    for g, props in groups.items():
        if any(p.get("type") in CMS_TYPES for p in props) and not any(
                p.get("type") in ("textContent", "richText", "link") for p in props):
            warnings.append(f"cms-content: '{g or 'Main'}' is filled from a CMS selection/filter that MCP cannot write")
    if comp.get("props") and not writable:
        warnings.append("no-writable-content: no text, rich text or link props; content cannot be set via MCP")
    switches = [p["name"] for p in comp.get("props") or [] if p.get("type") == "boolean"
                and re.search(r"\b(amount|number|count)\b", p["name"], re.I)]
    for base, cond in fixed:
        if switches:
            warnings.append(f"count-switch: {capacity[base]['max']} '{base}' repeats, shown count set by boolean "
                            f"{switches[0]!r}; which value shows how many is unverified")
            continue
        warnings.append(f"fixed-count: no writable per-item visibility for the {capacity[base]['max']} '{base}' repeats"
                        + (" (conditional visibility only; defaults decide what shows)" if cond
                           else "; all of them always render"))
    rec = {"content": content}
    if capacity:
        rec["capacity"] = capacity
    if slots:
        rec["slots"] = slots
    rec["cms"] = ({"status": "estimated", "min": cms_n,
                   "basis": f"{cms_n} CMS-bound props (lower bound)"} if cms_n else
                  {"status": "unknown", "basis": "no CMS-bound props; nested Collection Lists are not detectable"})
    if options:
        rec["options"] = options
    if toggles:
        rec["toggles"] = toggles
    if warnings:
        rec["warnings"] = warnings
    rec["props"] = len(comp.get("props") or [])
    return rec


def payload_md(title, doc):
    return (f"# {title}\n\n**Machine generated by `{SKILL_NAME}` v{SKILL_VERSION}. Do not edit.**\n\n"
            "```json\n" + json.dumps(doc, ensure_ascii=False, separators=(",", ":")) + "\n```\n")


def parse_payload(markdown):
    m = re.search(r"```json\n(.*?)\n```", markdown, re.S)
    if not m:
        raise ValueError("no ```json payload block")
    return json.loads(m.group(1))


def root_md(sel, size):
    return f"""# {REGISTRY_NAME}

**Machine generated by `{SKILL_NAME}` v{SKILL_VERSION}. Do not edit by hand.**

Site registry (schema `{SCHEMA}`) for SML Page Builder on {sel['site']['name']}
(`{sel['site']['id']}`). Plain-text paths on purpose:
- `{P['selection']}`: every `Section —` / `Item —` component ({size} bytes, digest `{sel['digest']}`).
- `{P['knowledge']}`: curated site knowledge (Starter page, link map, visual notes,
  Collection List status, execution dependencies). Overrides selection data.

Exact prop IDs and variant options are NOT stored; they are fetched on demand.

| Field | Value |
|---|---|
| Generated at | `{sel['generated']['at']}` |
| Sections / Items | {sel['counts'].get('section', 0)} / {sel['counts'].get('item', 0)} |

Regenerate with `refresh SML Page Builder registry` after Section or Item components change.
"""


def action(op, path, body, site_id, description=None):
    a = {"site_id": site_id, "kind": "skill", "path": path}
    if body is not None:
        a["markdown"] = body
        if description:
            a["description"] = description
    return {"label": path, f"{op}_instruction": a}


def registry_build(a):
    comps = components_from([a.components])
    out, counts, names, near = [], collections.Counter(), collections.Counter(), []
    for c in sorted(comps.values(), key=lambda c: (kind_of(c["name"]) != "section", c["name"])):
        k = kind_of(c["name"])
        if not k:
            if NEAR.match(c["name"]):
                near.append(c["name"])
            continue
        counts[k] += 1
        names[c["name"]] += 1
        out.append({"name": c["name"], "id": c["id"], "kind": k, **summarize(c)})
    digest = hashlib.sha256(json.dumps(out, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]
    sel = {
        "registry": REGISTRY, "schema": SCHEMA, "digest": digest,
        "generated": {"at": now(), "skillVersion": SKILL_VERSION, "mcpVersion": a.mcp_version},
        "site": {"id": a.site_id, "name": a.site_name},
        "counts": dict(counts),
        "legend": {"content": "group: fields; 'X ×N' = N numbered repeats",
                   "capacity": "max repeats; shownByDefault when later repeats start hidden",
                   "cms": "Collection Lists: verified | estimated (min = lower bound) | unknown; knowledge.md overrides",
                   "slots": "slot props (insert Item components here)",
                   "warnings": "ambiguous-slots, fixed-count: limitations to plan around"},
        "duplicateNames": [n for n, k in names.items() if k > 1],
        "nearMissNames": near,
        "components": out,
    }
    body = payload_md(f"{REGISTRY_NAME} · selection", sel)
    root = root_md(sel, len(body.encode()))
    for p, b in ((P["selection"], body), (P["root"], root)):
        if len(b.encode()) > MAX_BODY:
            sys.exit(f"{p} exceeds {MAX_BODY} B")
    assert parse_payload(body) == sel

    have = set(split_ids(a.existing_paths))
    # Root first: creating a nested data/ file before its parent folder exists returned an
    # upstream 500 on a fresh install (observed live, MCP 2.2).
    writes = [action("update" if P["root"] in have else "create", P["root"], root,
                     a.site_id, f"{REGISTRY_NAME} — root"),
              action("update" if P["selection"] in have else "create", P["selection"], body,
                     a.site_id, f"{REGISTRY_NAME} — selection")]
    keep = {P["selection"], P["root"], P["knowledge"]}
    cleanup = []
    for reg in LEGACY_REGISTRIES:
        legacy = sorted(p for p in have if p.startswith(reg + "/"))
        if legacy:   # deleting the legacy root cascades to all of its files
            root_l = f"{reg}/SKILL.md"
            cleanup.append(action("delete", root_l if root_l in legacy else legacy[0], None, a.site_id))
            cleanup += [action("delete", p, None, a.site_id) for p in legacy
                        if root_l not in legacy and p != legacy[0]]
    cleanup += [action("delete", p, None, a.site_id)
                for p in sorted(have) if p.startswith(REGISTRY + "/") and p not in keep]
    os.makedirs(a.out_dir, exist_ok=True)
    json.dump(sel, open(f"{a.out_dir}/selection.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    open(f"{a.out_dir}/write.call.json", "w").write(json.dumps(writes, ensure_ascii=True))
    open(f"{a.out_dir}/cleanup.call.json", "w").write(json.dumps(cleanup, ensure_ascii=True))
    dump({"counts": sel["counts"], "digest": digest, "selectionBytes": len(body.encode()),
          "writes": [next(k for k in w if k != "label").split("_")[0] + " " + w["label"] for w in writes],
          "cleanup": [c["label"] for c in cleanup], "nearMissNames": near,
          "knowledgeExists": P["knowledge"] in have,
          "warnings": {c["name"]: c["warnings"] for c in out if c.get("warnings")}})


def registry_verify(a):
    """Compare the stored selection (write/read result) with the generated one: digest AND every entry.
    Catches payloads altered in transit (a matching digest string alone does not)."""
    stored = selection_from(a.readback)
    gen = json.load(open(a.expected, encoding="utf-8"))
    s = {c["id"]: c for c in stored["components"]}
    g = {c["id"]: c for c in gen["components"]}
    recomputed = hashlib.sha256(json.dumps(stored["components"], sort_keys=True, ensure_ascii=False)
                                .encode()).hexdigest()[:12]
    diff = {"missing": [g[i]["name"] for i in g if i not in s], "extra": [s[i]["name"] for i in s if i not in g],
            "changed": [g[i]["name"] for i in g if i in s and s[i] != g[i]]}
    ok = (stored.get("digest") == gen["digest"] == recomputed) and not any(diff.values())
    dump({"ok": ok, "storedDigest": stored.get("digest"), "expectedDigest": gen["digest"],
          "recomputedFromStored": recomputed, **diff})
    if not ok:
        sys.exit(1)


def selection_load(a):
    bodies = {}
    for d in walk(load_objects(a.readback)):
        if d.get("action") == "read_instruction" and isinstance(d.get("label"), str):
            r = d.get("result") or {}
            md = r.get("markdown") if isinstance(r, dict) else None
            if md is not None:
                bodies[r.get("path") or d["label"]] = md
    md = next((bodies[k] for k in bodies if k.endswith("/data/selection.md")), None)
    if md is None:
        sys.exit("selection registry missing (tried new and legacy paths)")
    sel = parse_payload(md)
    major = int(str(sel.get("schema")).split(".")[0])
    if sel.get("registry") not in (REGISTRY,) + LEGACY_REGISTRIES or major not in READABLE_MAJORS:
        sys.exit(f"incompatible registry {sel.get('registry')} schema {sel.get('schema')}")
    if a.site_id and sel["site"]["id"] != a.site_id:
        sys.exit("registry belongs to another site")
    ids = [c["id"] for c in sel["components"]]
    if len(ids) != len(set(ids)) or len(ids) != sum(sel["counts"].values()):
        sys.exit("component list inconsistent with counts")
    for c in sel["components"]:          # schema 2 -> 3 view
        if "cms" not in c:
            n = c.pop("cmsLists", 0)
            c["cms"] = ({"status": "estimated", "min": n, "basis": "legacy cmsLists (lower bound)"} if n
                        else {"status": "unknown", "basis": "legacy registry"})
    dump({"legacy": sel["registry"] != REGISTRY, **sel})


# ----------------------------------------------------------- knowledge

KNOWN_KEYS = {"registry", "kind", "schema", "site", "updated", "starter", "locales", "links",
              "components", "notes", "catalogue"}


def knowledge_build(a):
    k = json.load(open(a.in_, encoding="utf-8"))
    problems = [f"unknown top-level key {x!r}" for x in k if x not in KNOWN_KEYS]
    cat = k.get("catalogue")
    if cat is not None and (not isinstance(cat, dict) or cat.get("path") != CATALOGUE_PATH):
        problems.append(f"catalogue.path must be {CATALOGUE_PATH!r} (the SML convention)")
    k.update(registry=REGISTRY, kind="knowledge", schema="1.0", updated=now())
    k.setdefault("site", {})["id"] = a.site_id
    st = k.get("starter") or {}
    if st and not (st.get("pageId") and isinstance(st.get("elements"), dict)):
        problems.append("starter needs pageId and elements")
    for el, v in (st.get("elements") or {}).items():
        if not (isinstance(v, dict) and v.get("component") and v.get("element")):
            problems.append(f"starter.elements.{el} needs component + element")
    for href, v in (k.get("links") or {}).items():
        if (v.get("path") or "").strip() in ("", "#", "/#"):
            problems.append(f"links[{href}] path is empty or a placeholder")
        elif v.get("resolution") not in SAFE_LINKS + ("confirmed", "manual"):
            problems.append(f"links[{href}] resolution must be {'|'.join(SAFE_LINKS)}|confirmed|manual "
                            "(a fuzzy/review match is stored only once the user confirmed it: 'confirmed')")
    ids, sel = None, {}
    if a.selection:
        sel = {c["id"]: c for c in selection_from(a.selection)["components"]}
        ids = set(sel)
    reviewed = set(split_ids(getattr(a, "reviewed", "")))
    for cid, v in (k.get("components") or {}).items():
        for fld in ("bestFor", "notFor", "limits"):
            if fld in v and not (isinstance(v[fld], list) and all(isinstance(x, str) for x in v[fld])):
                problems.append(f"components[{cid}].{fld} must be a list of strings")
        if cid in sel:
            if v.get("name") and _ws(v["name"]) != _ws(sel[cid]["name"]):
                problems.append(f"components[{cid}] name {v['name']!r} != registry {sel[cid]['name']!r} (renamed?)")
            if "sig" not in v or cid in reviewed:     # stamp what the knowledge was written against
                v["sig"] = comp_sig(sel[cid])
        for i, cf in enumerate(v.get("configs") or []):
            where = f"components[{cid}].configs[{i}]"
            if isinstance(cf, dict) and cf.get("kind") == "visibility":
                # a boolean prop that hides content props elsewhere in the component (any group)
                if not cf.get("prop") or not isinstance(cf.get("hides"), list) or not cf["hides"]:
                    problems.append(f"{where}: visibility config needs prop ('Group.Name') and hides [keys]")
                if cf.get("status") not in CONFIG_STATUS:
                    problems.append(f"{where}.status must be {'|'.join(CONFIG_STATUS)}")
                if cf.get("status") == "confirmed" and cf.get("basis") not in VISIBILITY_CONFIRMING:
                    problems.append(f"{where}: confirmed visibility needs basis {'|'.join(VISIBILITY_CONFIRMING)} "
                                    f"(a direct prop binding in the definition tree, a render, or the site owner)")
                continue
            if not isinstance(cf, dict) or not cf.get("prop") or not isinstance(cf.get("values"), dict):
                problems.append(f"{where}: needs prop ('Group.Name') and values {{value: {{label?, shows?}}}}")
                continue
            if cf.get("status") not in CONFIG_STATUS:
                problems.append(f"{where}.status must be {'|'.join(CONFIG_STATUS)}")
            if cf.get("status") == "confirmed" and cf.get("basis") not in CONFIG_CONFIRMING:
                problems.append(f"{where}: 'confirmed' needs basis {'|'.join(CONFIG_CONFIRMING)} "
                                f"(catalogue settings or the definition tree alone are 'inferred')")
            for val, d in cf["values"].items():
                for base, n in ((d or {}).get("shows") or {}).items():
                    if not isinstance(n, int) or n < 0:
                        problems.append(f"{where}.values[{val}].shows[{base}] must be a whole number")
        cms = v.get("cms")
        if cms and cms.get("status") not in ("verified", "estimated", "unknown"):
            problems.append(f"components[{cid}].cms.status must be verified|estimated|unknown")
        if cms and cms.get("status") == "verified" and not cms.get("basis"):
            problems.append(f"components[{cid}].cms verified needs a basis")
        if ids is not None and cid not in ids:
            problems.append(f"components[{cid}] ({v.get('name')}) not in selection registry (obsolete: remove it)")
    if problems:
        dump({"problems": problems})
        sys.exit(1)
    body = payload_md(f"{REGISTRY_NAME} · knowledge", k)
    if len(body.encode()) > MAX_BODY:
        sys.exit("knowledge exceeds 256 KB")
    call = [action("update" if a.exists else "create", P["knowledge"], body, a.site_id,
                   f"{REGISTRY_NAME} — knowledge")]
    open(a.out, "w").write(json.dumps(call, ensure_ascii=True))
    dump({"bytes": len(body.encode()), "components": len(k.get("components") or {}),
          "links": len(k.get("links") or {}), "starter": bool(st)})


# ------------------------------------------------------- pages / links

def pages_from(paths_):
    pages = {}
    for p in paths_:
        for d in walk(load_objects(p)):
            # the home page has no "slug" key (publishedPath "/"), so accept either
            if isinstance(d.get("id"), str) and "title" in d and ("slug" in d or "publishedPath" in d):
                pages[d["id"]] = d
    return list(pages.values())


def starter(a):
    cands = [p for p in pages_from(a.pages)
             if re.search(r"starter", f"{p.get('title','')} {p.get('slug','')}", re.I)
             and not p.get("collectionId")]
    cands.sort(key=lambda p: (not re.search(r"starter", p.get("title", ""), re.I), not p.get("draft")))
    dump([{k: p.get(k) for k in ("id", "title", "slug", "draft", "publishedPath")} for p in cands])


ROLE = {"navigation": re.compile(r"navigation|\bnav\b", re.I), "hero": re.compile(r"\bhero\b", re.I),
        "footer": re.compile(r"footer", re.I)}


def starter_check(a):
    """Wrapper + navigation/hero/footer instances of a Starter tree (depth 2) for knowledge.starter.elements."""
    root = next((d for d in walk(load_objects(a.tree)) if d.get("type") == "Body"), None)
    if not root:
        sys.exit("no Body in tree (read the Starter with get_all_elements{depth:2})")
    found, problems = {r: [] for r in ROLE}, []
    wrappers, truncated = [], []

    def visit(node, depth):
        if node.get("type") == "ComponentInstance":
            name = (node.get("instanceDetails") or {}).get("name") or ""
            for r, rx in ROLE.items():
                if rx.search(name):
                    found[r].append({"component": node["id"]["component"], "element": node["id"]["element"],
                                     "name": name, "depth": depth})
            return
        cls = " ".join(node.get("styleNames") or []).lower()
        attrs = node.get("attributes") or {}
        if node.get("type") == "DropTarget" or "wrapper" in cls or "main" in cls \
                or attrs.get("id") in ("main", "main-content") or (node.get("settings") or {}).get("tag") == "main":
            wrappers.append({"component": node["id"]["component"], "element": node["id"]["element"],
                             "type": node.get("type"), "styleNames": node.get("styleNames"), "depth": depth,
                             "holds": [], "holdIds": []})
        if node.get("hasMoreChildren") and not node.get("children"):
            truncated.append(node["id"]["element"])
        for ch in node.get("children") or []:
            if ch.get("type") == "ComponentInstance" and wrappers and wrappers[-1]["element"] == node["id"]["element"]:
                wrappers[-1]["holds"].append((ch.get("instanceDetails") or {}).get("name"))
                wrappers[-1]["holdIds"].append(ch["id"])
        for ch in node.get("children") or []:
            visit(ch, depth + 1)
    for ch in root.get("children") or []:
        visit(ch, 1)
    elements = {}
    hero = found["hero"]
    if truncated and not hero:
        dump({"problems": [f"tree truncated below depth (elements {truncated}); re-read with a larger depth"],
              "candidates": {"wrappers": wrappers, **found}})
        sys.exit(1)
    if wrappers:
        # sections go where the hero lives: the drop target holding it; else any drop target; else first candidate
        holds_hero = [w for w in wrappers if any(ROLE["hero"].search(n or "") for n in w["holds"])]
        drops = [w for w in wrappers if w["type"] == "DropTarget"]
        w = (holds_hero or drops or wrappers)[0]
        elements["wrapper"] = {"component": w["component"], "element": w["element"]}
        pre = [{"name": n, "id": i} for n, i in zip(w["holds"], w["holdIds"]) if n and not ROLE["hero"].search(n)]
        if pre:   # Starter ships content sections: every duplicate inherits them (usually placeholder text)
            elements["prefilled"] = pre
    else:
        problems.append("no page wrapper found: sections cannot be appended safely; ask which element holds content")
    for r in ROLE:
        if len(found[r]) == 1:
            elements[r] = {k: found[r][0][k] for k in ("component", "element")}
        elif not found[r]:
            problems.append(f"no {r} instance on the Starter" + (" (a page hero must be inserted)" if r == "hero" else ""))
        else:
            problems.append(f"{len(found[r])} {r} instances: {[x['name'] for x in found[r]]}")
    dump({"elements": elements, "heroName": hero[0]["name"] if len(hero) == 1 else None,
          "candidates": {"wrappers": wrappers, **found}, "problems": problems})
    if problems:
        sys.exit(1)


def links(a):
    loc = json.loads(a.locales)
    prim = loc.get("primary") or {}
    secs = loc.get("secondary") or []
    sec_dirs = {s.get("subdirectory") for s in secs if s.get("subdirectory")}
    strip = {x.lower() for x in (prim.get("tag"), prim.get("subdirectory")) if x} - {d.lower() for d in sec_dirs}
    pages = [p for p in pages_from(a.pages) if not p.get("collectionId")]
    live = {p["publishedPath"]: p for p in pages if p.get("publishedPath") and not p.get("draft")}
    drafts = {p["publishedPath"]: p for p in pages if p.get("publishedPath") and p.get("draft")}
    out = []
    for href in a.href:
        r = {"href": href}
        if href.strip() in ("", "#", "/#") or href.strip().lower().startswith("javascript:"):
            r.update(resolution="placeholder", note="not a real link; keep an intended button unlinked and report it")
            out.append(r)
            continue
        if href.startswith("#"):
            r.update(path=href, resolution="anchor")
            out.append(r)
            continue
        if re.match(r"^(https?:|mailto:|tel:)", href):
            r.update(path=href, resolution="external")
            out.append(r)
            continue
        path = "/" + href.split("?")[0].split("#")[0].strip("/")
        segs = [s for s in path.split("/") if s]
        prefix, how = "", "exact"
        if segs and segs[0] in sec_dirs:
            prefix, segs = "/" + segs[0], segs[1:]
        elif segs and segs[0].lower() in strip and (prim.get("subdirectory") or "") == "":
            segs, how = segs[1:], "locale-stripped"
        target = "/" + "/".join(segs)
        if target in live:
            r.update(path=prefix + target, pageId=live[target]["id"], resolution=how)
        else:
            last = segs[-1] if segs else ""
            cands = [p for pth, p in live.items() if last and (
                pth.rsplit("/", 1)[-1].startswith(last + "-") or pth.rsplit("/", 1)[-1] == last
                or last.startswith(pth.rsplit("/", 1)[-1] + "-"))]
            norm = {k.lower().rstrip("/") or "/": p for k, p in live.items()}
            t2 = re.sub(r"(/index)?\.html?$", "", target.lower()).rstrip("/") or "/"
            if t2 in norm:     # same path up to case / trailing slash / .html: equivalent, automatic
                r.update(path=prefix + norm[t2]["publishedPath"], pageId=norm[t2]["id"], resolution="normalized")
            elif cands:        # plausible is not proof: never written without confirmation
                r.update(resolution="review", candidates=[
                    {"path": prefix + c["publishedPath"], "pageId": c["id"], "title": c.get("title")}
                    for c in cands][:5],
                    note=f"{target} not found; similar page(s) need confirmation",
                    draftMatch=drafts[target]["id"] if target in drafts else None)
            else:
                r.update(resolution="unresolved", candidates=[],
                         draftMatch=drafts[target]["id"] if target in drafts else None)
        out.append(r)
    if getattr(a, "out", None):
        json.dump({x["href"]: x for x in out}, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    dump(out)


# ------------------------------------------------------------ execution

def instances(node):
    if isinstance(node, list):
        for x in node:
            yield from instances(x)
        return
    if not isinstance(node, dict):
        return
    if node.get("type") == "ComponentInstance":
        details = node.get("instanceDetails", node)
        if "props" in details:
            yield details
            for slot in details.get("slots") or []:
                yield from instances(slot.get("children") or [])
    for child in node.get("children") or []:
        yield from instances(child)


def bindings(tree):
    out = collections.defaultdict(list)
    for inst in instances(tree):
        for p in inst.get("props") or []:
            v = p.get("value")
            if isinstance(v, dict) and v.get("sourceType") == "prop":
                pair = (inst["id"], p["propId"])
                if pair not in out[v["propId"]]:
                    out[v["propId"]].append(pair)
    return out


def repeat_visibility(comp, tree):
    """Which numbered repeats ('Box 4', 'Card 2' …) always render and which depend on something else.
    Walks the definition tree (slots included); a repeat's state is the strongest condition on the path to
    each element bound to that repeat's props, and the repeat takes the weakest of those (it renders when any
    of its elements does): 'always' | 'conditional' (condition not exposed by MCP) |
    'prop:<propId>' (visibility bound to a component prop) | 'hidden' (static false)."""
    group_of = {}
    for p in comp.get("props") or []:
        for label_ in (p.get("group") or "", p.get("name") or ""):
            for part in re.split(r"\s*—\s*", label_):
                m = NUMBERED.match(part.strip())
                if m:
                    group_of[p["id"]] = (m.group(1).strip(), int(m.group(2)))
    if not group_of or not tree:
        return {}
    rank = {"always": 0, "prop": 1, "conditional": 2, "hidden": 3}
    found = {}

    def vis_of(props, settings):
        for q in props or []:
            if q.get("name") == "Visibility":
                v = q.get("value")
                if isinstance(v, dict) and v.get("sourceType") == "conditional":
                    return "conditional"
                if isinstance(v, dict) and v.get("sourceType") == "prop":
                    return "prop:" + v.get("propId", "")
                if v is False:
                    return "hidden"
        if isinstance(settings, dict) and settings.get("visibility") is False:
            return "hidden"
        return "always"

    def stronger(a, b):
        return a if rank[a.split(":")[0]] >= rank[b.split(":")[0]] else b

    def visit(n, state):
        if not isinstance(n, dict):
            return
        inst = n.get("instanceDetails") if isinstance(n.get("instanceDetails"), dict) else (
            n if n.get("type") == "ComponentInstance" and "props" in n else None)
        here = vis_of((inst or {}).get("props"), n.get("settings"))
        st = stronger(state, here)
        for q in (inst or {}).get("props") or []:
            v = q.get("value")
            if isinstance(v, dict) and v.get("sourceType") == "prop" and v.get("propId") in group_of \
                    and q.get("name") != "Visibility":
                key = group_of[v["propId"]]
                # a repeat shows if any of its bound elements shows: keep the weakest condition seen
                found[key] = st if key not in found or rank[st.split(":")[0]] < rank[found[key].split(":")[0]] \
                    else found[key]
        for c in n.get("children") or []:
            visit(c, st)
        for sl in (inst or {}).get("slots") or []:
            for c in sl.get("children") or []:
                visit(c, st)
    visit(tree, "always")
    out = collections.defaultdict(dict)
    for (base, i), st in sorted(found.items()):
        out[base][str(i)] = st
    return dict(out)


def prop_gates(comp, tree):
    """{content prop id: [boolean prop ids]} — the component booleans that every rendering of a content prop
    depends on, read from Visibility values bound directly to component props (sourceType 'prop') on the path
    to each element bound to that content prop. Conditional visibility is ignored (its rule is not exposed),
    so only confirmed, structural relationships are returned. Works across property groups."""
    bools = {p["id"] for p in comp.get("props") or [] if p.get("type") == "boolean"}
    if not tree or not bools:
        return {}
    seen = {}

    def gates_of(props, settings):
        g = set()
        vis = [q for q in props or [] if q.get("name") in ("Visibility", "Show")]
        # several props named Visibility on one nested instance (e.g. one for a decoration inside it): the tree
        # does not say which governs the instance itself — ambiguous, so none is taken as a gate
        if len(vis) == 1:
            v = vis[0].get("value")
            if isinstance(v, dict) and v.get("sourceType") == "prop":
                g.add(v.get("propId"))
        sv = (settings or {}).get("visibility") if isinstance(settings, dict) else None
        if isinstance(sv, dict) and sv.get("sourceType") == "prop":
            g.add(sv.get("propId"))
        return g

    def visit(n, gates):
        if not isinstance(n, dict):
            return
        inst = n.get("instanceDetails") if isinstance(n.get("instanceDetails"), dict) else (
            n if n.get("type") == "ComponentInstance" and "props" in n else None)
        here = gates | gates_of((inst or {}).get("props"), n.get("settings"))
        for q in (inst or {}).get("props") or []:
            v = q.get("value")
            if isinstance(v, dict) and v.get("sourceType") == "prop" and q.get("name") not in ("Visibility", "Show"):
                tgt = v.get("propId")
                # gated only if *every* element bound to the prop sits behind the gate
                seen[tgt] = here if tgt not in seen else seen[tgt] & here
        for c in n.get("children") or []:
            visit(c, here)
        for sl in (inst or {}).get("slots") or []:
            for c in sl.get("children") or []:
                visit(c, here)
    visit(tree, frozenset())
    return {pid: sorted(g & bools - {pid}) for pid, g in seen.items() if g & bools - {pid}}


def tree_slots(tree):
    out = []
    for inst in instances(tree):
        for s in inst.get("slots") or []:
            out.append({"name": s.get("name"), "instance": inst.get("name"),
                        "element": (s.get("id") or {}).get("element"),
                        "slotId": (s.get("id") or {}).get("slot")})
    return out


class Resolver:
    """Variant prop -> component whose variants are its options.
    1. non-base default variant id -> its owner (needs the variant catalogue)
    2. prop bound to nested instance props -> resolve recursively
    3. otherwise the component's own variants
    Records what is missing instead of guessing."""

    def __init__(self, details, variants, trees, has_catalogue):
        self.details, self.variants, self.trees = details, variants, trees
        self.has_catalogue = has_catalogue
        self.binds = {cid: bindings(t) for cid, t in trees.items() if t}
        self.vindex = collections.defaultdict(set)
        for c in list(variants.values()) + list(details.values()):
            for v in c.get("variants") or []:
                if v.get("id") and v["id"] != "base":
                    self.vindex[v["id"]].add(c["id"])
        self.need_details, self.need_trees, self.need_catalogue = set(), set(), False
        self.consulted = set()

    def resolve(self, cid, pid, path=()):
        comp = self.details.get(cid) or self.variants.get(cid)
        if comp is None or "props" not in comp:
            self.need_details.add(cid)
            return ("missing",)
        prop = next((p for p in comp["props"] if p["id"] == pid), None)
        if prop is None or prop.get("type") != "variant":
            return ("error", f"bound to non-variant prop {pid} on {cid}")
        step = path + ({"componentId": cid, "propId": pid},)
        default = prop.get("defaultValue")
        if isinstance(default, str) and default != "base":
            owners = self.vindex.get(default, set())
            if len(owners) == 1:
                return ("ok", next(iter(owners)), "default-id", step)
            if not owners and not self.has_catalogue:
                self.need_catalogue = True
                return ("missing",)
            return ("error", f"default variant id {default} owned by {len(owners)} components")
        if cid not in self.trees:
            self.need_trees.add(cid)
            return ("missing",)
        self.consulted.add(cid)
        if self.trees[cid] is None:
            return ("error", f"definition tree of {cid} unreadable")
        targets = self.binds.get(cid, {}).get(pid, [])
        if not targets:
            return ("ok", cid, "own", step)
        results = [self.resolve(nc, np, step) for nc, np in targets]
        for r in results:
            if r[0] != "ok":
                return r
        if len({r[1] for r in results}) != 1:
            return ("error", "bound to different option owners")
        return ("ok", results[0][1], "binding", results[0][3])


# set_component_instance_prop_values value shapes, verified on MCP 2.2.0
WRITE = {
    "textContent": {"type": "string", "field": "string_value"},
    "string": {"type": "string", "field": "string_value"},
    "id": {"type": "string", "field": "string_value"},
    "altText": {"type": "string", "field": "string_value"},
    "richText": {"type": "richText", "field": "rich_text_inner_text",
                 "note": "plain text only; blank line = new paragraph"},
    "boolean": {"type": "boolean", "field": "boolean_value"},
    "number": {"type": "number", "field": "number_value"},
    "link": {"type": "link", "field": "link_mode+link_to", "note": "url mode; 'page' mode is rejected"},
    "video": {"type": "video", "field": "video_src"},
    "variant": {"type": "string", "field": "string_value", "note": "option id as string"},
}
UNSUPPORTED = {"visibility": "conditional visibility; write shape unverified",
               "image": "no image value type (keep placeholders)",
               "selectedItems": "CMS selection; not writable via prop values",
               "filter": "CMS filter; not writable via prop values",
               "headingTag": "write shape unverified",
               "slot": "insert Item components instead"}


def _exec_inputs(a):
    selected = split_ids(a.selected)
    details = components_from(a.details)
    variants = components_from([a.variants]) if a.variants else {}
    trees = trees_from(a.trees)
    resolve = "all" if (a.resolve or "") == "all" else set(split_ids(a.resolve))
    return selected, details, variants, trees, resolve


def _wanted(resolve, pid):
    return resolve == "all" or pid in resolve


def exec_needs(a):
    selected, details, variants, trees, resolve = _exec_inputs(a)
    r = Resolver(details, variants, trees, bool(a.variants))
    investigate = set(split_ids(getattr(a, "investigate", "") or ""))
    for cid in selected:
        if cid not in details:
            r.need_details.add(cid)
            continue
        if (any(p.get("type") == "slot" for p in details[cid]["props"]) or cid in investigate) \
                and cid not in trees:
            r.need_trees.add(cid)
        for p in details[cid]["props"]:
            if p.get("type") == "variant" and _wanted(resolve, p["id"]):
                r.resolve(cid, p["id"])
    dump({"details": sorted(r.need_details), "trees": sorted(r.need_trees),
          "variantCatalogue": r.need_catalogue})


def exec_build(a):
    selected, details, variants, trees, resolve = _exec_inputs(a)
    r = Resolver(details, variants, trees, bool(a.variants))
    out, problems = {}, []
    for cid in selected:
        c = details.get(cid)
        if not c:
            problems.append(f"{cid}: details missing")
            continue
        props, slots = [], []
        for p in c["props"]:
            e = {"id": p["id"], "key": key_of(p), "type": p.get("type"),
                 "group": p.get("group") or "", "name": p["name"]}
            if p.get("type") in TEXT_TYPES and isinstance(p.get("defaultValue"), str) \
                    and p["defaultValue"].strip():
                e["defaultText"] = p["defaultValue"].strip()[:80]
            if p.get("type") == "slot":
                slots.append({"propId": p["id"], "key": key_of(p), "name": p["name"]})
                continue
            if p.get("type") not in TEXT_TYPES and "defaultValue" in p:
                e["default"] = p["defaultValue"]
            if p.get("type") in WRITE:
                e["write"] = WRITE[p["type"]]
            else:
                e["write"] = None
                e["writeNote"] = UNSUPPORTED.get(p.get("type"), "unknown prop type")
            if p.get("type") == "variant":
                if _wanted(resolve, p["id"]):
                    res = r.resolve(cid, p["id"])
                    if res[0] == "ok":
                        owner = variants.get(res[1]) or details.get(res[1])
                        e["options"] = [{"id": v["id"], "name": v["name"]} for v in owner.get("variants") or []]
                        e["optionsFrom"] = {"component": owner["name"], "method": res[2]}
                        if not e["options"]:
                            problems.append(f"{c['name']} / {e['key']}: owner has no variants")
                    else:
                        problems.append(f"{c['name']} / {e['key']}: unresolved ({res})")
                else:
                    e["optionsLazy"] = True
            props.append(e)
        rec = {"name": c["name"], "kind": kind_of(c["name"]),
               "variants": [{"id": v["id"], "name": v["name"]} for v in c.get("variants") or []],
               "props": props,
               "writable": {"text": sum(1 for e in props if e["type"] in TEXT_TYPES),
                            "link": sum(1 for e in props if e["type"] == "link"),
                            "unsupported": sorted({e["type"] for e in props if e.get("write") is None
                                                   and e["type"] not in ("visibility",)})}}
        if trees.get(cid):
            rv = repeat_visibility(c, trees[cid])
            if rv:
                rec["repeatVisibility"] = rv
                cond = {b: [i for i, v in m.items() if v != "always"] for b, m in rv.items()}
                switches = [e["key"] for e in props if e["type"] == "boolean"
                            and re.search(r"\b(amount|number|count)\b", e["name"], re.I)]
                if any(cond.values()) and switches:
                    rec["configHint"] = (f"{switches[0]} probably governs repeats "
                                         + "; ".join(f"{b} {', '.join(v)}" for b, v in cond.items() if v)
                                         + " (conditional visibility; MCP does not expose the condition). Confirm "
                                         "which value shows how many (catalogue, Designer render or a live test) "
                                         "and store it in knowledge configs.")
        if trees.get(cid):
            gates = prop_gates(c, trees[cid])
            if gates:
                rec["visibleIf"] = gates
                byid = {e["id"]: e["key"] for e in props}
                inv = collections.defaultdict(list)
                for pid, gs in gates.items():
                    for g in gs:
                        if pid in byid and g in byid:
                            inv[byid[g]].append(byid[pid])
                rec["visibilityControls"] = {g: sorted(v) for g, v in sorted(inv.items())}
        if slots:
            names = collections.Counter(s["name"] for s in slots)
            rec["slots"] = slots
            rec["slotNamesUnique"] = all(v == 1 for v in names.values())
            if trees.get(cid):
                rec["instanceSlotNames"] = [s["name"] for s in tree_slots(trees[cid])]
            if not rec["slotNamesUnique"]:
                problems.append(f"{c['name']}: ambiguous slot names {dict(names)}; only the first slot is addressable")
        keys = collections.Counter(e["key"] for e in props)
        dup = [k for k, n in keys.items() if n > 1]
        if dup:
            rec["duplicateKeys"] = dup
        out[cid] = rec
    deps = sorted(r.consulted - set(selected))
    doc = {"schema": SCHEMA, "kind": "execution", "components": out, "problems": problems, "deps": deps}
    json.dump(doc, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    dump({"components": len(out), "props": sum(len(c["props"]) for c in out.values()),
          "variantsResolved": sum(1 for c in out.values() for p in c["props"] if p.get("options")),
          "variantsLazy": sum(1 for c in out.values() for p in c["props"] if p.get("optionsLazy")),
          "deps": deps, "problems": problems})
    if problems:
        sys.exit(1)



SAFE_LINKS = ("exact", "locale-stripped", "normalized", "external", "anchor")
CONFIG_STATUS = ("confirmed", "inferred")
CONFIG_CONFIRMING = ("designer-render", "live-render", "site-owner")
# Visibility bindings are structural: a Visibility prop bound directly to a component prop in the definition tree is
# evidence (unlike a conditional rule, whose condition MCP does not expose).
VISIBILITY_CONFIRMING = CONFIG_CONFIRMING + ("definition-tree",)
CATALOGUE_PATH = "/stylesheet/components"     # SML convention on every site


def _ws(s):
    return re.sub(r"\s+", " ", s or "").strip()


def config_check(kentry, reg_entry):
    """The one rule for configuration knowledge, used by select-context, compose, writes-build and verify-page.
    Returns (usable configs, problem). Configs are usable only when the knowledge entry carries a fingerprint
    (sig) equal to the fingerprint of the component's *current* registry entry. Otherwise none are usable and
    problem says why: 'stale' (component changed), 'unverifiable: …' (no registry entry or no sig to compare).
    Unusable configs never hide repeats, never resolve warnings and never make a setting look safe."""
    cfgs = (kentry or {}).get("configs") or []
    if not cfgs:
        return [], None
    if reg_entry is None:
        return [], "unverifiable: current registry entry not available (pass the selection registry)"
    if not kentry.get("sig"):
        return [], "unverifiable: knowledge entry has no fingerprint (re-stamp with knowledge-build)"
    if kentry["sig"] != comp_sig(reg_entry):
        return [], "stale: component changed since the configuration was recorded"
    return cfgs, None


def reinvestigate_entry(name, kentry, problem, cid=None):
    return {"component": name, **({"id": cid} if cid else {}), "configs": [cf.get("prop") for cf in (kentry or {}).get("configs") or []],
            "reason": problem + " — reinvestigate before relying on it"}


def comp_sig(c):
    """Fingerprint of the registry facts a knowledge entry was written against."""
    keep = {k: c.get(k) for k in ("name", "content", "capacity", "slots", "options", "toggles", "warnings")}
    return hashlib.sha256(json.dumps(keep, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:10]


def payload_from(path, kinds=("selection", "knowledge")):
    """Registry payload from a plain JSON file or a saved read_instruction result."""
    objs = load_objects(path)
    for o in objs:
        if isinstance(o, dict) and ("components" in o or o.get("kind") == "knowledge") and "registry" in o:
            return o
    for d in walk(objs):
        r = d.get("result") if isinstance(d.get("result"), dict) else d
        md = r.get("markdown") if isinstance(r, dict) else None
        p = (r.get("path") or "") if isinstance(r, dict) else ""
        if isinstance(md, str) and any(p.endswith(f"/data/{k}.md") for k in kinds):
            return parse_payload(md)
    sys.exit(f"{path}: no {'/'.join(kinds)} payload found")


def selection_from(path):
    sel = payload_from(path, ("selection",))
    for c in sel["components"]:          # schema 2 -> 3 view
        if "cms" not in c:
            n = c.pop("cmsLists", 0)
            c["cms"] = ({"status": "estimated", "min": n, "basis": "legacy cmsLists (lower bound)"} if n
                        else {"status": "unknown", "basis": "legacy registry"})
    return sel


def select_context(a):
    """Selection cards: registry facts (authoritative) + curated knowledge (visual purpose)."""
    sel = selection_from(a.selection)
    kn = payload_from(a.knowledge, ("knowledge",)) if a.knowledge else {}
    kc = kn.get("components") or {}
    want = set(split_ids(a.ids))
    cards, health = [], {"noVisual": [], "stale": [], "obsolete": [], "renamed": []}
    regs = {c["id"]: c for c in sel["components"]}
    for cid, v in kc.items():
        if cid not in regs:
            health["obsolete"].append(f"{v.get('name')} ({cid})")
    for c in sel["components"]:
        if want and c["id"] not in want:
            continue
        k = kc.get(c["id"]) or {}
        card = {"name": c["name"], "id": c["id"], "kind": c["kind"], "content": c.get("content", [])}
        for f in ("capacity", "slots", "options", "toggles", "warnings"):
            if c.get(f):
                card[f] = c[f]
        cms = c.get("cms")
        if k.get("cms"):                     # curated evidence beats a derived estimate
            cms = k["cms"]
        card["cms"] = cms
        for f in ("visual", "visualBasis", "bestFor", "notFor", "limits", "execDeps", "configs"):
            if k.get(f):
                card[f] = k[f]
        usable, problem = config_check(k, c)
        if problem:
            card["configsUnusable"] = problem
            health.setdefault("reinvestigate", []).append(reinvestigate_entry(c["name"], k, problem, c["id"]))
        conf = [cf for cf in usable if cf.get("status") == "confirmed"]
        if conf and card.get("warnings"):
            card["warnings"] = [w + (" — RESOLVED by knowledge configs (confirmed)" if w.startswith("count-switch")
                                     else "") for w in card["warnings"]]
        elif any(w.startswith("count-switch") for w in card.get("warnings") or []):
            card["investigate"] = (("stored configuration is unusable (" + problem + "); ") if problem else "") + (
                                   "count switch not yet confirmed: read the definition tree "
                                   "(exec-needs --investigate), the catalogue, then render or live-test; "
                                   "do not reject the component before that")
        if not k.get("visual"):
            health["noVisual"].append(c["name"])
        if k and k.get("sig") and k["sig"] != comp_sig(c):
            card["knowledgeStale"] = ("component changed since this knowledge was written: fields/capacity "
                                      "above are current; re-check visual, bestFor and limits")
            health["stale"].append(c["name"])
        if k.get("name") and _ws(k["name"]) != _ws(c["name"]):
            health["renamed"].append(f"{k['name']} -> {c['name']}")
        cards.append(card)
    dump({"site": sel["site"], "digest": sel.get("digest"), "health": health, "cards": cards})


# --------------------------------------------------------------- writes

def load_exec(path):
    """execution.json components; fills group/name for files written by v0.4 (key = 'Group.Name')."""
    ex = json.load(open(path, encoding="utf-8"))["components"]
    for c in ex.values():
        for p in c.get("props") or []:
            if "name" not in p:
                g, _, n = p["key"].partition(".") if "." in p["key"] else ("", "", p["key"])
                p["group"], p["name"] = g, n
    return ex


def _role(p):
    n, g = p.get("name", "").lower(), p.get("group", "").lower()
    if "eyebrow" in n:
        return "eyebrow"
    if "button" in n and "text" in n or (("button" in g or "cta" in g) and n == "text"):
        return "button"
    if n in ("heading", "title", "question", "label column — heading") or n.endswith(" heading") \
            or n.endswith("— title"):
        return "heading"
    if p.get("type") == "richText" or n in ("paragraph", "larger paragraph", "answer", "quote", "description"):
        return "body"
    return "text"


GENERIC = re.compile(r"\b(unlock|unleash|seamless(ly)?|cutting[- ]edge|game[- ]chang\w*|revolutioni[sz]\w*|"
                     r"next[- ]level|world[- ]class|best[- ]in[- ]class|supercharge\w*|elevate your|"
                     r"empower(s|ing)? (you|your)|in today's fast[- ]paced|take .{0,20} to the next level|"
                     r"look no further|harness the power)\b", re.I)
MARKDOWN = re.compile(r"(\*\*[^*]+\*\*|^#{1,6} |^\s*[-*•] |^\s*\d+\) )", re.M)


def _count_hidden(props, setv, configs=None):
    """Repeats switched off by 'Amount of X' style number props, or by knowledge configs
    (a prop value whose 'shows' says how many repeats render): {stem: count}."""
    out = {}
    byk = {p.get("key") or key_of(p): p for p in props}
    for cf in configs or []:
        p = byk.get(cf.get("prop"))
        if not p:
            continue
        v = setv.get(p["id"], p.get("default"))
        d = (cf.get("values") or {}).get(json.dumps(v) if isinstance(v, bool) else str(v)) or {}
        for base, n in (d.get("shows") or {}).items():
            out[base.lower().rstrip("s")] = int(n)
    for p in props:
        m = re.match(r"^(amount of|number of|items shown)\s*(\w*)", p.get("name", ""), re.I)
        if p.get("type") == "number" and m:
            stem = (m.group(2) or "item").lower().rstrip("s")
            v = setv.get(p["id"], p.get("default"))
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                out[stem] = int(v)
    return out


MEDIA_NAME = re.compile(r"video|embed|iframe", re.I)
MEDIA_URL = re.compile(r"^https?://\S*(vimeo|youtu|wistia|\.mp4|\.webm|\.m3u8|player\.)", re.I)


def _is_media(p):
    """A default video or embed source (not an on/off switch)."""
    if p.get("type") == "video":
        return True
    if p.get("type") not in TEXT_TYPES:
        return False
    return bool(MEDIA_NAME.search(p.get("name", "")) or MEDIA_URL.match(p.get("defaultText") or ""))


def _media_switches(p, props):
    """Boolean props that turn this media on (same group, name mentions video/lightbox/embed)."""
    return [q for q in props if q.get("type") == "boolean" and q.get("group", "") == p.get("group", "")
            and re.search(r"video|lightbox|embed", q.get("name", ""), re.I)]


def _leftovers(comp, setv, accepted, media=None, configs=None, hidden_out=None):
    """Visible text that keeps its component default (or links left empty/'#') after the write.
    Heuristic: group 'Visibility'/'Show', field toggles ('Button — Visibility' governs 'Button — Text',
    'Column 1 — Highlight' governs 'Column 1 — Highlight label'), 'Amount of X' counts, parent groups."""
    props = comp["props"]
    counts = _count_hidden(props, setv, configs)
    by_group = collections.defaultdict(list)
    for p in props:
        by_group[p.get("group", "")].append(p)
    variant_set = any(p["type"] == "variant" and p["id"] in setv and setv[p["id"]] not in (None, "base")
                      for p in props)

    def off(s):
        return setv.get(s["id"], s.get("default")) is False

    def toggles_for(p, group):
        n = p["name"].lower()
        for s in by_group.get(group, []):
            if s.get("type") != "boolean" or s is p:
                continue
            lab = VIS.sub("", s["name"]).strip(" —").lower()
            if s["name"] in ("Visibility", "Show") or (lab and n.startswith(lab)):
                yield s

    def repeat_hidden(p):
        for label_ in (p.get("group", ""), p.get("name", "")):
            for part in re.split(r"\s*—\s*", label_):
                m = NUMBERED.match(part.strip())
                if m:
                    stem = m.group(1).split()[-1].lower().rstrip("s")
                    if stem in counts and int(m.group(2)) > counts[stem]:
                        return True
        return False

    byid = {p["id"]: p for p in props}
    bykey = {p.get("key"): p for p in props}
    gates = collections.defaultdict(set)          # content prop id -> boolean prop ids that hide it when off
    for pid, gs in (comp.get("visibleIf") or {}).items():
        gates[pid].update(gs)
    for cf in configs or []:                      # confirmed knowledge (already fingerprint-checked)
        if cf.get("kind") == "visibility" and cf.get("status") == "confirmed" and cf.get("prop") in bykey:
            for k in cf.get("hides") or []:
                if k in bykey:
                    gates[bykey[k]["id"]].add(bykey[cf["prop"]]["id"])

    def gated(p):
        return any(g in byid and off(byid[g]) for g in gates.get(p["id"], ()))

    def hidden(p):
        g = p.get("group", "")
        parent = re.split(r"\s*—\s*", g)[0]
        groups = [g] + ([parent] if parent != g else [])
        return repeat_hidden(p) or gated(p) or any(off(s) for gg in groups for s in toggles_for(p, gg)
                                                   if gg == g or s["name"] in ("Visibility", "Show"))

    if hidden_out is not None:
        hidden_out.append(hidden)
    out = []
    for p in props:
        if p["id"] in setv or p["id"] in accepted or p.get("key") in accepted or hidden(p):
            continue
        if p["type"] == "image":
            # Placeholder images are part of the draft layout: kept as they are (never a reason to hide or
            # reject); listed for replacement before production publishing.
            if media is not None:
                media.append(f"{p['key']}: placeholder image kept — replace in the Designer before publishing")
            continue
        if _is_media(p):
            # A default video/embed is not a harmless placeholder: it may play or load unrelated content.
            d = p.get("defaultText") or (p.get("default") if isinstance(p.get("default"), str) else "")
            if not (d or "").strip():
                continue
            switches = _media_switches(p, props)
            if switches and not any(setv.get(s["id"], s.get("default")) is True for s in switches):
                if media is not None:
                    media.append(f"{p['key']}: default media {d[:60]!r} present but switched off "
                                 f"({', '.join(s['key'] for s in switches)})")
                continue
            how = (f"switch it off ({', '.join(s['key'] for s in switches)})" if switches
                   else "no on/off switch found")
            out.append(f"{p['key']}: default video/embed {d[:60]!r} would play or load — write the source's own, "
                       f"{how}, or accept it with a reason")
            continue
        if p["type"] not in TEXT_TYPES | {"link"}:
            continue      # other media: placeholders stay by rule; their visibility may be conditional
        if p["type"] == "link":
            d = p.get("default")
            to = d.get("to") if isinstance(d, dict) else None
            label_ = [s for s in by_group[p.get("group", "")] if s["type"] in TEXT_TYPES and not hidden(s)
                      and ("button" in s["name"].lower() or s["name"] == "Text")]
            if not label_:
                continue
            if isinstance(to, dict):       # component default points at some page: wrong destination risk
                out.append(f"{p['key']}: keeps the component's default link (page {to.get('pageId')}) "
                           f"while {label_[0]['key']} is visible")
            elif not isinstance(to, str) or to.strip() in ("", "#", "/#"):
                out.append(f"{p['key']}: link empty or '#' while {label_[0]['key']} is visible")
            continue
        if p["type"] not in TEXT_TYPES or not p.get("defaultText"):
            continue
        if re.match(r"^(https?:|/|www\.)", p["defaultText"]) or re.search(r"\b(url|endpoint)\b",
                                                                        p["name"], re.I):
            continue                      # settings, not visible copy
        note = " (unless the selected variant hides it)" if variant_set else ""
        out.append(f"{p['key']}: shows default {p['defaultText']!r}{note}")
    return out


def _lint(comp, written):
    """Editorial guideline checks on written text (guidelines, not rendering facts)."""
    out = []
    props = {p["id"]: p for p in comp["props"]}
    vals = {pid: v for pid, v in written.items() if isinstance(v, str)}
    eyebrows = {props[pid].get("group"): v for pid, v in vals.items() if _role(props[pid]) == "eyebrow"}
    for pid, v in vals.items():
        p, n, words = props[pid], len(v), len(v.split())
        r = _role(p)
        if r == "eyebrow" and (words > 4 or n > 32):
            out.append(f"{p['key']}: eyebrow {words} words / {n} chars (guide 1–4 words)")
        elif r == "heading" and n > 70:
            out.append(f"{p['key']}: heading {n} chars (guide: 1–2 desktop lines, ~70 chars)")
        elif r == "button" and (words > 4 or n > 28):
            out.append(f"{p['key']}: button label {words} words / {n} chars (guide: short and direct)")
        elif r == "body" and p["type"] != "richText" and n > 320:
            out.append(f"{p['key']}: intro/description {n} chars (guide 2–4 lines, ~5 max)")
        if GENERIC.search(v):
            out.append(f"{p['key']}: generic marketing phrase {GENERIC.search(v).group(0)!r}")
        if p["type"] == "richText" and MARKDOWN.search(v):
            out.append(f"{p['key']}: markdown-style markers render literally in plain rich text "
                       f"({MARKDOWN.search(v).group(0).strip()!r})")
        if r == "heading" and eyebrows.get(p.get("group")):
            e = eyebrows[p.get("group")].lower().strip()
            if e and (v.lower().startswith(e) or e == v.lower().strip()):
                out.append(f"{p['key']}: heading repeats the eyebrow {eyebrows[p.get('group')]!r}")
    sibs = collections.defaultdict(list)
    for pid, v in vals.items():
        p = props[pid]
        m = NUMBERED.match(re.split(r"\s*—\s*", p.get("group", ""))[0].strip()) if p.get("group") else None
        if m and _role(p) in ("body", "heading"):
            sibs[(m.group(1), p["name"])].append((len(v), p["key"]))
    for (base, field), xs in sibs.items():
        if len(xs) > 1:
            lo, hi = min(xs), max(xs)
            if hi[0] >= 2.2 * lo[0] and hi[0] - lo[0] >= 80:
                out.append(f"{base} '{field}': siblings range {lo[0]}–{hi[0]} chars ({lo[1]} vs {hi[1]}); "
                           "fine if natural — trim only if the long one repeats or wanders, never pad")
    return out


def _value(p, val, linkmap, where, errors, notes, links=None, native=False):
    """One validated prop value for set_component_instance_prop_values, or None.
    links (list) collects every written link: {where, action, to, mode, pageId?, unlinked?}."""
    pid, t = p["id"], p["type"]
    if val is None:
        return {"prop_id": pid, "type": "null"}, None
    if t not in WRITE:
        errors.append(f"{where}: unsupported ({UNSUPPORTED.get(t, t)})")
        return None, None
    if t in ("textContent", "string", "id", "altText"):
        if not isinstance(val, str):
            errors.append(f"{where}: expected text")
            return None, None
        return {"prop_id": pid, "type": "string", "string_value": val}, val
    if t == "richText":
        if not isinstance(val, str) or not val.strip():
            errors.append(f"{where}: expected non-empty text")
            return None, None
        return {"prop_id": pid, "type": "richText", "rich_text_inner_text": val}, val
    if t == "boolean":
        if not isinstance(val, bool):
            errors.append(f"{where}: expected true/false")
            return None, None
        return {"prop_id": pid, "type": "boolean", "boolean_value": val}, val
    if t == "number":
        if isinstance(val, bool) or not isinstance(val, (int, float)):
            errors.append(f"{where}: expected number")
            return None, None
        return {"prop_id": pid, "type": "number", "number_value": val}, val
    if t == "link":
        links = links if links is not None else []
        action = val.get("action") if isinstance(val, dict) else None
        if isinstance(val, dict) and val.get("unlinked"):
            # an intended action whose destination is unknown: the button stays visible, without a target
            # (MCP stores {"mode":"url"} with no 'to' — verified live). Never a guessed or default destination.
            act = val["unlinked"] if isinstance(val["unlinked"], str) else action or ""
            if not act.strip():
                errors.append(f"{where}: unlinked needs the intended action, e.g. {{\"unlinked\": \"Download the guide\"}}")
                return None, None
            links.append({"where": where, "action": act, "unlinked": True})
            return {"prop_id": pid, "type": "link", "link_mode": "url"}, "<unlinked>"
        to = val.get("url") if isinstance(val, dict) else val
        page_id = None
        if isinstance(val, dict) and "href" in val:
            res = linkmap.get(val["href"])
            if not res:
                errors.append(f"{where}: {val['href']!r} not in --links map; run `links` first")
                return None, None
            conf = val.get("confirmed")
            if res["resolution"] in SAFE_LINKS:
                to = res["path"]
                page_id = res.get("pageId")
            elif res["resolution"] == "review" and conf and conf in [c["path"] for c in res["candidates"]]:
                to = conf
                page_id = next((c.get("pageId") for c in res["candidates"] if c["path"] == conf), None)
                notes.append(f"{where}: {val['href']} -> {conf} (user-confirmed similar page)")
            else:
                cands = [c["path"] for c in res.get("candidates") or []]
                errors.append(f"{where}: {val['href']!r} is {res['resolution']}"
                              + (f"; candidates {cands} need confirmation" if cands else "")
                              + "; confirm a candidate, or keep the intended button visible and unlinked "
                                "({\"unlinked\": \"<action>\"}) and report it — never guess")
                return None, None
        if not isinstance(to, str) or not to.strip() or to.strip() in ("#", "/#"):
            errors.append(f"{where}: empty or placeholder link {to!r}")
            return None, None
        external = bool(re.match(r"^(https?:|mailto:|tel:)", to.strip()))
        if native and page_id and not external:
            v = {"prop_id": pid, "type": "link", "link_mode": "page", "link_to": page_id}
            mode = "page"
        else:
            v = {"prop_id": pid, "type": "link", "link_mode": "url", "link_to": to}
            mode = "url"
        if isinstance(val, dict) and val.get("newTab"):
            v["link_open_in_new_tab"] = True
        links.append({"where": where, **({"action": action} if action else {}), "to": to, "mode": mode,
                      **({"pageId": page_id} if page_id else {}),
                      "kind": "external" if external else "internal"})
        return v, to
    if t == "video":
        return {"prop_id": pid, "type": "video", "video_src": val}, val
    if t == "variant":
        if p.get("optionsLazy") or "options" not in p:
            errors.append(f"{where}: options not resolved; rerun exec-needs/exec-build with --resolve {pid}")
            return None, None
        opt = next((o for o in p["options"] if val in (o["id"], o["name"])), None)
        if not opt:
            errors.append(f"{where}: no option {val!r} (have {[o['name'] for o in p['options']]})")
            return None, None
        return {"prop_id": pid, "type": "string", "string_value": opt["id"]}, opt["id"]
    errors.append(f"{where}: unhandled type {t}")
    return None, None


def _configs(a):
    """({component id: usable configs}, [reinvestigate entries]) under config_check. Without --selection the
    current fingerprint is unknown, so stored configs are unverifiable and none are used."""
    path = getattr(a, "knowledge", None)
    if not path:
        return {}, []
    kn = payload_from(path, ("knowledge",))
    reg = ({c["id"]: c for c in selection_from(a.selection)["components"]}
           if getattr(a, "selection", None) else {})
    usable, redo = {}, []
    for cid, v in (kn.get("components") or {}).items():
        cfgs, problem = config_check(v, reg.get(cid))
        if problem:
            redo.append(reinvestigate_entry(v.get("name") or cid, v, problem, cid))
        elif cfgs:
            usable[cid] = cfgs
    return usable, redo


def writes_build(a):
    """Validate a content spec against execution details.
    Per section status: supported | limited (accepted gaps / declared limits) | unsuitable (visible defaults
    the source cannot replace) | invalid (bad writes) | unresolved (no component chosen) | skipped (test-scoped)."""
    ex = load_exec(a.exec)
    spec = json.load(open(a.spec, encoding="utf-8"))
    linkmap = json.load(open(a.links, encoding="utf-8")) if a.links else {}
    cfgs, redo = _configs(a)
    actions, errors, advice, notes, report, items, review = [], [], [], [], [], [], []
    native = bool(getattr(a, "native_links", False))
    linklog, unplaced = [], []
    used = {it.get("component") for it in spec}
    redo = [r for r in redo if r.get("id") in used]
    for r in redo:
        advice.append(f"{r['component']}: stored configuration not used — {r['reason']}")
    for item in spec:
        lbl = item["label"]
        cid = item.get("component")
        if not cid or cid == "unresolved":
            if item.get("skip"):
                items.append({"label": lbl, "status": "skipped", "reason": item["skip"]})
            else:
                items.append({"label": lbl, "status": "unresolved",
                              "reason": item.get("reason", "no registered component chosen")})
                errors.append(f"{lbl}: no component chosen — ask the user which registered component to use"
                              + (f" (candidates rejected: {item['considered']})" if item.get("considered") else ""))
            continue
        if item.get("remove"):        # e.g. a prefilled Starter section the page does not use
            items.append({"label": lbl, "status": "removed", "reason": item["remove"],
                          **({"element": item["element"]} if item.get("element") else {})})
            continue
        comp = ex.get(cid)
        if not comp:
            errors.append(f"{lbl}: component {cid} not in execution details")
            items.append({"label": lbl, "status": "invalid"})
            continue
        if not a.plan and not item.get("element"):
            errors.append(f"{lbl}: no element id (insert the section first; use --plan before insertion)")
        props = {p["id"]: p for p in comp["props"]}
        bykey = collections.defaultdict(list)
        for p in comp["props"]:
            bykey[p["key"]].append(p)
        values, setv, written, ierr, item_links = [], {}, {}, [], []
        for ref, raw in item.get("set", {}).items():
            if ref in props:
                p = props[ref]
            elif len(bykey.get(ref, [])) == 1:
                p = bykey[ref][0]
            else:
                if bykey.get(ref):
                    ierr.append(f"{lbl} / {ref}: ambiguous key; use the prop id")
                else:
                    near = difflib.get_close_matches(ref, list(bykey), n=3, cutoff=0.6)
                    ierr.append(f"{lbl} / {ref}: no such prop on {comp['name']}"
                                + (f" (renamed? closest: {near})" if near else ""))
                continue
            meta = raw if isinstance(raw, dict) and "value" in raw else None
            val = meta["value"] if meta else raw
            v, shown = _value(p, val, linkmap, f"{lbl} / {p['key']}", ierr, notes, item_links, native)
            if v is None:
                continue
            values.append(v)
            setv[p["id"]] = None if v["type"] == "null" else shown
            if v["type"] != "null":
                written[p["id"]] = shown
            if meta and (meta.get("source") is not None or meta.get("why")):
                report.append({"section": lbl, "component": comp["name"], "field": p["key"],
                               "source": meta.get("source"), "revised": shown, "why": meta.get("why", "")})
        acc = item.get("accept") or {}
        if isinstance(acc, list):
            acc = {k: "" for k in acc}
        for k, why in acc.items():
            if not why:
                advice.append(f"{lbl} / {k}: accepted without a reason — say why it may stay")
        media, hid = [], []
        ccf = cfgs.get(cid) or []
        left = _leftovers(comp, setv, set(acc), media, ccf, hid)
        # intended actions (from the source) must survive restructuring: placed on a visible button
        # (linked or deliberately unlinked) or reported as unplaced — never silently dropped or hidden
        keyed = {f"{lbl} / {p['key']}": p for p in comp["props"]}
        for L in item_links:
            p = keyed.get(L["where"])
            if p is not None and hid and hid[0](p):
                ierr.append(f"{L['where']}: carries the intended action {L.get('action') or L.get('to')!r} "
                            f"but its button is hidden — show the button or move the action")
        placed = {L.get("action") for L in item_links if L.get("action")}
        for act in item.get("actions") or []:
            if act not in placed and act not in (item.get("unplacedActions") or []):
                ierr.append(f"{lbl}: intended action {act!r} is not on any button — put it on a button "
                            f"(linked, or {{\"unlinked\": \"{act}\"}}), or list it under unplacedActions with "
                            f"the reason it cannot be represented")
        for act in item.get("unplacedActions") or []:
            unplaced.append({"section": lbl, "action": act})
        linklog += item_links
        review += [f"{lbl} / {x}" for x in media]
        byk = {p["key"]: p for p in comp["props"]}
        inferred = []
        for cf in ccf:
            p = byk.get(cf.get("prop"))
            if not p or p["id"] not in setv:
                continue
            d = (cf.get("values") or {}).get(json.dumps(setv[p["id"]]) if isinstance(setv[p["id"]], bool)
                                              else str(setv[p["id"]])) or {}
            if cf.get("status") != "confirmed":
                inferred.append(cf["prop"])
                advice.append(f"{lbl} / {cf['prop']}: configuration only inferred ({cf.get('basis')}) — "
                              f"confirm it (render or live test) and store it as confirmed")
            for base, n in (d.get("shows") or {}).items():
                extra = sorted({int(m.group(2)) for q in comp["props"] if q["id"] in written
                                for part in re.split(r"\s*—\s*", q.get("group", ""))
                                for m in [NUMBERED.match(part.strip())]
                                if m and m.group(1).split()[-1].lower().rstrip("s") == base.lower().rstrip("s")
                                and int(m.group(2)) > n})
                if extra:
                    advice.append(f"{lbl} / {base} {', '.join(map(str, extra))}: written but not shown with "
                                  f"{cf['prop']} = {setv[p['id']]} (shows {n})")
        accepted_hits = [k for k in acc]
        lint = _lint(comp, written)
        if ierr:
            status = "invalid"
        elif left:
            status = "unsuitable"
        elif accepted_hits or item.get("limits") or inferred:
            status = "limited"
        else:
            status = "supported"
        items.append({"label": lbl, "component": comp["name"], "status": status,
                      **({"leftovers": left} if left else {}),
                      **({"accepted": acc} if acc else {}),
                      **({"limits": item["limits"]} if item.get("limits") else {})})
        errors += ierr
        errors += [f"{lbl} / {x} — write it, hide it, or accept it with a reason"
                   + ("" if comp.get("visibleIf") is not None else
                      " (if a setting in another group may hide it, read the definition tree: "
                      f"exec-needs --investigate {cid})") for x in left]
        advice += [f"{lbl} / {x}" for x in lint]
        if values and item.get("element"):
            actions.append({"label": lbl, "set_component_instance_prop_values":
                            {"element_id": item["element"], "values": values}})
    if a.plan or errors:   # never leave a sendable (partial or stale) call behind
        if os.path.exists(a.out):
            os.remove(a.out)
    else:
        open(a.out, "w").write(json.dumps(actions, ensure_ascii=False))
    if a.report:
        lines = ["| Section | Field | Original | Revised | Why |", "|---|---|---|---|---|"]
        esc = lambda s: ("—" if s in (None, "") else str(s)).replace("|", "\\|").replace("\n", " ⏎ ")
        for r in report:
            src = r["source"]
            delta = (f" ({len(src)}→{len(r['revised'])} chars)" if isinstance(src, str) and src
                     and isinstance(r["revised"], str) else "")
            lines.append(f"| {r['section']} | {r['field']} | {esc(src)} | {esc(r['revised'])} | "
                         f"{esc(r['why'])}{delta} |")
        open(a.report, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    if redo:
        notes.append(f"{len(redo)} stored configuration(s) not used; see reinvestigate")
    dump({**({"reinvestigate": redo} if redo else {}), "mode": "plan" if a.plan else "build",
          "status": dict(collections.Counter(i["status"] for i in items)),
          "items": items, "actions": len(actions),
          "values": sum(len(x["set_component_instance_prop_values"]["values"]) for x in actions),
          "errors": errors, "notes": notes, "advice": advice, "editorialRows": len(report),
          "productionReview": review, "links": _link_report(linklog, unplaced, native)})
    if errors:
        sys.exit(1)


def _link_report(linklog, unplaced, native):
    """Actions and destinations for the build report: linked (with mode), unlinked (configure before publishing),
    unplaced (no control in the chosen component), and the internal-link method used."""
    internal = [L for L in linklog if L.get("kind") == "internal"]
    out = {"linked": [{k: L[k] for k in ("where", "action", "to", "mode", "pageId") if k in L}
                      for L in linklog if not L.get("unlinked")],
           "unlinked": [{"where": L["where"], "action": L["action"]} for L in linklog if L.get("unlinked")],
           "unplaced": unplaced}
    if internal and not native:
        out["internalMethod"] = ("verified URL path (native page links: Webflow MCP 2.2 rejects link_mode 'page' "
                                 "on component props — tested 2026-11-01; try --native-links when MCP supports it)")
    elif internal:
        out["internalMethod"] = "native page link (verify the stored page reference with verify-page)"
    return out


def ids(a):
    out = []
    for d in walk(load_objects(a.result)):
        if not (isinstance(d.get("label"), str) or isinstance(d.get("build_label"), str)):
            continue
        if "action" not in d and "build_label" not in d:
            continue
        lbl = d.get("label") or d.get("build_label")
        if d.get("error") or d.get("status") == "error":
            out.append({"label": lbl, "error": (d.get("error") or {}).get("message") if isinstance(d.get("error"), dict)
                        else d.get("error") or d.get("message")})
            continue
        res = d.get("result")
        data = d.get("data")   # data_component_builder shape: {build_label, status, data:{id, instanceDetails}}
        if isinstance(data, dict) and isinstance(data.get("id"), dict):
            out.append({"label": lbl, "element": data["id"],
                        "name": (data.get("instanceDetails") or {}).get("name")})
        elif isinstance(res, list) and res and isinstance(res[0], dict) and "id" in res[0]:
            out.append({"label": lbl, "element": res[0]["id"],
                        "name": (res[0].get("instanceDetails") or {}).get("name")})
        elif d.get("status") == "success":
            out.append({"label": lbl, "ok": True, "note": "no element id returned"})
    dump(out)
    if any("error" in x for x in out):
        sys.exit(1)


def _norm(v):
    if isinstance(v, dict) and "innerText" in v:
        return re.sub(r"\s+", " ", v["innerText"].replace("‍", "")).strip()
    if isinstance(v, str):
        return re.sub(r"\s+", " ", v).strip()
    return v


def verify_page(a):
    root = next(d for d in walk(load_objects(a.tree)) if d.get("type") == "Body")
    allinst, order = {}, []

    def visit(node, top):
        if node.get("type") == "ComponentInstance":
            det = node.get("instanceDetails") or {}
            allinst[node["id"]["element"]] = det
            if top:
                order.append(det.get("name"))
        for ch in node.get("children") or []:
            visit(ch, top and node.get("type") != "ComponentInstance")
    visit(root, True)
    issues = []
    names = [n for n in order if n]
    for role, rx in ROLE.items():
        n = sum(1 for x in names if rx.search(x or ""))
        if n != 1:
            issues.append(f"{n} {role} instances (expected 1)")
    if a.expect:
        exp = json.loads(a.expect)
        body = [n for n in names if kind_of(n or "") == "section"
                and not (ROLE["navigation"].search(n) or ROLE["footer"].search(n))]
        if body != exp:
            issues.append(f"section order differs: {body}")
    checked, unlinked = 0, []
    for act in json.load(open(a.call, encoding="utf-8")):
        s = act["set_component_instance_prop_values"]
        inst = allinst.get(s["element_id"]["element"])
        if inst is None:
            issues.append(f"{act['label']}: element not found on page")
            continue
        have = {p["propId"]: p.get("value") for p in inst.get("props") or []}
        for v in s["values"]:
            checked += 1
            got = have.get(v["prop_id"], "<missing>")
            t = v["type"]
            want = (v.get("string_value") if t == "string" else v.get("boolean_value") if t == "boolean"
                    else v.get("number_value") if t == "number" else v.get("rich_text_inner_text") if t == "richText"
                    else {"mode": v.get("link_mode"), "to": v.get("link_to")} if t == "link" else None)
            if t == "null":
                continue
            if t == "link":
                to = got.get("to") if isinstance(got, dict) else None
                if want["mode"] == "page":
                    ok = isinstance(got, dict) and got.get("mode") == "page" and (
                        (to.get("pageId") if isinstance(to, dict) else to) == want["to"])
                else:
                    ok = isinstance(got, dict) and got.get("mode") == want["mode"] and to == want["to"]
                if ok and want["mode"] == "url" and want["to"] is None:
                    unlinked.append(f"{act['label']} / {v['prop_id']}")
            else:
                ok = _norm(got) == _norm(want)
            if not ok:
                issues.append(f"{act['label']} / {v['prop_id']}: expected {str(want)[:60]!r}, found {str(got)[:60]!r}")
    leftovers = []
    if getattr(a, "exec", None):     # what the live page still shows from component defaults
        ex = load_exec(a.exec)
        cfgs, redo = _configs(a)
        review = []                      # placeholder images / switched-off media: production review
        accepted = {}                    # element id -> keys the spec accepted with a reason
        if getattr(a, "spec", None):
            for it in json.load(open(a.spec, encoding="utf-8")):
                acc = it.get("accept") or {}
                if it.get("element"):
                    accepted[it["element"].get("element")] = set(acc if isinstance(acc, list) else acc.keys())
        found, seen = [], set()
        for d in walk(load_objects(a.tree)):
            if d.get("type") == "ComponentInstance" and isinstance(d.get("instanceDetails"), dict):
                el = (d.get("id") or {}).get("element")
                if el in seen:           # the same tree may appear in several saved blocks
                    continue
                seen.add(el)
                found.append((el, d["instanceDetails"]))
        if not found:
            issues.append("leftover check: no component instances found in the tree")
        on_page = {inst.get("id") for _, inst in found}
        redo = [r for r in redo if r.get("id") in on_page]
        for el, inst in found:
            c = ex.get(inst.get("id"))
            if c:
                setv = {p["propId"]: p.get("value") for p in inst.get("props") or [] if p.get("hasOverride")}
                media = []
                leftovers += [f"{inst.get('name')}: {x}"
                              for x in _leftovers(c, setv, accepted.get(el, set()), media, cfgs.get(inst.get("id")))]
                review += [f"{inst.get('name')}: {x}" for x in media]
    slots = {}
    for el, det in allinst.items():
        for s in det.get("slots") or []:
            kids = [((c.get("instanceDetails") or {}).get("name") or c.get("type")) for c in s.get("children") or []]
            slots.setdefault(det.get("name"), []).append({"slot": s.get("name"), "children": kids})
    if unlinked and getattr(a, "exec", None):
        keys = {p["id"]: p["key"] for c in load_exec(a.exec).values() for p in c["props"]}
        unlinked = [re.sub(r"/ (\S+)$", lambda m: "/ " + keys.get(m.group(1), m.group(1)), u) for u in unlinked]
    out = {"sections": names, "valuesChecked": checked, "issues": issues,
           **({"unlinked": [f"{u}: visible button without a destination — configure before publishing"
                            for u in unlinked]} if unlinked else {})}
    if slots:
        out["slots"] = slots
    if getattr(a, "exec", None):
        out["leftovers"] = leftovers
        out["productionReview"] = review
        if redo:
            out["reinvestigate"] = redo
    dump(out)
    if issues:
        sys.exit(1)


# ------------------------------------------------------- catalogue / compose

def find_catalogue(paths_):
    """Locate the page at CATALOGUE_PATH. Works with or without publishedPath, for drafts and unpublished pages:
    1. publishedPath equals the path;
    2. the slug chain (page slug + parent folder/page slugs, from any folder records present) equals the path;
    3. the parent folder's path is known from a sibling page's publishedPath;
    4. slug only: last segment matches and the page sits in a folder whose slug cannot be resolved — reported
       as 'unverified' (confirm with get_page_metadata), never as a match.
    Collection template pages and archived pages are ignored."""
    segs = [x for x in CATALOGUE_PATH.strip("/").split("/") if x]
    nodes = {}
    for p in paths_:
        for d in walk(load_objects(p)):
            if isinstance(d.get("id"), str) and ("slug" in d or "publishedPath" in d) and \
                    ("title" in d or "displayName" in d or "name" in d):
                nodes.setdefault(d["id"], {}).update(d)
    pages = [n for n in nodes.values() if "title" in n and not n.get("collectionId") and not n.get("archived")]

    def chain(n, seen=()):
        parent = n.get("parentId") or n.get("parentFolderId") or n.get("parentFolder")
        here = [n.get("slug") or ""] if n.get("slug") else []
        if not parent:
            return here
        if parent in seen or parent not in nodes:
            return None                     # parent not resolvable from the records we have
        up = chain(nodes[parent], seen + (parent,))
        return None if up is None else up + here

    def folder_path_from_siblings(parent):
        for sib in pages:
            if (sib.get("parentId") == parent) and sib.get("publishedPath") and sib.get("slug"):
                pp = sib["publishedPath"].rstrip("/")
                if pp.endswith("/" + sib["slug"]):
                    return [x for x in pp[: -len(sib["slug"]) - 1].split("/") if x]
        return None

    hits, unverified = [], []
    for n in pages:
        pp = (n.get("publishedPath") or "").rstrip("/")
        if pp:
            if pp == CATALOGUE_PATH:
                hits.append((n, "publishedPath"))
            continue
        if (n.get("slug") or "") != segs[-1]:
            continue
        c = chain(n)
        if c is not None:
            if c == segs:
                hits.append((n, "hierarchy"))
            continue
        fp = folder_path_from_siblings(n.get("parentId"))
        if fp is not None:
            if fp + [n["slug"]] == segs:
                hits.append((n, "sibling-path"))
            continue
        unverified.append(n)
    keep = ("id", "title", "slug", "publishedPath", "draft", "parentId")
    if hits:
        res = {"page": {k: hits[0][0].get(k) for k in keep if k in hits[0][0]}, "match": hits[0][1]}
        if len(hits) > 1:
            res["note"] = f"{len(hits)} pages resolve to {CATALOGUE_PATH}; using the first — confirm"
        return res
    if unverified:
        return {"page": None, "candidates": [{k: n.get(k) for k in keep if k in n} for n in unverified],
                "note": f"slug '{segs[-1]}' found inside a folder whose path is unknown: confirm with "
                        f"get_page_metadata (publishedPath) before treating it as the catalogue"}
    return {"page": None, "note": "no page at the SML catalogue path; visual knowledge must come from published "
                                  "pages, the Designer or fields"}


def catalogue(a):
    """SML component catalogue: the page at /stylesheet/components (--pages) and what it demonstrates (--tree):
    per component, how many instances and which non-text settings the examples use. Visual context only —
    the registry stays authoritative for ids, props and capabilities."""
    out = {"path": CATALOGUE_PATH}
    if a.pages:
        found = find_catalogue(a.pages)
        out.update(found)
    if a.tree:
        comps = collections.OrderedDict()
        for d in walk(load_objects(a.tree)):
            inst = d.get("instanceDetails") if isinstance(d, dict) else None
            if not isinstance(inst, dict) or not kind_of(inst.get("name") or ""):
                continue
            e = comps.setdefault(inst["name"], {"instances": 0, "settings": []})
            e["instances"] += 1
            st = {p["name"] + ("" if not p.get("group") else ""): p["value"] for p in inst.get("props") or []
                  if p.get("hasOverride") and isinstance(p.get("value"), (bool, int, float))
                  or (p.get("hasOverride") and isinstance(p.get("value"), str) and UUID.fullmatch(p["value"] or ""))}
            if st:
                e["settings"].append(st)
        out["components"] = comps
        out["order"] = list(comps)
    dump(out)


def compose(a):
    """Page-level composition check for a planned spec (advisory, no scoring): the section sequence, runs of
    the same component, and — for sections whose spec declares a 'shape' with items — registered components
    whose repeats could carry those items (fixed counts, count switches and confirmed knowledge configs)."""
    spec = json.load(open(a.spec, encoding="utf-8"))
    sel = {c["id"]: c for c in selection_from(a.selection)["components"]}
    kn = payload_from(a.knowledge, ("knowledge",)) if a.knowledge else {}
    kc = kn.get("components") or {}
    seq = [(it["label"], it["component"]) for it in spec
           if it.get("component") and not it.get("remove") and not it.get("skip")]
    names = [sel.get(c, {}).get("name", c) for _, c in seq]
    runs, i = [], 0
    while i < len(names):
        j = i
        while j + 1 < len(names) and names[j + 1] == names[i]:
            j += 1
        if j - i + 1 >= 3:
            runs.append({"component": names[i], "sections": [seq[k][0] for k in range(i, j + 1)]})
        i = j + 1
    common = collections.Counter(names).most_common(1)
    advice = []
    for r in runs:
        advice.append(f"{len(r['sections'])} consecutive '{r['component']}' sections ({', '.join(r['sections'])}): "
                      "reconsider — check repeat/card/comparison components for the structured ones; keep the run "
                      "only if the content genuinely calls for the same presentation")
    if common and len(names) >= 5 and common[0][1] / len(names) > 0.5:
        advice.append(f"'{common[0][0]}' carries {common[0][1]} of {len(names)} sections: the page may read as "
                      "monotonous")

    reinvestigate = []

    def usable_configs(c):
        """Confirmed configs that pass config_check (current fingerprint)."""
        k = kc.get(c["id"]) or {}
        cfgs, problem = config_check(k, c)
        if problem:
            if c["name"] not in [r["component"] for r in reinvestigate]:
                reinvestigate.append(reinvestigate_entry(c["name"], k, problem, c["id"]))
            return [], True
        return [cf for cf in cfgs if cf.get("status") == "confirmed"], False

    def repeats(c):
        out = []
        conf, stale = usable_configs(c)
        for base, cap in (c.get("capacity") or {}).items():
            ws = " ".join(c.get("warnings") or [])
            fixed = f"'{base}' repeats" in ws and "fixed-count" in ws
            sw = "count-switch" in ws and f"'{base}'" in ws
            shows = sorted({n for cf in conf
                            for d in (cf.get("values") or {}).values()
                            for b, n in ((d or {}).get("shows") or {}).items() if b.lower() == base.lower()})
            out.append({"base": base, "max": cap["max"], "fixed": fixed, "switch": sw, "shows": shows, "stale": stale,
                        "cms": "cms-content" in ws, "noWrite": "no-writable-content" in ws})
        return out

    options = []
    for it in spec:
        shape = it.get("shape") or {}
        n = shape.get("items")
        purpose = shape.get("purpose")
        if not (n or purpose) or not it.get("component"):
            continue
        cur = sel.get(it["component"], {})
        cands = []
        for c in sel.values():
            if c["kind"] != "section" or c["id"] == it["component"]:
                continue
            k = kc.get(c["id"]) or {}
            ws = " ".join(c.get("warnings") or [])
            if purpose and purpose in (k.get("bestFor") or []) and not c.get("capacity") \
                    and "cms-content" not in ws and "no-writable-content" not in ws:
                # layout alternatives by purpose (e.g. media beside text) — placeholder images do not count
                # against a component: they are kept in the draft and listed for production review
                cands.append({"component": c["name"], "repeats": None, "fit": "purpose layout",
                              "basis": "knowledge bestFor", "purpose": "match", "visual": k.get("visual"),
                              **({"placeholderImage": True} if any("image" in x for x in c.get("content") or [])
                                 else {})})
            if not n or cur.get("capacity"):
                continue                              # repeat layouts only for item lists not yet in repeats
            for r in repeats(c):
                if r["cms"] or r["noWrite"]:
                    continue
                if r["shows"]:
                    fit = "fits" if n in r["shows"] else ("regroup to " + "/".join(map(str, r["shows"])))
                    basis = "confirmed config"
                elif r["switch"]:
                    fit, basis = "investigate count switch", ("stale config — reinvestigate" if r["stale"]
                                                             else "unconfirmed")
                elif r["fixed"]:
                    fit, basis = ("fits" if n == r["max"] else f"always {r['max']}: regroup or split"), "fixed count"
                else:
                    fit, basis = ("fits" if n <= r["max"] else f"max {r['max']}"), "per-item visibility"
                if purpose and purpose in (k.get("notFor") or []):
                    continue                          # knowledge says this layout misrepresents the purpose
                bf = k.get("bestFor") or []
                match = (None if not purpose else "match" if purpose in bf
                         else ("other: " + ", ".join(bf)) if bf else "unknown")
                cands.append({"component": c["name"], "repeats": f"{r['base']} ×{r['max']}", "fit": fit,
                              "basis": basis, "purpose": match, "visual": k.get("visual")})
        prank = lambda p: 0 if p == "match" else 2 if (p or "").startswith("other") else 1
        cands.sort(key=lambda x: (prank(x.get("purpose")), x["fit"] not in ("fits", "purpose layout"),
                                  x["basis"] not in ("confirmed config", "knowledge bestFor")
                                  and not x["basis"].startswith(("fixed", "per-item")), x["component"]))
        if not cands and not n:
            continue
        options.append({"section": it["label"], "current": cur.get("name"), "items": n,
                        "kind": shape.get("kind"), "candidates": cands})
    for r in reinvestigate:
        advice.append(f"{r['component']}: stored configuration ignored — {r['reason']}")
    dump({"sequence": names, "runs": runs, "advice": advice, "alternatives": options,
          **({"reinvestigate": reinvestigate} if reinvestigate else {})})


# ----------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("registry-build")
    s.add_argument("--components", required=True)
    s.add_argument("--site-id", required=True)
    s.add_argument("--site-name", required=True)
    s.add_argument("--existing-paths", default="")
    s.add_argument("--mcp-version", required=True)
    s.add_argument("--out-dir", required=True)
    s = sub.add_parser("selection-load")
    s.add_argument("--readback", required=True)
    s.add_argument("--site-id")
    s = sub.add_parser("registry-verify")
    s.add_argument("--readback", required=True)
    s.add_argument("--expected", required=True)
    s = sub.add_parser("knowledge-build")
    s.add_argument("--in", dest="in_", required=True)
    s.add_argument("--site-id", required=True)
    s.add_argument("--out", required=True)
    s.add_argument("--exists", action="store_true")
    s.add_argument("--selection")
    s.add_argument("--reviewed", default="", help="component ids whose knowledge was re-checked: restamp sig")
    s = sub.add_parser("starter")
    s.add_argument("--pages", nargs="+", required=True)
    s = sub.add_parser("starter-check")
    s.add_argument("--tree", required=True)
    s = sub.add_parser("links")
    s.add_argument("--pages", nargs="+", required=True)
    s.add_argument("--locales", required=True)
    s.add_argument("--href", action="extend", nargs="+", required=True)
    s.add_argument("--out")
    s = sub.add_parser("select-context")
    s.add_argument("--selection", required=True)
    s.add_argument("--knowledge")
    s.add_argument("--ids", default="")
    for n in ("exec-needs", "exec-build"):
        s = sub.add_parser(n)
        s.add_argument("--selected", required=True)
        s.add_argument("--details", nargs="+", required=True)
        s.add_argument("--trees", nargs="*", default=[])
        s.add_argument("--variants")
        s.add_argument("--resolve", default="")
        if n == "exec-needs":
            s.add_argument("--investigate", default="", help="component ids whose definition tree to read "
                                                            "(count switches, conditional repeats)")
        if n == "exec-build":
            s.add_argument("--out", required=True)
    s = sub.add_parser("writes-build")
    s.add_argument("--exec", required=True)
    s.add_argument("--spec", required=True)
    s.add_argument("--out", required=True)
    s.add_argument("--links")
    s.add_argument("--report")
    s.add_argument("--plan", action="store_true", help="validate before any Webflow change; writes no call")
    s.add_argument("--native-links", action="store_true",
                   help="write internal links as native page links (link_mode page + pageId); off by default because Webflow MCP 2.2 rejects page mode on component props")
    s.add_argument("--knowledge", help="knowledge (configs: confirmed repeat counts per setting)")
    s.add_argument("--selection", help="selection registry: needed to check config fingerprints; without it "
                                       "stored configs are not used")
    s = sub.add_parser("ids")
    s.add_argument("--result", required=True)
    s = sub.add_parser("verify-page")
    s.add_argument("--tree", required=True)
    s.add_argument("--call", required=True)
    s.add_argument("--expect")
    s.add_argument("--exec", help="execution.json: also report visible default text left on the live page")
    s.add_argument("--knowledge", help="knowledge (configs) so repeats hidden by a confirmed setting are not leftovers")
    s.add_argument("--spec", help="spec.json: leftovers the spec accepted with a reason are not reported")
    s.add_argument("--selection", help="selection registry: needed to check config fingerprints; without it "
                                       "stored configs are not used")
    s = sub.add_parser("catalogue")
    s.add_argument("--pages", nargs="*")
    s.add_argument("--tree")
    s = sub.add_parser("compose")
    s.add_argument("--spec", required=True)
    s.add_argument("--selection", required=True)
    s.add_argument("--knowledge")
    a = ap.parse_args()
    {"registry-build": registry_build, "selection-load": selection_load, "registry-verify": registry_verify, "knowledge-build": knowledge_build,
     "starter": starter, "starter-check": starter_check, "links": links, "select-context": select_context, "exec-needs": exec_needs, "exec-build": exec_build,
     "writes-build": writes_build, "ids": ids, "verify-page": verify_page, "catalogue": catalogue,
     "compose": compose}[a.cmd](a)


if __name__ == "__main__":
    main()
