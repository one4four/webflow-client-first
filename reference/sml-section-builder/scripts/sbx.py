#!/usr/bin/env python3
"""sbx.py - SML Section Builder v6 compiler (site-agnostic, standard library only).

Every deterministic step of Section Builder lives here: registry generation and
verification, DSL parsing, validation and lints, build planning (insert waves),
id mapping, property writes, verification by readback, rollback and decompiling.
The skill (SKILL.md) only orchestrates Webflow MCP calls and makes judgements.

Subcommands (run with -h for details):
  registry-build   components + definition trees + target page -> registry files + write call
  registry-verify  stored registry (read_instruction result) vs generated payload
  registry-load    read_instruction result -> local registry.json
  check            parse + validate + lint DSL (no Webflow); used by Mode B preview
  build            DSL -> state.json + wave 1 insert call
  next             ingest a wave result (file or ids) -> next wave, or props + finalize calls
  verify           readback (finalize result) vs plan -> report, corrective call or rollback
  rollback         state -> remove calls for elements this build created
  rollback-check   rollback result -> removed roots gone, pre-existing content unchanged
  decompile        page/element tree -> DSL
  target-check     page tree -> wrapper element for a non-default target page

This script carries no site data. All ids come from MCP results passed as files.
"""
import argparse
import datetime
import difflib
import hashlib
import json
import os
import re
import sys

SKILL_VERSION = "6.0.0"
SCHEMA = "4.0"          # payload schema of sml-section-builder-registry/data/components.md

REGISTRY = "sml-section-builder-registry"        # Agent Instructions folder owned by this skill
REGISTRY_NAME = "SML Section Builder Registry"   # display name (root title and descriptions)
PATH_STUB = f"{REGISTRY}/SKILL.md"
PATH_V6 = f"{REGISTRY}/data/components.md"

WRITABLE = {"variant", "textContent", "string", "richText", "boolean", "link",
            "image", "headingTag", "id", "visibility", "number", "altText"}
UUIDISH = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$|^[0-9a-f]{24}$")


class SbxError(Exception):
    pass


def die(msg, code=1):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def dump(path, obj):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# MCP result files
#
# The harness saves large tool results either as plain text (one or more
# concatenated JSON objects, one per action) or as a JSON array of
# {"type":"text","text":...} blocks. Small results may be written by the agent
# from the result itself. All shapes are accepted here.
# ---------------------------------------------------------------------------

def _concat_objects(text):
    dec = json.JSONDecoder()
    out, i, n = [], 0, len(text)
    while i < n:
        while i < n and text[i] in " \t\r\n,":
            i += 1
        if i >= n:
            break
        if text[i] not in "{[":
            j = text.find("{", i)
            if j < 0:
                break
            i = j
            continue
        obj, i = dec.raw_decode(text, i)
        if isinstance(obj, list):
            out.extend(obj)
        else:
            out.append(obj)
    return out


def load_mcp(path):
    """Return a list of per-action result objects ({label, action, result|error})
    or, for builder tools, the list of build results."""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    stripped = text.lstrip()
    objs = None
    if stripped.startswith("["):
        try:
            arr = json.loads(stripped)
            if arr and all(isinstance(x, dict) and x.get("type") == "text" and "text" in x for x in arr):
                objs = _concat_objects("".join(x["text"] for x in arr))
            else:
                objs = arr
        except json.JSONDecodeError:
            objs = None
    if objs is None:
        objs = _concat_objects(text)
    flat = []
    for o in objs:
        if isinstance(o, list):
            flat.extend(o)
        else:
            flat.append(o)
    return flat


def by_label(objs):
    out = {}
    for o in objs:
        if isinstance(o, dict) and "label" in o:
            out.setdefault(o["label"], o)
    return out


# ---------------------------------------------------------------------------
# Tree helpers
# ---------------------------------------------------------------------------

def walk_elements(node):
    """Yield every element node of an element tree (children only)."""
    stack = [node]
    while stack:
        n = stack.pop()
        yield n
        kids = n.get("children") or []
        stack.extend(reversed(kids))


def walk_instance(inst):
    """Yield an instanceDetails node and every nested slot child (pre-order)."""
    yield inst
    for s in inst.get("slots") or []:
        for c in s.get("children") or []:
            yield from walk_instance(c)


def tree_root(result_obj):
    r = result_obj.get("result")
    if isinstance(r, list) and r:
        r = r[0]
    if isinstance(r, dict) and "data" in r:
        return r["data"]
    raise SbxError(f"no tree in result {result_obj.get('label')!r}")


# ---------------------------------------------------------------------------
# Registry build
# ---------------------------------------------------------------------------

def alias_of(name):
    if name.startswith("__dev — "):
        return name[len("__dev — "):].strip().lower()
    if name.startswith("sml__") or name in ("Navigation", "global-styles"):
        return name.strip().lower()
    return None


def is_helper(name):
    return name.startswith("🚫 __dev — ")


def norm_name(s):
    return s.replace("\u00a0", " ").replace("\\u2014", "—")


def prop_key(p):
    return f"{p['group']}.{p['name']}" if p.get("group") else p["name"]


def components_from(path):
    objs = load_mcp(path)
    for o in objs:
        r = o.get("result") if isinstance(o, dict) else None
        if isinstance(r, list) and r and isinstance(r[0], dict) and "props" in r[0]:
            return r
    raise SbxError("no get_all_components result found (need includeProps + includeVariants)")


def definition_bindings(def_root, comp_id_by_name):
    """From a component definition tree return
       bindings: parentPropId -> (childComponentName, childPropId)
       slots: [slotElementId,...] in DOM order (plus first class)"""
    bindings, slots = {}, []
    for el in walk_elements(def_root):
        if el.get("type") == "Slot":
            slots.append({"id": el["id"]["element"], "cls": (el.get("styleNames") or [None])[0]})
        det = el.get("instanceDetails")
        if det:
            for p in det.get("props") or []:
                v = p.get("value")
                if isinstance(v, dict) and v.get("sourceType") == "prop":
                    bindings.setdefault(v["propId"], (det["name"], p["propId"]))
    return bindings, slots


def runtime_slot_names(tree_root_node):
    """Map (componentName, slotId) -> runtime slot name from instances on a page."""
    names = {}
    for el in walk_elements(tree_root_node):
        det = el.get("instanceDetails")
        if not det:
            continue
        for inst in walk_instance(det):
            for s in inst.get("slots") or []:
                names.setdefault((inst["name"], s["id"]["slot"]), s["name"])
    return names


def instance_defaults(tree_root_node):
    """propId -> value for props never overridden on page instances (fallback defaults)."""
    seen = {}
    for el in walk_elements(tree_root_node):
        det = el.get("instanceDetails")
        if not det:
            continue
        for inst in walk_instance(det):
            for p in inst.get("props") or []:
                if not p.get("hasOverride") and not isinstance(p.get("value"), dict):
                    seen.setdefault(p["propId"], p["value"])
    return seen


def find_wrapper(page_root, cls="page-wrapper"):
    hits = [el for el in walk_elements(page_root)
            if el.get("type") != "ComponentInstance" and cls in (el.get("styleNames") or [])]
    if len(hits) != 1:
        raise SbxError(f"expected exactly one .{cls} element on the target page, found {len(hits)}")
    return hits[0]["id"]["element"]


def digest_of(obj):
    return hashlib.md5(json.dumps(obj, sort_keys=True, ensure_ascii=False,
                                  separators=(",", ":")).encode()).hexdigest()[:12]


def load_display_names(path):
    """display-name result file, or an agent-written map {slotElementId: name|null}."""
    with open(path, encoding="utf-8") as f:
        text = f.read().strip()
    if text.startswith("{") and '"label"' not in text[:200]:
        return json.loads(text)
    dn = {}
    for o in load_mcp(path):
        r = o.get("result")
        r = r[0] if isinstance(r, list) and r else r
        data = (r or {}).get("data") or {}
        if data.get("element_id"):
            dn[data["element_id"]["element"]] = data.get("display_name")
    return dn


def load_probe(path):
    """slot-probe builder result -> {slotId: runtime name, '_roots': [element ids]}"""
    out = {"_roots": []}
    for o in load_mcp(path):
        if not isinstance(o, dict) or o.get("status") != "success":
            continue
        data = o.get("data") or {}
        if data.get("id", {}).get("element"):
            out["_roots"].append(data["id"]["element"])
        for s in (data.get("instanceDetails") or {}).get("slots") or []:
            out[s["id"]["slot"]] = s["name"]
    return out


def registry_build_obj(components, elements, site_id, page_id, display_names=None, probed=None):
    comps = []
    for c in components:
        c = dict(c)
        c["name"] = norm_name(c["name"])
        comps.append(c)
    by_name = {c["name"]: c for c in comps}
    by_id = {c["id"]: c for c in comps}
    labels = by_label(elements)
    if "page" not in labels:
        raise SbxError("elements file has no 'page' result (target page tree)")
    page = tree_root(labels["page"])
    wrapper = find_wrapper(page)
    slotnames = runtime_slot_names(page)
    inst_defaults = instance_defaults(page)
    display_names = display_names or {}

    defs = {}
    for lab, o in labels.items():
        if lab.startswith("def:"):
            cid = lab[4:]
            if "error" in o:
                raise SbxError(f"definition tree {cid} failed: {o['error']}")
            defs[cid] = tree_root(o)

    # option resolution through bindings (memoised)
    bind_cache = {}

    def binds(cid):
        if cid not in bind_cache:
            if cid in defs:
                bind_cache[cid] = definition_bindings(defs[cid], None)
            else:
                bind_cache[cid] = None
        return bind_cache[cid]

    def own_options(comp):
        return {v["name"]: v["id"] for v in comp.get("variants") or []}

    def resolve(comp, prop_id, depth=0):
        """-> (options dict, owner name or None, basis)"""
        b = binds(comp["id"])
        if b is not None:
            hit = b[0].get(prop_id)
            if hit and depth < 6:
                child = by_name.get(norm_name(hit[0]))
                if child:
                    cp = next((p for p in child.get("props") or [] if p["id"] == hit[1]), None)
                    if cp and cp["type"] == "variant":
                        opts, owner, basis = resolve(child, cp["id"], depth + 1)
                        return opts, owner or child["name"], "binding"
            return own_options(comp), None, "definition"
        # no definition tree: fall back to a non-base default's owning component
        p = next((p for p in comp.get("props") or [] if p["id"] == prop_id), {})
        dv = p.get("defaultValue")
        if isinstance(dv, str) and dv != "base":
            for other in comps:
                if any(v["id"] == dv for v in other.get("variants") or []):
                    if other["id"] != comp["id"]:
                        return own_options(other), other["name"], "default-owner (unverified)"
        return own_options(comp), None, "own (unverified: no definition tree)"

    aliases, out, problems = {}, {}, []
    for comp in comps:
        name = comp["name"]
        al = alias_of(name)
        if al is None or is_helper(name):
            continue
        if al in aliases:
            raise SbxError(f"alias collision: {al!r} ({aliases[al]} / {name})")
        aliases[al] = name
        props, slot_props = {}, []
        for p in comp.get("props") or []:
            if p["type"] == "slot":
                slot_props.append(p)
                continue
            key = prop_key(p)
            if key in props:
                raise SbxError(f"prop key collision on {name!r}: {key!r}")
            e = {"id": p["id"], "type": p["type"]}
            if "defaultValue" in p:
                dv = p["defaultValue"]
                if isinstance(dv, str) and len(dv) > 160:
                    e["default"] = dv[:160]
                    e["defaultTruncated"] = True
                elif isinstance(dv, dict) and "innerText" in dv:
                    e["default"] = {"innerText": dv["innerText"][:160]}
                    e["defaultTruncated"] = len(dv["innerText"]) > 160
                else:
                    e["default"] = dv
            elif p["id"] in inst_defaults:
                e["default"] = inst_defaults[p["id"]]
                e["defaultBasis"] = "page instance"
            if p["type"] == "variant":
                opts, owner, basis = resolve(comp, p["id"])
                e["options"] = opts
                if owner:
                    e["owner"] = owner
                if "unverified" in basis:
                    e["optionsBasis"] = basis
                    problems.append(f"{name}.{key}: options {basis}")
            if p["type"] not in WRITABLE:
                e["writable"] = False
            props[key] = e
        entry = {"id": comp["id"], "kind": "container" if slot_props else "leaf", "props": props}
        if slot_props:
            b = binds(comp["id"])
            def_slots = b[1] if b else []
            slots = []
            for s in def_slots:
                nm, basis = slotnames.get((name, s["id"])), "catalogue"
                if not nm and (probed or {}).get(s["id"]):
                    nm, basis = probed[s["id"]], "probe"
                if not nm and s["id"] in display_names:
                    # live rule: runtime slot name = display name, else the slot's first class
                    if display_names[s["id"]]:
                        nm, basis = display_names[s["id"]], "display-name"
                    elif s.get("cls"):
                        nm, basis = s["cls"], "class (inferred)"
                slots.append({"name": nm or None, "id": s["id"], "basis": basis if nm else None})
            if not def_slots:
                problems.append(f"{name}: has slot props but no definition tree; slot names unknown")
            seen_names = set()
            for sl in slots:
                if sl["name"] and sl["name"] in seen_names:
                    sl["unreachable"] = True      # insert_in_slot matches by name: only the first is reachable
                seen_names.add(sl["name"])
            if any(sl.get("unreachable") for sl in slots):
                problems.append(f"{name}: duplicate slot names {sorted({x['name'] for x in slots if x.get('unreachable')})}; only the first such slot is reachable through MCP")
            entry["slots"] = slots
        prim = primary_prop(props)
        if prim:
            entry["primary"] = prim
        link = next((k for k, v in props.items() if v["type"] == "link"), None)
        if link:
            entry["link"] = link
        out[name] = entry

    body = {"aliases": dict(sorted(aliases.items())), "components": dict(sorted(out.items()))}
    reg = {
        "schema": SCHEMA,
        "kind": "sml-section-builder-registry",
        "site": {"id": site_id},
        "target": {"pageId": page_id, "wrapperId": wrapper, "wrapperClass": "page-wrapper"},
        "generated": {"at": now(), "skillVersion": SKILL_VERSION},
        "digest": digest_of(body),
        **body,
    }
    missing_slots = [s["id"] for c in out.values() for s in c.get("slots", []) if not s["name"]]
    return reg, problems, missing_slots


def primary_prop(props):
    if "Text" in props and props["Text"]["type"] in ("textContent", "string"):
        return "Text"
    for k, v in props.items():
        if v["type"] == "richText":
            return k
    tc = [k for k, v in props.items() if v["type"] == "textContent" and "." not in k]
    if len(tc) == 1:
        return tc[0]
    for k, v in props.items():
        if v["type"] == "string" and "code" in k.lower():
            return k
    return None


def fenced(title, intro, obj, compact=True):
    js = json.dumps(obj, ensure_ascii=False, separators=(",", ":")) if compact else json.dumps(obj, ensure_ascii=False, indent=1)
    return f"# {title}\n\n{intro}\n\n```json\n{js}\n```\n"


def stub_md(reg, size):
    return f"""# {REGISTRY_NAME}

**Machine generated by sml-section-builder v{SKILL_VERSION}. Do not edit by hand.**
Every file under `{REGISTRY}/` belongs to sml-section-builder (`initialize SML registry`).

| File | Content |
|---|---|
| `{PATH_V6}` | Component registry, schema `{SCHEMA}` (aliases, components, props, slots, defaults, option owners). |

| Field | Value |
|---|---|
| Site ID | `{reg['site']['id']}` |
| Build target page | `{reg['target']['pageId']}` |
| Build target wrapper | `{reg['target']['wrapperId']}` |
| Aliases | {len(reg['aliases'])} |
| Digest | `{reg['digest']}` |
| Generated | `{reg['generated']['at']}` |
| Payload size | {size} bytes |

Regenerate whenever components, props, variants or slots change,
the build target page or wrapper changes, or the registry was copied from another site.
"""


def registry_build(a):
    components = components_from(a.components)
    elements = load_mcp(a.elements)
    dn = load_display_names(a.display_names) if a.display_names else {}
    probed = load_probe(a.probe_result) if a.probe_result else {}
    reg, problems, missing = registry_build_obj(components, elements, a.site_id, a.page_id, dn, probed)
    os.makedirs(a.out_dir, exist_ok=True)
    if missing and not a.display_names:
        acts = []
        for cname, e in reg["components"].items():
            for s in e.get("slots", []):
                if not s["name"]:
                    acts.append({"label": f"slot:{s['id']}", "get_display_name": {
                        "element_id": {"component": e["id"], "element": s["id"]},
                        "scope_component_id": e["id"]}})
        dump(os.path.join(a.out_dir, "slotnames.call.json"), {"tool": "data_element_tool", "pageId": a.page_id, "actions": acts})
        print(json.dumps({"status": "needs-slot-names", "missing": len(missing),
                          "call": os.path.join(a.out_dir, "slotnames.call.json"),
                          "next": "send the call; write {slotElementId: display_name|null} from the result (or save the result file); rerun with --display-names"}, indent=1))
        sys.exit(3)
    if missing and not a.probe_result:
        comps_missing = sorted({n for n, e in reg["components"].items() if any(not s["name"] for s in e.get("slots", []))})
        ppage = a.probe_page or a.page_id
        pparent = a.probe_parent or reg["target"]["wrapperId"]
        acts = [{"build_label": f"probe:{reg['components'][n]['id']}", "action_type": "insert_in_element",
                 "parent_element_id": {"component": ppage, "element": pparent},
                 "creation_position": "append", "return_component_info": True, "component_schema": {"name": n}}
                for n in comps_missing]
        dump(os.path.join(a.out_dir, "slotprobe.call.json"), {"tool": "data_component_builder", "siteId": a.site_id,
                                                             "pageId": ppage, "actions": acts})
        problems.append(f"slot names unresolved for {comps_missing}; these components are unusable until probed")
    if probed.get("_roots"):
        ppage = a.probe_page or a.page_id
        dump(os.path.join(a.out_dir, "slotprobe.cleanup.json"), {"tool": "data_element_tool", "siteId": a.site_id, "pageId": ppage,
             "actions": [{"label": f"remove probe {i+1}", "remove_element": {"id": {"component": ppage, "element": el}}}
                         for i, el in enumerate(probed["_roots"])]})
    v6_md = fenced(f"{REGISTRY_NAME} · components",
                   f"Machine generated by sml-section-builder v{SKILL_VERSION}. Schema `{SCHEMA}` · site `{reg['site']['id']}` · digest `{reg['digest']}`. Do not edit.",
                   reg)
    unchanged = False
    if a.current:
        try:
            cur = registry_from_read(a.current)
            body_ok = digest_of({"aliases": cur.get("aliases"), "components": cur.get("components")}) == reg["digest"]
            if body_ok and cur.get("digest") == reg["digest"] and cur.get("site", {}).get("id") == reg["site"]["id"] \
                    and cur.get("target") == reg["target"] and cur.get("schema") == SCHEMA:
                unchanged = True
                reg["generated"] = cur.get("generated") or reg["generated"]
                v6_md = fenced(f"{REGISTRY_NAME} · components",
                               f"Machine generated by sml-section-builder v{SKILL_VERSION}. Schema `{SCHEMA}` · site `{reg['site']['id']}` · digest `{reg['digest']}`. Do not edit.",
                               reg)
        except (SbxError, json.JSONDecodeError, KeyError):
            unchanged = False
    stub = stub_md(reg, len(v6_md.encode()))
    for nm, body in ((PATH_STUB, stub), (PATH_V6, v6_md)):
        if len(body.encode()) > 256 * 1024:
            die(f"{nm} is over the 256 KB Agent Instruction limit")
    if v6_md.count("```") != 2:
        die(f"{PATH_V6} must contain exactly one fenced block")
    existing = set(filter(None, (a.existing_paths or "").split(",")))
    descs = {PATH_STUB: f"{REGISTRY_NAME} — index. Machine generated by sml-section-builder, do not edit.",
             PATH_V6: f"{REGISTRY_NAME} — components, schema {SCHEMA}. Machine generated by sml-section-builder, do not edit."}
    actions = []
    for path, body in ((PATH_STUB, stub), (PATH_V6, v6_md)):
        if path == PATH_V6 and unchanged:
            continue          # stored registry already matches: no rewrite
        verb = "update_instruction" if path in existing else "create_instruction"
        act = {"site_id": reg["site"]["id"], "kind": "skill", "path": path, "markdown": body,
               "description": descs[path]}
        actions.append({"label": f"{verb.split('_')[0]} {path}", verb: act})
    # repeated so the harness saves the result to a file for registry-verify (~100K characters)
    reps = max(1, -(-110_000 // max(1, len(v6_md))))
    for i in range(reps):
        actions.append({"label": "readback" if i == 0 else f"readback-{i + 1}", "read_instruction": {
            "site_id": reg["site"]["id"], "path": PATH_V6, "resolve_references": False}})
    dump(os.path.join(a.out_dir, "registry.json"), reg)
    dump(os.path.join(a.out_dir, "write.call.json"), actions)
    print(json.dumps({"status": "ok", "digest": reg["digest"], "aliases": len(reg["aliases"]),
                      "components": len(reg["components"]), "wrapper": reg["target"]["wrapperId"],
                      "problems": problems,
                      "writeCall": os.path.join(a.out_dir, "write.call.json"),
                      "registryUnchanged": unchanged,
                      "actions": [x["label"] for x in actions]}, indent=1, ensure_ascii=False))


def bootstrap_elements(a):
    """components file -> data_element_tool call: target page tree + definition trees."""
    comps = components_from(a.components)
    acts = [{"label": "page", "get_all_elements": {"depth": -1}}]
    skipped = []
    for c in comps:
        name = norm_name(c["name"])
        if alias_of(name) is None or is_helper(name):
            continue
        if not c.get("props"):
            skipped.append(name)
            continue
        acts.append({"label": f"def:{c['id']}", "get_all_elements": {"depth": -1, "scope_component_id": c["id"]}})
    aliasable = sum(1 for c in comps if alias_of(norm_name(c["name"])) and not is_helper(norm_name(c["name"])))
    call = {"tool": "data_element_tool", "pageId": a.page_id, "actions": acts}
    dump(a.out, call)
    print(json.dumps({"status": "ok", "components": len(comps), "aliasable": aliasable,
                      "definitionTrees": len(acts) - 1, "skippedWithoutProps": skipped, "call": a.out},
                     indent=1, ensure_ascii=False))


def parse_registry_md(md):
    blocks = re.findall(r"```json\n(.*?)\n```", md, re.S)
    if len(blocks) != 1:
        raise SbxError(f"registry markdown must contain exactly one fenced json block (found {len(blocks)})")
    return json.loads(blocks[0])


def registry_from_read(path):
    """Accept a read_instruction result file, a raw markdown file or a registry.json."""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    t = text.lstrip()
    if t.startswith("{") and '"schema"' in t[:200] and '"components"' in t:
        try:
            return json.loads(t)
        except json.JSONDecodeError:
            pass
    if "```json" in text and not t.startswith(("{", "[")):
        return parse_registry_md(text)
    for o in load_mcp(path):
        r = o.get("result") if isinstance(o, dict) else None
        if isinstance(r, dict) and r.get("path") == PATH_V6:
            return parse_registry_md(r["markdown"])
    raise SbxError(f"no {PATH_V6} found in {path}")


def check_registry(reg, site_id=None):
    if reg.get("schema") != SCHEMA:
        raise SbxError(f"registry schema {reg.get('schema')!r}; this skill (v{SKILL_VERSION}) requires {SCHEMA}. Run 'initialize SML registry'.")
    for k in ("site", "target", "aliases", "components", "digest"):
        if k not in reg:
            raise SbxError(f"registry missing {k!r}")
    if site_id and reg["site"]["id"] != site_id:
        raise SbxError("registry site mismatch: the registry belongs to another site. Re-run 'initialize SML registry'.")
    body = {"aliases": reg["aliases"], "components": reg["components"]}
    if digest_of(body) != reg["digest"]:
        raise SbxError("registry digest mismatch: payload altered. Re-run 'initialize SML registry'.")


def registry_verify(a):
    expected = load_json(a.expected)
    stored = None
    for o in load_mcp(a.readback):
        r = o.get("result") if isinstance(o, dict) else None
        if isinstance(r, dict) and r.get("path") == PATH_V6:
            stored = parse_registry_md(r["markdown"])
    if stored is None:
        stored = registry_from_read(a.readback)
    probs = []
    for o in load_mcp(a.readback):
        if isinstance(o, dict) and str(o.get("label", "")).startswith(("create ", "update ")) and o.get("error"):
            err = o["error"]
            probs.append(f"{o['label']}: {err.get('message') if isinstance(err, dict) else err}")
    body = {"aliases": stored.get("aliases"), "components": stored.get("components")}
    if digest_of(body) != expected["digest"] or stored.get("digest") != expected["digest"]:
        if stored.get("digest") != expected["digest"]:
            probs.append(f"stored digest {stored.get('digest')} != expected {expected['digest']}")
        for name in sorted(set(expected["components"]) | set(stored.get("components") or {})):
            if expected["components"].get(name) != (stored.get("components") or {}).get(name):
                probs.append(f"component differs: {name}")
        if expected["aliases"] != stored.get("aliases"):
            probs.append("aliases differ")
    res = {"status": "ok" if not probs else "mismatch", "digest": expected["digest"], "problems": probs}
    print(json.dumps(res, indent=1, ensure_ascii=False))
    sys.exit(0 if not probs else 1)


def registry_load(a):
    reg = registry_from_read(a.read)
    check_registry(reg, a.site_id)
    dump(a.out, reg)
    print(json.dumps({"status": "ok", "digest": reg["digest"], "aliases": len(reg["aliases"]),
                      "target": reg["target"]}, indent=1))


# ---------------------------------------------------------------------------
# DSL parser
# ---------------------------------------------------------------------------

class Node:
    __slots__ = ("alias", "name", "content", "link", "props", "children", "slot_blocks",
                 "line", "is_container_line", "slot_header", "comp", "path", "writes",
                 "slot_children", "id", "deferred", "inline", "kind", "parent")

    def __init__(self, line):
        self.alias = None
        self.name = None
        self.content = None
        self.link = None
        self.props = []        # [(key, raw value, quoted)]
        self.children = []     # for single-slot containers / pending
        self.slot_blocks = []  # [(slotName, [Node])] for multi-slot
        self.line = line
        self.is_container_line = False
        self.slot_header = None
        self.comp = None
        self.path = None
        self.writes = []
        self.slot_children = {}
        self.id = None
        self.deferred = []
        self.inline = False
        self.kind = None
        self.parent = None


BARE = re.compile(r"[A-Za-z0-9_\-.—/]+")


def _strip_comment(s):
    out, q = [], False
    i = 0
    while i < len(s):
        ch = s[i]
        if ch == '"' and (i == 0 or s[i - 1] != "\\"):
            q = not q
        if ch == "#" and not q and (i == 0 or s[i - 1].isspace()):
            break
        out.append(ch)
        i += 1
    return "".join(out).rstrip()


def _read_quoted(s, i, lineno):
    assert s[i] == '"'
    j = i + 1
    buf = []
    while j < len(s):
        if s[j] == "\\" and j + 1 < len(s):
            nxt = s[j + 1]
            buf.append({"n": "\n", "t": "\t", '"': '"', "\\": "\\"}.get(nxt, nxt))
            j += 2
            continue
        if s[j] == '"':
            return "".join(buf), j + 1
        buf.append(s[j])
        j += 1
    raise SbxError(f"line {lineno}: unterminated quote")


def _parse_props(s, i, lineno):
    assert s[i] == "{"
    i += 1
    props = []
    while True:
        while i < len(s) and s[i].isspace():
            i += 1
        if i >= len(s):
            raise SbxError(f"line {lineno}: unterminated {{")
        if s[i] == "}":
            return props, i + 1
        if s[i] == '"':
            key, i = _read_quoted(s, i, lineno)
        else:
            m = re.compile(r"[^=\s}]+").match(s, i)
            if not m:
                raise SbxError(f"line {lineno}: bad prop key near {s[i:i+20]!r}")
            key, i = m.group(0), m.end()
        while i < len(s) and s[i].isspace():
            i += 1
        if i >= len(s) or s[i] != "=":
            raise SbxError(f"line {lineno}: expected '=' after prop {key!r}")
        i += 1
        while i < len(s) and s[i].isspace():
            i += 1
        if i < len(s) and s[i] == '"':
            val, i = _read_quoted(s, i, lineno)
            quoted = True
        else:
            m = re.compile(r"[^\s}]+").match(s, i)
            if not m:
                raise SbxError(f"line {lineno}: missing value for {key!r}")
            val, i, quoted = m.group(0), m.end(), False
        props.append((key, val, quoted))


def _parse_content(s, i, lineno):
    assert s[i] == "("
    i += 1
    content, link = None, None
    while i < len(s) and s[i].isspace():
        i += 1
    if i < len(s) and s[i] == '"':
        content, i = _read_quoted(s, i, lineno)
    else:
        m = re.compile(r"[^)→]*?(?=\s*(→|->|\)))").match(s, i)
        if m:
            content, i = m.group(0).strip(), m.end()
            if content == "":
                content = None
    while i < len(s) and s[i].isspace():
        i += 1
    if s.startswith("→", i) or s.startswith("->", i):
        i += 1 if s[i] == "→" else 2
        while i < len(s) and s[i].isspace():
            i += 1
        if i < len(s) and s[i] == '"':
            link, i = _read_quoted(s, i, lineno)
        else:
            m = re.compile(r"[^)\s]+").match(s, i)
            link, i = (m.group(0), m.end()) if m else ("", i)
    while i < len(s) and s[i].isspace():
        i += 1
    if i >= len(s) or s[i] != ")":
        raise SbxError(f"line {lineno}: unterminated ( … )")
    return content, link, i + 1


def parse_items(s, lineno):
    """Parse one line into [Node]; the last may be a container opener (trailing ':')."""
    items, i = [], 0
    while True:
        while i < len(s) and s[i].isspace():
            i += 1
        if i >= len(s):
            break
        n = Node(lineno)
        if s[i] == '"':
            n.alias, i = _read_quoted(s, i, lineno)
        else:
            m = BARE.match(s, i)
            if not m:
                raise SbxError(f"line {lineno}: unexpected {s[i:i+15]!r}")
            n.alias, i = m.group(0), m.end()
        while True:
            if i < len(s) and s[i] == "[":
                j = s.find("]", i)
                if j < 0:
                    raise SbxError(f"line {lineno}: unterminated [name]")
                n.name = s[i + 1:j].strip()
                i = j + 1
            elif i < len(s) and s[i] == "(":
                n.content, n.link, i = _parse_content(s, i, lineno)
            elif i < len(s) and s[i] == "{":
                p, i = _parse_props(s, i, lineno)
                n.props.extend(p)
            else:
                break
        if i < len(s) and s[i] == ":":
            n.is_container_line = True
            i += 1
            items.append(n)
            rest = s[i:].strip()
            if rest:
                inline = parse_items(rest, lineno)
                if any(x.is_container_line for x in inline):
                    raise SbxError(f"line {lineno}: nested containers must use block form (one per line)")
                n.children.extend(inline)
            break
        items.append(n)
    return items


def parse_dsl(text):
    """Return list of top-level Nodes. Multi-slot detection happens in compile."""
    roots = []
    stack = []  # (indent, node)
    for lineno, raw in enumerate(text.splitlines(), 1):
        if not raw.strip() or raw.strip().startswith("```"):
            continue
        line = _strip_comment(raw.replace("\t", "    "))
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        items = parse_items(line.strip(), lineno)
        if not items:
            continue
        while stack and stack[-1][0] >= indent:
            stack.pop()
        target = stack[-1][1].children if stack else roots
        target.extend(items)
        last = items[-1]
        if last.is_container_line:
            stack.append((indent, last))
    return roots


# ---------------------------------------------------------------------------
# Compile: resolve, validate, writes
# ---------------------------------------------------------------------------

def _norm(s):
    return re.sub(r"\s+", " ", s.strip().lower())


def resolve_key(comp_name, entry, key):
    props = entry["props"]
    k = key.replace(" :: ", ".").replace("::", ".")
    if k in props:
        return k, None
    low = {_norm(x): x for x in props}
    if _norm(k) in low:
        return low[_norm(k)], None
    bare = [x for x in props if x.split(".")[-1] == k or _norm(x.split(".")[-1]) == _norm(k)]
    if len(bare) == 1:
        return bare[0], None
    if len(bare) > 1:
        return None, f"{comp_name}: prop {key!r} is ambiguous; use one of {bare}"
    close = difflib.get_close_matches(k, list(props), n=3, cutoff=0.5)
    hint = f" (closest: {', '.join(close)})" if close else ""
    return None, f"{comp_name}: unknown prop {key!r}{hint}"


TRUE = {"true", "yes", "on", "visible", "shown", "show"}
FALSE = {"false", "no", "off", "hidden", "hide"}


def coerce(comp_name, key, pe, raw, quoted):
    """-> (normalised value for comparison, write value dict) or raise SbxError"""
    t = pe["type"]
    pid = pe["id"]
    if pe.get("writable") is False:
        raise SbxError(f"{comp_name}.{key}: prop type {t!r} cannot be written through MCP")
    if t == "variant":
        opts = pe.get("options") or {}
        oid = None
        if raw in opts:
            oid = opts[raw]
        else:
            low = {_norm(k): v for k, v in opts.items()}
            if _norm(raw) in low:
                oid = low[_norm(raw)]
            elif raw in opts.values():
                oid = raw
        if oid is None:
            close = difflib.get_close_matches(raw, list(opts), n=3, cutoff=0.4)
            raise SbxError(f"{comp_name}.{key}: {raw!r} is not an option ({', '.join(close) or ', '.join(list(opts)[:8])})")
        return oid, {"prop_id": pid, "type": "string", "string_value": oid}
    if t in ("boolean", "visibility"):
        r = raw.strip().lower()
        if r in TRUE:
            b = True
        elif r in FALSE:
            b = False
        else:
            raise SbxError(f"{comp_name}.{key}: expected a boolean, got {raw!r}")
        return b, {"prop_id": pid, "type": "boolean", "boolean_value": b}
    if t == "richText":
        return {"innerText": raw}, {"prop_id": pid, "type": "richText", "rich_text_inner_text": raw}
    if t == "number":
        try:
            num = float(raw)
        except ValueError:
            raise SbxError(f"{comp_name}.{key}: expected a number, got {raw!r}")
        num = int(num) if num.is_integer() else num
        return num, {"prop_id": pid, "type": "number", "number_value": num}
    if t == "link":
        mode = "url"
        to = raw
        if raw.startswith("mailto:"):
            mode, to = "email", raw[7:]
        elif raw.startswith("tel:"):
            mode, to = "phone", raw[4:]
        return {"mode": mode, "to": to}, {"prop_id": pid, "type": "link", "link_mode": mode, "link_to": to}
    if t == "headingTag":
        if not re.fullmatch(r"h[1-6]", raw.strip().lower()):
            raise SbxError(f"{comp_name}.{key}: heading tag must be h1-h6, got {raw!r}")
        v = raw.strip().lower()
        return v, {"prop_id": pid, "type": "string", "string_value": v}
    if t == "image":
        if not re.fullmatch(r"[0-9a-f]{24}", raw.strip()):
            raise SbxError(f"{comp_name}.{key}: image needs a Webflow asset id (24 hex), got {raw!r}")
        return raw.strip(), {"prop_id": pid, "type": "string", "string_value": raw.strip()}
    # textContent, string, id, altText
    return raw, {"prop_id": pid, "type": "string", "string_value": raw}


def equals_default(pe, value):
    if "default" not in pe or pe.get("defaultTruncated"):
        return False
    d = pe["default"]
    if pe["type"] == "variant":
        return value == d
    if pe["type"] == "link":
        return isinstance(d, dict) and d.get("mode") == value.get("mode") and d.get("to") == value.get("to")
    return value == d


class Compiled:
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.roots = []
        self.nodes = []


def compile_dsl(text, reg):
    c = Compiled()
    try:
        roots = parse_dsl(text)
    except SbxError as e:
        c.errors.append(str(e))
        return c
    comps = reg["components"]

    def resolve_node(n, path, parent):
        n.path = path
        n.parent = parent
        al = n.alias.lower()
        name = reg["aliases"].get(al)
        if not name:
            close = difflib.get_close_matches(al, list(reg["aliases"]), n=3, cutoff=0.5)
            c.errors.append(f"line {n.line}: unknown component {n.alias!r}" + (f" (closest: {', '.join(close)})" if close else ""))
            return
        e = comps[name]
        n.comp = name
        n.kind = e["kind"]
        c.nodes.append(n)
        seen = {}
        # props
        for key, raw, quoted in n.props:
            k, err = resolve_key(name, e, key)
            if err:
                c.errors.append(f"line {n.line}: {err}")
                continue
            try:
                norm, w = coerce(name, k, e["props"][k], raw, quoted)
            except SbxError as ex:
                c.errors.append(f"line {n.line}: {ex}")
                continue
            seen[k] = (norm, w)
        if n.content is not None:
            pk = e.get("primary")
            if not pk:
                c.errors.append(f"line {n.line}: {n.alias} has no primary text prop for ( … )")
            else:
                norm, w = coerce(name, pk, e["props"][pk], n.content, True)
                if pk in seen:
                    c.warnings.append(f"line {n.line}: {n.alias} {pk} set twice; ( … ) wins")
                seen[pk] = (norm, w)
        if n.link is not None:
            lk = e.get("link")
            if not lk:
                c.errors.append(f"line {n.line}: {n.alias} has no link prop for →")
            else:
                norm, w = coerce(name, lk, e["props"][lk], n.link, True)
                seen[lk] = (norm, w)
        n.writes = []
        for k, (norm, w) in seen.items():
            pe = e["props"][k]
            n.writes.append({"key": k, "value": norm, "write": w, "default": equals_default(pe, norm)})
        # children / slots
        slots = e.get("slots") or []
        if n.children and n.kind != "container":
            c.errors.append(f"line {n.line}: {n.alias} is not a container (it has no slot) but has children")
            return
        if n.kind == "container":
            if any(s["name"] is None for s in slots):
                c.errors.append(f"line {n.line}: {n.alias}: runtime slot names unknown (run the slot probe in 'initialize SML registry')")
                return
            names = [s["name"] for s in slots if not s.get("unreachable")]
            if len(names) < len(slots):
                c.warnings.append(f"line {n.line}: {n.alias} has {len(slots)} slots but only {len(names)} reachable by name through MCP")
            n.slot_children = {s: [] for s in names}
            headers = {}
            for ch in n.children:
                if not ch.is_container_line or ch.props or ch.content is not None:
                    continue
                target = slot_header_target(ch.alias, slots)
                if target is None:
                    continue
                if isinstance(target, SbxError):
                    c.errors.append(f"line {ch.line}: {n.alias}: {target}")
                    headers[ch] = None
                else:
                    headers[ch] = target
            if len(names) == 1 and not headers:
                n.slot_children[names[0]] = list(n.children)
                if len(slots) > 1 and len(n.children) > 1:
                    c.warnings.append(
                        f"line {n.line}: all {len(n.children)} children go into {n.alias}'s first slot '{names[0]}'; "
                        f"its other {len(slots) - 1} slots share that name and cannot be filled through MCP")
            else:
                for ch in n.children:
                    if ch in headers:
                        if headers[ch] is not None:
                            n.slot_children[headers[ch]].extend(ch.children)
                    elif len(names) == 1:
                        n.slot_children[names[0]].append(ch)
                    else:
                        c.errors.append(f"line {ch.line}: {n.alias} has slots {names}; put children under a slot line such as '{names[0]}:'")
            idx = 0
            for s in names:
                for ch in n.slot_children[s]:
                    resolve_node(ch, f"{path}.{idx}", n)
                    idx += 1

    for i, r in enumerate(roots):
        resolve_node(r, f"s{i+1}", None)
        c.roots.append(r)
    if not c.errors:
        lint(c, reg)
    return c


SLOT_POS = re.compile(r"^(.+?)\s*#(\d+)$")


def slot_header_target(label, slots):
    """Slot header text -> runtime slot name, None (not a header) or SbxError (unaddressable slot).

    'content' / 'tab-2' name a slot directly. 'Slot #3' names the third slot called 'Slot';
    only the first slot of a duplicated name is reachable, because Webflow MCP resolves
    insert_in_slot and component_schema.slots by name, first match (verified live 2026-11-02).
    """
    reachable = [s["name"] for s in slots if not s.get("unreachable")]
    if label in reachable:
        return label
    m = SLOT_POS.match(label or "")
    if not m:
        return None
    base, k = m.group(1).strip(), int(m.group(2))
    same = [s for s in slots if s["name"] == base]
    if not same:
        return None
    if k < 1 or k > len(same):
        return SbxError(f"there is no slot '{base} #{k}' (it has {len(same)} slot(s) named '{base}')")
    if k == 1:
        return base
    return SbxError(
        f"slot '{base} #{k}' shares its name with slot '{base} #1'. Webflow MCP addresses slots by name "
        f"and always resolves to the first match, so slots 2-{len(same)} cannot be filled headlessly. "
        f"Fill them in the Designer, or give the slots unique names in the component definition")


def _children(n):
    out = []
    for s, kids in (n.slot_children or {}).items():
        out.extend(kids)
    return out


def _w(n, keypart):
    for w in n.writes:
        if w["key"].split(".")[-1].lower() == keypart.lower():
            return w
    return None


def _opt_label(reg, n, w):
    pe = reg["components"][n.comp]["props"][w["key"]]
    for k, v in (pe.get("options") or {}).items():
        if v == w["value"]:
            return k
    return None


def lint(c, reg):
    """SML convention checks (warnings). Errors are reserved for invalid builds."""
    W = c.warnings
    for n in c.nodes:
        al = reg["aliases"]
        a = n.alias.lower()
        e = reg["components"][n.comp]
        # images must set a ratio
        if a == "image":
            ratio_keys = [k for k in e["props"] if "ratio" in k.lower()]
            if ratio_keys and not any(w["key"] in ratio_keys for w in n.writes):
                W.append(f"line {n.line}: image without {ratio_keys[0]!r} (every image must set its ratio)")
        # text casing
        for w in n.writes:
            v = w["write"].get("string_value") or w["write"].get("rich_text_inner_text")
            if isinstance(v, str) and w["key"] == e.get("primary") and len(v) > 3 and v.upper() == v and re.search(r"[A-Z]{4}", v):
                W.append(f"line {n.line}: text in all caps ({v[:30]!r}); use sentence case, CSS handles uppercase")
        # leaves left with placeholder text
        if n.kind == "leaf" and e.get("primary") and a not in ("icon",):
            pk = e["primary"]
            if not any(w["key"] == pk for w in n.writes):
                d = e["props"][pk].get("default")
                dtext = d.get("innerText") if isinstance(d, dict) else d
                if isinstance(dtext, str) and dtext.strip():
                    W.append(f"line {n.line}: {n.alias} keeps its default text ({dtext[:40]!r})")
        if e.get("link") and n.kind == "leaf":
            lk = e["link"]
            if not any(w["key"] == lk for w in n.writes):
                d = e["props"][lk].get("default")
                if isinstance(d, dict) and d.get("to") in ("#", "", None) and a == "button":
                    W.append(f"line {n.line}: button has no link (default '#')")
        if n.kind != "container":
            continue
        kids = _children(n)
        # row rules
        if a == "row":
            cols = [k for k in kids if k.alias.lower() == "col"]
            non = [k for k in kids if k.alias.lower() not in ("col", "hr dividing line")]
            if non:
                g = _w(n, "horizontal gap size")
                if not g or _opt_label(reg, n, g) != "no-gap":
                    W.append(f"line {n.line}: row with direct non-col children should set \"horizontal gap size\"=no-gap")
            widths = []
            for col in cols:
                d = _w(col, "Layout Desktop")
                if d:
                    lab = _opt_label(reg, col, d) or ""
                    m = re.match(r"(\d+)\s*/\s*12", lab)
                    if m:
                        widths.append(int(m.group(1)))
                    if not _w(col, "Layout Tablet") or not _w(col, "Layout Mobile"):
                        W.append(f"line {col.line}: col sets Layout Desktop but not Layout Tablet and Layout Mobile")
            if widths and len(widths) > 1 and sum(widths) > 12 and sum(widths) % 12:
                W.append(f"line {n.line}: col widths sum to {sum(widths)}; wrapping lines will not fill 12 columns evenly")
        # positional slots: one visible element each
        for s, ks in (n.slot_children or {}).items():
            if re.match(r"(grid|tab|slide)-\d+$", s) and len(ks) > 1:
                W.append(f"line {n.line}: slot {s} holds {len(ks)} elements; wrap them in a box")
        # vertical stacks: same-size consecutive single paragraphs -> rich text
        prev = None
        for k in kids:
            if prev is not None and prev.alias.lower() == "single paragraph" and k.alias.lower() == "single paragraph":
                a1, a2 = _w(prev, "Text size"), _w(k, "Text size")
                if (a1 and a1["value"]) == (a2 and a2["value"]):
                    W.append(f"line {k.line}: consecutive same-size single paragraphs; consider one \"rich text\"")
            prev = k
        # horizontal button grouping (v5.3 convention): no-gap + align=center, buttons direct children
        if a == "row" and sum(1 for k in kids if k.alias.lower() == "button") >= 2:
            al_w = _w(n, "align")
            if not al_w or _opt_label(reg, n, al_w) != "center":
                W.append(f"line {n.line}: row of buttons should set align=center (horizontal button grouping)")
        # text-align: the alignment must hold at every breakpoint (tablet/mobile have their own options)
        if a == "text-align":
            keys = [k for k in e["props"] if k.lower().startswith("text align")]
            set_keys = {w["key"] for w in n.writes}
            if set_keys & set(keys) and not set(keys) <= set_keys:
                missing = [k for k in keys if k not in set_keys]
                W.append(f"line {n.line}: text-align sets {sorted(set_keys & set(keys))[0]!r} but not "
                         f"{', '.join(missing)}; set every breakpoint so the alignment holds when text wraps")
        # spacer directly after an eyebrow (an eyebrow alias, or a paragraph using an 'eyebrow' option)
        def _is_eyebrow(k):
            return k.alias.lower() == "eyebrow" or any(
                (_opt_label(reg, k, w) or "").lower() == "eyebrow" for w in k.writes)
        for i in range(len(kids) - 1):
            if _is_eyebrow(kids[i]) and kids[i + 1].alias.lower() == "spacer":
                W.append(f"line {kids[i+1].line}: remove this spacer; an eyebrow and the heading below it take no spacer")
        # section background pairing
        if a == "section":
            st = _w(n, "Style")
            full = st and _opt_label(reg, n, st) == "Full screen"
            first = kids[0] if kids else None
            bg = first is not None and first.alias.lower() == "image" and any(
                _opt_label(reg, first, w) == "background" for w in first.writes if "ratio" in w["key"].lower())
            if full and not bg:
                W.append(f"line {n.line}: Style=\"Full screen\" expects an image with ratio 'background' as first child")
            if bg and not full:
                W.append(f"line {n.line}: background image as first child expects section Style=\"Full screen\"")


# ---------------------------------------------------------------------------
# Build planning (insert waves)
# ---------------------------------------------------------------------------

def needs_id(n):
    return n.kind == "container" or bool([w for w in n.writes if not w["default"]]) or bool(n.name)


def slot_inlineable(n, slot):
    return all(ch.kind == "container" or not needs_id(ch) for ch in n.slot_children.get(slot, []))


def schema_of(n, collect):
    """Component schema for n; collects (path) of containers inlined (pre-order)."""
    collect.append(n.path)
    sch = {"name": n.comp}
    if n.kind == "container":
        slots = []
        n.deferred = []
        for s, kids in n.slot_children.items():
            if not kids:
                continue
            if slot_inlineable(n, s):
                ch = []
                for k in kids:
                    if k.kind == "container":
                        ch.append(schema_of(k, collect))
                    else:
                        ch.append({"name": k.comp})
                        k.inline = True
                slots.append({"name": s, "children": ch})
            else:
                n.deferred.append(s)
        if slots:
            sch["slots"] = slots
    return sch


def node_index(roots):
    idx = {}

    def rec(n):
        idx[n.path] = n
        for k in _children(n):
            rec(k)
    for r in roots:
        rec(r)
    return idx


def serialise(n):
    return {"path": n.path, "alias": n.alias, "comp": n.comp, "kind": n.kind, "name": n.name,
            "writes": n.writes, "line": n.line,
            "slots": {s: [k.path for k in ks] for s, ks in (n.slot_children or {}).items()},
            "id": n.id, "inline": n.inline}


def expect_doc(state):
    """What the agent must copy from an inline wave result: per action, the distinct element ids in order."""
    return {lab: [f"{p} {state['nodes'][p]['alias']}" for p in paths] for lab, paths in state["pending"].items()}


def make_wave(state, items):
    """items: [(parentSpec, node)] -> actions + expectations"""
    acts, expect = [], {}
    wave = state["wave"] + 1
    nodes = _rehydrate(state)
    for i, (parent, path) in enumerate(items):
        n = nodes[path]
        collect = []
        sch = schema_of(n, collect)
        lab = f"w{wave}.{i+1}"
        # a leaf inside one of our own containers that needs no writes and no name needs no id:
        # skip return_component_info (its reply is ~1KB of defaults) and expect no id back
        light = (n.kind == "leaf" and not needs_id(n) and parent["type"] == "slot"
                 and path not in state["roots"])
        a = {"build_label": lab, "return_component_info": not light, "component_schema": sch,
             "creation_position": parent.get("position", "append")}
        if light:
            collect = []
        if parent["type"] == "element":
            a.update({"action_type": "insert_in_element",
                      "parent_element_id": {"component": state["pageId"], "element": parent["element"]}})
        else:
            a.update({"action_type": "insert_in_slot", "slot_name": parent["slot"],
                      "parent_element_id": {"component": state["pageId"], "element": parent["element"]}})
        acts.append(a)
        expect[lab] = collect
        # persist deferred slots computed by schema_of
        for p in collect:
            state["nodes"][p]["deferred"] = list(nodes[p].deferred)
        for p in [x for x in state["nodes"]]:
            if nodes[p].inline:
                state["nodes"][p]["inline"] = True
    state["wave"] = wave
    state["pending"] = expect
    call = {"tool": "data_component_builder", "siteId": state["siteId"], "pageId": state["pageId"],
            "actions": acts}
    return call


class _N:
    pass


def _rehydrate(state):
    """Rebuild light Node objects from state for schema generation."""
    nodes = {}
    for p, d in state["nodes"].items():
        n = Node(d["line"])
        n.path, n.alias, n.comp, n.kind, n.name = p, d["alias"], d["comp"], d["kind"], d["name"]
        n.writes, n.id, n.inline = d["writes"], d.get("id"), d.get("inline", False)
        nodes[p] = n
    for p, d in state["nodes"].items():
        nodes[p].slot_children = {s: [nodes[k] for k in ks] for s, ks in d["slots"].items()}
    return nodes


def build(a):
    reg = load_json(a.registry)
    check_registry(reg)
    with open(a.dsl, encoding="utf-8") as f:
        text = f.read()
    comp = compile_dsl(text, reg)
    report = {"errors": comp.errors, "warnings": comp.warnings}
    if comp.errors:
        print(json.dumps({"status": "invalid", **report}, indent=1, ensure_ascii=False))
        sys.exit(1)
    if a.strict and comp.warnings:
        print(json.dumps({"status": "lint-failed", **report}, indent=1, ensure_ascii=False))
        sys.exit(1)
    page = a.page_id or reg["target"]["pageId"]
    if a.parent_element:
        parent = {"type": "slot" if a.slot else "element", "element": a.parent_element,
                  "slot": a.slot, "position": a.position}
    else:
        if a.page_id and a.page_id != reg["target"]["pageId"] and not a.wrapper:
            die("a non-default --page-id needs --wrapper (run target-check on that page's tree)")
        parent = {"type": "element", "element": a.wrapper or reg["target"]["wrapperId"], "position": a.position}
    nodes = node_index(comp.roots)
    state = {"skillVersion": SKILL_VERSION, "siteId": reg["site"]["id"], "pageId": page,
             "registryDigest": reg["digest"], "parent": parent, "wave": 0,
             "roots": [r.path for r in comp.roots],
             "nodes": {p: serialise(n) for p, n in nodes.items()},
             "namePrefix": a.prefix, "created": [], "status": "building", "warnings": comp.warnings,
             "dsl": text}
    for r in comp.roots:
        if r.name is None:
            state["warnings"].append(f"line {r.line}: top-level {r.alias} has no [name]; give generated sections a descriptive name")
    if a.page_tree and parent["type"] == "element":
        # snapshot of the parent's existing children: verify proves they are untouched
        root = None
        for o in load_mcp(a.page_tree):
            if isinstance(o, dict) and o.get("action") not in (None, "get_all_elements"):
                continue
            try:
                root = tree_root(o)
                break
            except (SbxError, AttributeError, KeyError, TypeError):
                continue
        if root is None:
            die("--page-tree holds no page tree")
        par = next((el for el in walk_elements(root) if (el.get("id") or {}).get("element") == parent["element"]), None)
        if par is None:
            die(f"target element {parent['element']} is not on the page tree; regenerate the registry or check --wrapper")
        state["before"] = [ch["id"]["element"] for ch in par.get("children") or []]
    call = make_wave(state, [(parent, p) for p in state["roots"]])
    dump(a.state, state)
    dump(a.out, call)
    total = len(state["nodes"])
    print(json.dumps({"status": "ok", "wave": 1, "actions": len(call["actions"]), "instances": total,
                      "writes": sum(len([w for w in n['writes'] if not w['default']]) for n in state['nodes'].values()),
                      "warnings": state["warnings"], "call": a.out, "expect": expect_doc(state)}, indent=1, ensure_ascii=False))


def check(a):
    reg = load_json(a.registry)
    check_registry(reg)
    with open(a.dsl, encoding="utf-8") as f:
        text = f.read()
    comp = compile_dsl(text, reg)
    status = "invalid" if comp.errors else "ok"
    out = {"status": status, "errors": comp.errors, "warnings": comp.warnings}
    if not comp.errors:
        out["sections"] = len(comp.roots)
        out["instances"] = len(comp.nodes)
        out["unnamed"] = [r.line for r in comp.roots if r.name is None]
    print(json.dumps(out, indent=1, ensure_ascii=False))
    sys.exit(0 if not comp.errors else 1)


# ---------------------------------------------------------------------------
# Wave ingestion
# ---------------------------------------------------------------------------

def ids_from_result(path):
    """Builder result file -> {label: {"status", "ids": [...], "error"}}"""
    out = {}
    for o in load_mcp(path):
        if not isinstance(o, dict) or "build_label" not in o:
            continue
        lab = o["build_label"]
        if o.get("status") != "success":
            out[lab] = {"status": "error", "error": o.get("message"), "ids": []}
            continue
        data = o.get("data") or {}
        seq = []
        if data.get("id", {}).get("element"):
            seq.append(data["id"]["element"])

        def rec(inst):
            for s in inst.get("slots") or []:
                el = (s.get("id") or {}).get("element")
                if el and el not in seq:
                    seq.append(el)
                for ch in s.get("children") or []:
                    rec(ch)
        det = data.get("instanceDetails")
        if det:
            rec(det)
        out[lab] = {"status": "success", "ids": seq, "detail": bool(det)}
    return out


def ids_from_text(path):
    """Agent-written ids file: JSON {label: [ids]} or lines 'label id id …' / 'label ERROR msg'."""
    with open(path, encoding="utf-8") as f:
        text = f.read().strip()
    if text.startswith("{"):
        d = json.loads(text)
        return {k: ({"status": "success", "ids": v} if isinstance(v, list) else v) for k, v in d.items()}
    out = {}
    for line in text.splitlines():
        parts = line.split()
        if not parts:
            continue
        if len(parts) > 1 and parts[1].upper() == "ERROR":
            out[parts[0]] = {"status": "error", "error": " ".join(parts[2:]), "ids": []}
        else:
            out[parts[0]] = {"status": "success", "ids": parts[1:]}
    return out


def next_step(a):
    state = load_json(a.state)
    if state["status"] != "building":
        die(f"state is {state['status']!r}, not building")
    got = ids_from_result(a.result) if a.result else ids_from_text(a.ids)
    expect = state["pending"]
    failures, created_now = [], []
    for lab, paths in expect.items():
        g = got.get(lab)
        if g is None:
            failures.append(f"{lab}: no result")
            continue
        if g["status"] != "success":
            failures.append(f"{lab}: {g.get('error')}")
            continue
        ids = g["ids"]
        for x in ids:
            if not UUIDISH.match(x):
                failures.append(f"{lab}: {x!r} is not an element id")
        if len(ids) != len(paths):
            failures.append(f"{lab}: expected {len(paths)} element ids ({', '.join(paths)}), got {len(ids)}")
            continue
        for p, el in zip(paths, ids):
            state["nodes"][p]["id"] = el
        if paths and (state["wave"] == 1 or paths[0] in state["roots"]):
            created_now.append({"path": paths[0], "id": ids[0]})
    if state["wave"] == 1:
        state["created"].extend(created_now)
    if failures:
        state["status"] = "failed"
        state["failure"] = {"wave": state["wave"], "problems": failures}
        dump(a.state, state)
        rb = rollback_call(state)
        dump(a.out, rb)
        print(json.dumps({"status": "build-failed", "wave": state["wave"], "problems": failures,
                          "rollback": a.out if rb["actions"] else None,
                          "note": "send the rollback call now (it removes only elements this build created)" if rb["actions"]
                          else "nothing this build created is known; nothing to roll back"}, indent=1, ensure_ascii=False))
        sys.exit(2)
    # next wave
    nodes = state["nodes"]
    items = []
    for lab, paths in expect.items():
        for p in paths:
            d = nodes[p]
            for s in d.get("deferred", []):
                for k in d["slots"][s]:
                    items.append(({"type": "slot", "element": d["id"], "slot": s, "position": "append"}, k))
    if items:
        call = make_wave(state, items)
        dump(a.state, state)
        dump(a.out, call)
        print(json.dumps({"status": "next-wave", "wave": state["wave"], "actions": len(call["actions"]),
                          "call": a.out, "expect": expect_doc(state)}, indent=1, ensure_ascii=False))
        return
    # done inserting: props + finalize
    state["status"] = "inserted"
    props_acts = []
    missing = []
    for p, d in nodes.items():
        ws = [w["write"] for w in d["writes"] if not w["default"]]
        if not ws:
            continue
        if not d.get("id"):
            missing.append(p)
            continue
        props_acts.append({"label": f"props {p}", "set_component_instance_prop_values": {
            "element_id": {"component": state["pageId"], "element": d["id"]}, "values": ws}})
    if missing:
        die(f"internal: instances with writes but no id: {missing}")
    props_call = {"tool": "data_component_props_tool", "siteId": state["siteId"], "pageId": state["pageId"],
                  "actions": props_acts}
    fin = finalize_call(state)
    base = os.path.splitext(a.out)[0]
    dump(base + ".props.json", props_call)
    dump(base + ".finalize.json", fin)
    dump(a.state, state)
    print(json.dumps({"status": "inserted", "instances": len(nodes), "propActions": len(props_acts),
                      "propsCall": base + ".props.json", "finalizeCall": base + ".finalize.json"}, indent=1))


def finalize_call(state, pad=0):
    acts = []
    pref = state.get("namePrefix") or ""
    for p, d in state["nodes"].items():
        if d.get("name") and d.get("id"):
            acts.append({"label": f"name {p}", "set_display_name": {
                "element_id": {"component": state["pageId"], "element": d["id"]},
                "display_name": f"{pref}{d['name']}"}})
    acts.append({"label": "verify:page", "get_all_elements": {"depth": -1}})
    queries = [{"label": f"root {r}", "element_id": {"component": state["pageId"], "element": state["nodes"][r]["id"]},
                "children_depth": -1} for r in state["roots"]]
    acts.append({"label": "verify:roots", "query_elements": {"queries": queries}})
    for i in range(pad):
        acts.append({"label": f"verify:roots-copy-{i+2}", "query_elements": {"queries": queries}})
    return {"tool": "data_element_tool", "siteId": state["siteId"], "pageId": state["pageId"], "actions": acts}


def rollback_call(state):
    acts = []
    for c in state.get("created", []):
        acts.append({"label": f"rollback {c['path']}", "remove_element": {
            "id": {"component": state["pageId"], "element": c["id"]}}})
    if acts:
        qs = [{"label": f"gone {c['path']}", "element_id": {"component": state["pageId"], "element": c["id"]}}
              for c in state["created"]]
        if state.get("before") is not None and state["parent"]["type"] == "element":
            qs.append({"label": "parent", "element_id": {"component": state["pageId"],
                                                          "element": state["parent"]["element"]}, "children_depth": 1})
        acts.append({"label": "rollback:check", "query_elements": {"queries": qs}})
    return {"tool": "data_element_tool", "siteId": state["siteId"], "pageId": state["pageId"], "actions": acts}


def rollback_check(a):
    """Rollback result -> every removed root is gone; the parent's other children are exactly as before."""
    state = load_json(a.state)
    objs = load_mcp(a.result)
    labels = by_label(objs)
    probs = []
    for c in state.get("created", []):
        lab = f"rollback {c['path']}"
        o = labels.get(lab)
        if o is None or o.get("error"):
            probs.append(f"{lab}: {(o or {}).get('error') or 'no result'}")
    chk = labels.get("rollback:check")
    data = []
    if chk and not chk.get("error"):
        r = chk.get("result")
        r = r[0] if isinstance(r, list) and r else r
        data = (r or {}).get("data") or []
    else:
        probs.append("rollback:check missing or failed (re-read before trusting the page)")
    byq = {q.get("label"): q for q in data}
    for c in state.get("created", []):
        q = byq.get(f"gone {c['path']}")
        if q is None or q.get("total_matches", len(q.get("matches") or [])) != 0:
            probs.append(f"{c['path']} ({c['id']}) still on the page")
    untouched = None
    if state.get("before") is not None and "parent" in byq:
        m = (byq["parent"].get("matches") or [None])[0] or {}
        kids = [(ch.get("id") or {}).get("element") for ch in m.get("children") or []]
        untouched = kids == state["before"]
        if not untouched:
            probs.append("the parent's children differ from the snapshot taken before the build")
    out = {"status": "rolled-back" if not probs else "check-failed", "problems": probs,
           "preExistingUntouched": untouched}
    if not probs:
        state["status"] = "rolled-back"
        dump(a.state, state)
    print(json.dumps(out, indent=1, ensure_ascii=False))
    sys.exit(0 if not probs else 1)


def rollback(a):
    state = load_json(a.state)
    call = rollback_call(state)
    dump(a.out, call)
    state["status"] = "rolling-back"
    dump(a.state, state)
    print(json.dumps({"status": "ok", "removes": len(call["actions"]) - (1 if call["actions"] else 0),
                      "call": a.out}, indent=1))


# ---------------------------------------------------------------------------
# Verification by readback
# ---------------------------------------------------------------------------

def _readback_value(v):
    return v


def norm_cmp(t, v):
    if t == "richText":
        if isinstance(v, dict):
            return (v.get("innerText") or "").replace("\r\n", "\n").strip()
        return (v or "").strip()
    if t == "link":
        if isinstance(v, dict):
            return (v.get("mode"), v.get("to") or "")
        return v
    if isinstance(v, str):
        return v.strip()
    return v


def verify(a):
    state = load_json(a.state)
    reg = load_json(a.registry)
    objs = load_mcp(a.result)
    labels = by_label(objs)
    problems, corrective, named_fail = [], [], []
    # display-name results (non-fatal)
    for lab, o in labels.items():
        if lab.startswith("name ") and "error" in o:
            named_fail.append(f"{lab}: {o['error'].get('message') if isinstance(o['error'], dict) else o['error']}")
    rr = labels.get("verify:roots")
    if not rr or "error" in rr:
        print(json.dumps({"status": "unverified", "reason": "readback failed",
                          "detail": (rr or {}).get("error"), "advice": "structure kept; resend the finalize call once (read-only). Never roll back because a read failed."}, indent=1))
        sys.exit(4)
    res = rr["result"]
    res = res[0] if isinstance(res, list) else res
    data = {q["label"]: q for q in (res.get("data") or [])}
    checked = 0
    nodes = state["nodes"]
    for r in state["roots"]:
        q = data.get(f"root {r}")
        if not q or not q.get("matches"):
            problems.append(f"{r}: root element not found")
            continue
        det = q["matches"][0].get("instanceDetails")
        stack = [(r, det)]
        while stack:
            p, inst = stack.pop()
            d = nodes[p]
            if inst is None or inst.get("name") != d["comp"]:
                problems.append(f"{p}: expected {d['comp']}, found {inst and inst.get('name')}")
                continue
            got = {pp["propId"]: pp for pp in inst.get("props") or []}
            entry = reg["components"][d["comp"]]
            written = set()
            for w in d["writes"]:
                pe = entry["props"][w["key"]]
                written.add(pe["id"])
                g = got.get(pe["id"])
                checked += 1
                if g is None:
                    problems.append(f"{p} {w['key']}: not in readback")
                    continue
                want = norm_cmp(pe["type"], w["value"])
                have = norm_cmp(pe["type"], g.get("value"))
                if want != have:
                    problems.append(f"{p} {w['key']}: expected {want!r}, found {have!r}")
                    if d.get("id"):
                        corrective.append((d["id"], w["write"]))
            for pid, g in got.items():
                if g.get("hasOverride") and pid not in written:
                    problems.append(f"{p}: unexpected override on prop {g.get('name')}")
            # children
            rs = inst.get("slots") or []
            reg_slot_id = {}
            for sl in entry.get("slots") or []:
                if sl.get("name") and not sl.get("unreachable"):
                    reg_slot_id.setdefault(sl["name"], sl.get("id"))
            for s, kids in d["slots"].items():
                # match by slot id: names can repeat (duplicate-named slots)
                hit = next((x for x in rs if (x.get("id") or {}).get("slot") == reg_slot_id.get(s)), None)
                if hit is None:
                    hit = next((x for x in rs if x.get("name") == s), None)
                rk = (hit or {}).get("children") or []
                if len(rk) != len(kids):
                    problems.append(f"{p} slot {s}: expected {len(kids)} children, found {len(rk)}")
                for kp, kinst in zip(kids, rk):
                    stack.append((kp, kinst))
    # placement: roots must be children of the parent element on the page tree
    placement = None
    pg = labels.get("verify:page")
    if pg and "error" not in pg and state["parent"]["type"] == "element":
        try:
            root = tree_root(pg)
            parent = next((el for el in walk_elements(root) if el["id"]["element"] == state["parent"]["element"]), None)
            if parent is None:
                problems.append("parent element not found on page")
            else:
                kids = [ch["id"]["element"] for ch in parent.get("children") or []]
                want = [nodes[r]["id"] for r in state["roots"]]
                pos = [kids.index(x) if x in kids else -1 for x in want]
                if -1 in pos:
                    problems.append("a built section is not a child of the target wrapper")
                elif pos != sorted(pos):
                    problems.append("built sections are out of order in the wrapper")
                placement = {"wrapperChildren": len(kids), "positions": pos}
                if state.get("before") is not None:
                    mine = set(want)
                    others = [x for x in kids if x not in mine]
                    placement["preExisting"] = len(state["before"])
                    if others != state["before"]:
                        missing = [x for x in state["before"] if x not in others]
                        placement["preExistingChanged"] = {
                            "missing": missing[:10], "added": [x for x in others if x not in state["before"]][:10],
                            "reordered": not missing and sorted(others) == sorted(state["before"])}
                    else:
                        placement["preExistingUntouched"] = True
        except SbxError as e:
            placement = {"skipped": str(e)}
    structural = [x for x in problems if "slot" in x or "expected __" in x or "not found" in x or "out of order" in x or "not a child" in x]
    value_only = [x for x in problems if x not in structural]
    out = {"checked": checked, "problems": problems, "nameWarnings": named_fail, "placement": placement}
    if not problems:
        state["status"] = "verified"
        dump(a.state, state)
        out["status"] = "verified"
        out["summary"] = summary(state, checked)
        print(json.dumps(out, indent=1, ensure_ascii=False))
        return
    if structural:
        state["status"] = "failed"
        state["failure"] = {"stage": "verify", "problems": problems}
        dump(a.state, state)
        rb = rollback_call(state)
        dump(a.out, rb)
        out.update({"status": "structure-mismatch", "rollback": a.out})
        print(json.dumps(out, indent=1, ensure_ascii=False))
        sys.exit(2)
    attempts = state.get("correctiveAttempts", 0)
    if attempts >= 1 or not corrective:
        state["status"] = "failed"
        state["failure"] = {"stage": "verify", "problems": problems}
        dump(a.state, state)
        rb = rollback_call(state)
        dump(a.out, rb)
        out.update({"status": "values-mismatch", "rollback": a.out,
                    "note": "a corrective write already failed to fix this; roll back"})
        print(json.dumps(out, indent=1, ensure_ascii=False))
        sys.exit(2)
    by_el = {}
    for el, w in corrective:
        by_el.setdefault(el, []).append(w)
    call = {"tool": "data_component_props_tool", "siteId": state["siteId"], "pageId": state["pageId"],
            "actions": [{"label": f"fix {el}", "set_component_instance_prop_values": {
                "element_id": {"component": state["pageId"], "element": el}, "values": ws}} for el, ws in by_el.items()]}
    state["correctiveAttempts"] = attempts + 1
    dump(a.state, state)
    dump(a.out, call)
    out.update({"status": "values-mismatch", "corrective": a.out,
                "note": "send the corrective call, then resend the finalize call and verify again"})
    print(json.dumps(out, indent=1, ensure_ascii=False))
    sys.exit(3)


def summary(state, checked):
    n = len(state["nodes"])
    s = len(state["roots"])
    return f"Build complete: {s} section{'s' if s != 1 else ''}, {n} instances, {checked}/{checked} values verified."


# ---------------------------------------------------------------------------
# Decompile
# ---------------------------------------------------------------------------

def _q(s):
    if re.fullmatch(r"[A-Za-z0-9_\-./—]+", s) and s.lower() not in TRUE | FALSE:
        return s
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def decompile_inst(inst, reg, indent=0, name=None):
    comps = reg["components"]
    alias = {v: k for k, v in reg["aliases"].items()}
    nm = inst.get("name")
    if nm not in comps:
        return [" " * indent + f"# unregistered component: {nm}"]
    e = comps[nm]
    al = alias[nm]
    head = _q(al) if " " in al else al
    if name:
        head += f"[{name}]"
    by_id = {v["id"]: (k, v) for k, v in e["props"].items()}
    content = link = None
    props = []
    for p in inst.get("props") or []:
        if p["propId"] not in by_id:
            continue
        k, pe = by_id[p["propId"]]
        v = p.get("value")
        if isinstance(v, dict) and v.get("sourceType"):
            props.append(f"# {k} is bound ({v.get('sourceType')})")
            continue
        overridden = p.get("hasOverride")
        if not overridden:
            continue
        if k == e.get("primary"):
            content = v.get("innerText") if isinstance(v, dict) else v
            continue
        if k == e.get("link") and isinstance(v, dict) and v.get("mode") in ("url", "email", "phone"):
            to = v.get("to") or ""
            link = {"email": "mailto:", "phone": "tel:"}.get(v["mode"], "") + to
            continue
        if pe["type"] == "variant":
            lab = next((ol for ol, oid in (pe.get("options") or {}).items() if oid == v), v)
            props.append(f"{_q(k)}={_q(str(lab))}")
        elif pe["type"] in ("boolean", "visibility"):
            props.append(f"{_q(k)}={'true' if v else 'false'}")
        elif pe["type"] == "richText":
            props.append(f"{_q(k)}={_q(v.get('innerText', '') if isinstance(v, dict) else str(v))}")
        elif pe["type"] == "link" and isinstance(v, dict):
            props.append(f"{_q(k)}={_q(v.get('to') or '')}")
        else:
            props.append(f"{_q(k)}={_q(str(v))}")
    comments = [x for x in props if x.startswith("#")]
    props = [x for x in props if not x.startswith("#")]
    if content is not None or link is not None:
        inner = _q(content) if content is not None else ""
        if link is not None:
            inner += ("→" if inner else "→") + link
        head += f"({inner})"
    if props:
        head += "{ " + " ".join(props) + " }"
    lines = []
    slots = [s for s in inst.get("slots") or [] if s.get("children")]
    if e["kind"] == "container" and slots:
        lines.append(" " * indent + head + ":")
        multi = len(e.get("slots") or []) > 1
        rs_all = inst.get("slots") or []
        for s in slots:
            ind = indent + 2
            if multi:
                same = [x for x in rs_all if x.get("name") == s["name"]]
                if len(same) > 1:
                    k = same.index(s) + 1
                    lab = s["name"] if k == 1 else _q(f"{s['name']} #{k}")
                    if k > 1:
                        lines.append(" " * ind + f"# slot {lab} cannot be filled through MCP (duplicate slot name)")
                else:
                    lab = s["name"]
                lines.append(" " * ind + f"{lab}:")
                ind += 2
            for ch in s["children"]:
                lines.extend(decompile_inst(ch, reg, ind))
    else:
        lines.append(" " * indent + head)
    return lines


def decompile(a):
    reg = load_json(a.registry)
    objs = load_mcp(a.tree)
    out = []
    want = set(filter(None, (a.ids or "").split(",")))
    names = {}
    for o in objs:
        if not isinstance(o, dict):
            continue
        r = o.get("result")
        r = r[0] if isinstance(r, list) and r else r
        if not isinstance(r, dict):
            continue
        data = r.get("data")
        if isinstance(data, list):     # query_elements
            for q in data:
                for m in q.get("matches") or []:
                    if not want or m["id"]["element"] in want:
                        out.append((m["id"]["element"], m.get("instanceDetails")))
        elif isinstance(data, dict):   # get_all_elements
            for el in walk_elements(data):
                det = el.get("instanceDetails")
                if det and (not want or el["id"]["element"] in want):
                    if not want and det["name"] not in reg["components"]:
                        continue
                    out.append((el["id"]["element"], det))
    seen, lines = set(), []
    for el, det in out:
        if el in seen or det is None:
            continue
        seen.add(el)
        if not want and reg["components"].get(det["name"], {}).get("kind") != "container":
            continue
        lines.extend(decompile_inst(det, reg, 0))
        lines.append("")
    text = "\n".join(lines).rstrip() + "\n"
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(text)
    print(text)


def target_check(a):
    root = None
    for o in load_mcp(a.tree):
        try:
            root = tree_root(o)
            break
        except (SbxError, AttributeError):
            continue
    if root is None:
        die("no page tree found")
    try:
        w = find_wrapper(root, a.cls)
        print(json.dumps({"status": "ok", "wrapper": w}, indent=1))
    except SbxError as e:
        cands = [{"element": el["id"]["element"], "type": el["type"], "classes": el.get("styleNames")}
                 for el in walk_elements(root) if el.get("type") in ("Block", "DropTarget", "Section", "Container")][:12]
        print(json.dumps({"status": "ambiguous", "error": str(e), "candidates": cands}, indent=1))
        sys.exit(1)


# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("registry-build")
    s.add_argument("--components", required=True, help="saved get_all_components result (includeProps+includeVariants)")
    s.add_argument("--elements", required=True, help="saved data_element_tool result: label 'page' + 'def:<componentId>' trees")
    s.add_argument("--site-id", required=True)
    s.add_argument("--page-id", required=True, help="build target page (stylesheet/components)")
    s.add_argument("--display-names", help="saved result of slotnames.call.json, or a {slotId: name|null} map")
    s.add_argument("--probe-result", help="saved result of slotprobe.call.json (only when asked)")
    s.add_argument("--existing-paths", default="", help="comma-separated Agent Instruction paths that already exist")
    s.add_argument("--probe-page", help="page for slot-probe inserts when the target page cannot take them (e.g. a disposable draft page)")
    s.add_argument("--probe-parent", help="element on --probe-page to insert probes into (e.g. its Body)")
    s.add_argument("--current", help="saved read_instruction result for sml-section-builder-registry/data/components.md; an identical registry is not rewritten")
    s.add_argument("--out-dir", required=True)
    s = sub.add_parser("bootstrap-elements")
    s.add_argument("--components", required=True)
    s.add_argument("--page-id", required=True)
    s.add_argument("--out", required=True)
    s = sub.add_parser("registry-verify")
    s.add_argument("--readback", required=True)
    s.add_argument("--expected", required=True)
    s = sub.add_parser("registry-load")
    s.add_argument("--read", required=True)
    s.add_argument("--site-id")
    s.add_argument("--out", required=True)
    s = sub.add_parser("check")
    s.add_argument("--registry", required=True)
    s.add_argument("--dsl", required=True)
    s = sub.add_parser("build")
    s.add_argument("--registry", required=True)
    s.add_argument("--dsl", required=True)
    s.add_argument("--state", required=True)
    s.add_argument("--out", required=True)
    s.add_argument("--page-id")
    s.add_argument("--wrapper")
    s.add_argument("--parent-element", help="insert into an existing instance (with --slot) or element")
    s.add_argument("--slot")
    s.add_argument("--position", default="append", choices=["append", "prepend"])
    s.add_argument("--prefix", default="", help="display-name prefix for named instances")
    s.add_argument("--strict", action="store_true", help="treat lint warnings as errors")
    s.add_argument("--page-tree", help="saved get_all_elements result of the target page: records the parent's existing children so verify can prove them untouched")
    s = sub.add_parser("rollback-check")
    s.add_argument("--state", required=True)
    s.add_argument("--result", required=True, help="saved result of the rollback call")
    s = sub.add_parser("next")
    s.add_argument("--state", required=True)
    g = s.add_mutually_exclusive_group(required=True)
    g.add_argument("--result", help="saved builder result file")
    g.add_argument("--ids", help="agent-written ids file")
    s.add_argument("--out", required=True)
    s = sub.add_parser("verify")
    s.add_argument("--state", required=True)
    s.add_argument("--registry", required=True)
    s.add_argument("--result", required=True, help="saved finalize-call result")
    s.add_argument("--out", required=True)
    s = sub.add_parser("rollback")
    s.add_argument("--state", required=True)
    s.add_argument("--out", required=True)
    s = sub.add_parser("decompile")
    s.add_argument("--registry", required=True)
    s.add_argument("--tree", required=True)
    s.add_argument("--ids", help="comma-separated element ids to decompile")
    s.add_argument("--out")
    s = sub.add_parser("target-check")
    s.add_argument("--tree", required=True)
    s.add_argument("--cls", default="page-wrapper")
    a = ap.parse_args()
    fn = {"registry-build": registry_build, "bootstrap-elements": bootstrap_elements, "registry-verify": registry_verify, "registry-load": registry_load,
          "check": check, "build": build, "next": next_step, "verify": verify, "rollback": rollback, "rollback-check": rollback_check,
          "decompile": decompile, "target-check": target_check}[a.cmd]
    try:
        fn(a)
    except SbxError as e:
        die(str(e))


if __name__ == "__main__":
    main()
