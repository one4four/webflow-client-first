---
name: sml-page-builder
description: "Build Webflow pages from Google Docs on any SML-convention site (`Section —` / `Item —` components, Starter page) via Webflow MCP 2.2: discover what each site's components can do (catalogue, configurations), compose the page as a whole, choose components by content purpose and visual fit, adapt copy editorially, handle per-site component differences, and verify the result. Use for 'initialize/refresh SML Page Builder registry', building a page from a doc, selecting components and fetching execution details. Formerly sml-marketer."
---

# SML Page Builder (v1.0.0 — Webflow MCP 2.2)

| Thing | Version |
|---|---|
| Skill `sml-page-builder` (formerly `sml-marketer`) | `1.0.0` |
| Registry **SML Page Builder Registry** (`sml-page-builder-registry/`) | schema `3.0`, knowledge `1.0`; reads legacy `sml-marketer-registry/` schema 2.x |

The skill is site-agnostic: SML conventions and decision rules live here; component IDs, the Starter
page, link map, visual purposes and limitations live in each site's registry. Independent of
`sml-webflow`: never touches `sml-registry/*`.

**Registry files** — the **SML Page Builder Registry** (Webflow Agent Instructions, kind `skill`). Agent Instructions have no
separate display-name field: the root title `# SML Page Builder Registry` and the `SML Page Builder Registry — …`
description prefix carry the name. `registry-build` and `knowledge-build` produce this layout; never rename by hand.

```
sml-page-builder-registry/
├── SKILL.md
└── data/
    ├── knowledge.md
    └── selection.md
```

- `sml-page-builder-registry/data/selection.md` — generated catalogue of every `Section —` / `Item —` component: content areas, capacity, slots, options, toggles, `cms`, `warnings`, `digest`. **Authoritative** for what a component can hold.
- `sml-page-builder-registry/data/knowledge.md` — curated site knowledge: Starter, links, and per component `visual`, `bestFor`, `notFor`, `limits`, `cms` evidence, `execDeps`, `sig`. **Authoritative** for what a component is *for*.
- `sml-page-builder-registry/SKILL.md` — generated root.

**Execution details** (exact prop IDs/types/defaults, variant options, slots) are fetched per build for the selected components only (`execution.json`). Not cached: MCP exposes no component version (see references).

`S=scripts/spb.py`. Large MCP results are saved to files by the harness; pass those to the script. Small results come back inline: consume them directly, and if the script needs one, write it to a file **from the result itself, never retyped** (a retyped payload can be silently corrupted — `registry-verify` exists because of this). If only part is needed (e.g. `list_pages`), write a compact file with just the fields the script reads (`id`, `title`, `slug`, `draft`, `archived`, `publishedPath`, `parentId`, `collectionId`). Never add padding reads.

Tests: `python3 tests/run_tests.py` (offline, fixtures included, no Webflow access).

---

# STANDARD WORKFLOW (what a minimal request triggers)

A request needs only **which Webflow site** (name or id; resolve a name with `data_sites_tool list_sites`) and **which Google Doc**. Everything else is part of the normal workflow, without further prompting:

1. Read the Google Doc.
2. Discover the site's registry and knowledge (refresh or initialize the registry if missing or stale).
3. Find and validate the Starter page.
4. Locate the site's **`/stylesheet/components`** page **inside the Webflow project** (SML convention; a standard step on every build, not an optional extra).
5. Use that page for component discovery and visual understanding: its MCP page tree always (it works unpublished — demonstrated components and configurations); its rendered page as well when it is published, or through the existing authenticated Chrome connection.
6. Explore suitable components and configurations before rejecting any (DISCOVERY).
7. Plan the overall page composition — after the visual exploration, before committing to components (COMPOSITION, SELECTION).
8. Adapt the content to the chosen layouts (EDITORIAL MODE), keeping every intended action on a button (ACTIONS AND LINKS).
9. Build and verify the page (draft only).
10. Ask the user only when the skill genuinely cannot proceed: one batched question at the plan check (step 3b of BUILD A PAGE) for sections without a suitable component or editorial changes that would materially change meaning (similar-page link candidates may be added to that same question; otherwise the button stays unlinked and is reported).

Placeholder images are acceptable on draft builds and never disqualify an image-based component (IMAGES AND MEDIA). Rendered inspection uses the existing authenticated Chrome connection when available; never request a separate Webflow login in another browser. When rendered inspection is unavailable, continue with MCP and stored knowledge and mark visual assumptions as **unverified** — that never blocks the build.

---

# HARD RULES

1. Writes only under `sml-page-builder-registry/` (legacy files only to migrate/delete them) and, when building, the new page. Never modify components, props, variants, styles, classes, variables or existing pages. Never create elements.
2. Scope: names `Section — …` / `Item — …` (em dash; NBSP tolerated), stored verbatim. `nearMissNames` (en dash, hyphen) are reported, not used.
3. Never fabricate IDs, options, links, components, props, variants or visibility controls. Only what MCP results, `spb.py` or validated knowledge show exists.
4. Webflow calls: `webflow_guide_tool` once per task (`session_id:"start"`), then the issued `ses_…`; one `agent_id`; `context` 15–25 words; a `label` per action.
5. On `429`, auth or unexpected MCP errors: stop and report. Expected, recoverable errors are handled below.
6. Never publish. Never leave visible component default text, `#`/default links or unconfirmed links on a built page. A button for an intended action whose destination is unknown stays visible and **unlinked**, and is reported — never a guessed, default or unrelated destination.
7. **Never silently drop a source section.** Every source section ends as written, adapted (and reported), or explicitly resolved by the user (another component, leave out, defer). A page with an unresolved section is not complete.

---

# INITIALIZE / REFRESH REGISTRY (≈5 calls)

Triggers: `initialize|refresh SML Page Builder registry`, any capitalization (legacy: `… SML Marketer registry`).

1. Guide (once). In parallel: `data_sites_tool get_site` (inline: id, displayName, locales); `data_agent_instructions_tool search_instructions{limit:100}` (inline: every existing path under both registries).
2. `data_component_tool get_all_components{options:{includeProps:true}}` → saved file.
3. `python3 $S registry-build --components F --site-id ID --site-name NAME --existing-paths <all registry paths, comma-separated> --mcp-version X --out-dir out`
4. Send `out/write.call.json` verbatim as `actions` (root first; it creates the folder). Each result returns the stored markdown: confirm it contains `"digest":"<digest>"`, then save the selection result and run `python3 $S registry-verify --readback F --expected out/selection.json` — it recomputes the digest from the **stored components** and lists missing/extra/changed entries (a matching digest string alone does not prove the content arrived intact). On a mismatch, resend that action unchanged and verify again. If an action returns an upstream `500`, run `search_instructions` and resend only the actions whose path is missing (unchanged payload); never send cleanup before both are confirmed. Only then send `out/cleanup.call.json` (deletes legacy `sml-marketer-registry/` via its root, plus stale files). `knowledge.md` is never touched by a refresh.
5. Run `select-context` (below) and report counts, digest, migrated/deleted files, `nearMissNames`, warnings and knowledge health (`stale`, `obsolete`, `renamed`). Compatibility warnings the registry emits: `ambiguous-slots`, `fixed-count`, `count-switch` (a boolean such as "Amount of boxes" changes how many repeats show — which value shows how many is unverified until inspected), `cms-content` (a group filled from a CMS selection MCP cannot write), `no-writable-content` (nothing MCP can populate). Pass `get_all_components` a real page id (e.g. the Starter) when it needs one.

---

# SITE KNOWLEDGE (`knowledge.md`)

JSON, written via `knowledge-build --in F --site-id ID --selection out/selection.json [--exists] [--reviewed IDS] --out call.json`:

```json
{"starter":{"pageId":"…","title":"…","validatedAt":"…","heroComponent":"<component name>",
   "elements":{"wrapper":{"component":"…","element":"…"},"hero":{…},"navigation":{…},"footer":{…},
     "prefilled":[{"name":"Section — …","id":{…}}]}},
 "locales":{"primary":{"tag":"en","subdirectory":""},"secondary":[]},
 "links":{"/en/about":{"path":"/about-us","pageId":"…","resolution":"confirmed","note":"confirmed by <who/when>"}},
 "components":{"<id>":{"name":"…",
   "visual":"1–2 sentences: what it looks like and what it communicates",
   "visualBasis":"catalogue | fields+defaults (catalogue unavailable) | designer",
   "bestFor":["benefits","process"],"notFor":["testimonial"],
   "limits":["…"],"cms":{"status":"verified|estimated|unknown","count":0,"basis":"…"},
   "execDeps":["<nested component id>"],"sig":"(stamped by knowledge-build)",
   "configs":[{"prop":"Group.Name","type":"boolean","values":{"false":{"label":"…","shows":{"Box":6}},
      "true":{"label":"…","shows":{"Box":3}}},"status":"confirmed|inferred",
      "basis":"designer-render|live-render|site-owner|catalogue|definition-tree","evidence":"…","checkedAt":"…"}]}},
 "catalogue":{"pageId":"…","path":"/stylesheet/components","publicUrl":"ok|404 (unpublished)","readVia":"…"},
 "notes":["…"]}
```

- **Purposes** (`bestFor` / `notFor`) use this shared vocabulary, extended when needed: `hero`, `intro`, `section-intro`, `benefits`, `features`, `services`, `process`, `specifications`, `specifications-grouped`, `comparison`, `faq`, `testimonial`, `proof`, `metrics`, `case`, `story`, `challenges`, `applications`, `resources`, `logos`, `products`, `media`, `form`, `cta`, `long-text`, `limitations`, `navigation`, `listing`.
- **Discover once, reuse, validate**: Starter via `get_page_metadata`; link `pageId`s batched in one call.
- **Visual knowledge**: written from the site's `/stylesheet/components` page the first time a component is relevant to a decision, then reused (re-checked when `knowledgeStale` or when a decision depends on looks it doesn't cover). When that page is unpublished, use its MCP page tree (`catalogue --tree`) plus the component's fields and defaults, record that in `visualBasis` (e.g. "catalogue tree via MCP; render unverified"), and treat looks as unverified. Describe purpose, not just fields ("buyer-challenge statements in the customer's voice", not "three cards with heading and quote").
- **Freshness**: `knowledge-build` stamps `sig` (a fingerprint of the component's registry entry). When the registry changes, `select-context` marks the entry `knowledgeStale`: the registry's fields/capacity are used, the visual/limits must be re-checked (catalogue) and re-stamped with `--reviewed <id>`. Entries for components no longer in the registry are rejected as `obsolete`; remove them.
- **CMS**: never present an estimate as exact. `verified` only with a basis (Webflow limit error, site owner, Designer count). Page budget: ≤ 20 Collection Lists including Navigation/Footer.
- **Links**: only `exact`, `locale-stripped`, `normalized`, `confirmed` (user said so) or `manual` (user supplied) are stored. Similar-page matches are never stored unconfirmed.
- **Configs** (what a setting does — repeat counts, layout switches): `confirmed` only with rendered evidence (`designer-render`, `live-render` of a published page) or the site owner; catalogue settings and definition-tree analysis alone are `inferred`. `knowledge-build` enforces this. Confirmed configs are reused on every build and not re-tested unless the component's `sig` goes stale. **One rule everywhere** (`select-context`, `compose`, `writes-build`, `verify-page`): configs are usable only when the knowledge `sig` equals the fingerprint of the component's current registry entry. Stale, unsigned or unverifiable configs (no registry passed) are ignored — they hide no repeats and resolve no warnings — and are listed under `reinvestigate`. Always pass `--selection` together with `--knowledge` to `writes-build` and `verify-page`.

---

# BUILD A PAGE

1. **Load** (parallel, all inline): guide; read `selection.md` + `knowledge.md` (one `data_agent_instructions_tool` call; if the new path is missing, read the legacy `sml-marketer-registry/data/selection.md`, use it, and suggest a refresh); read the Google Doc. Save both registry reads → `python3 $S select-context --selection sel.read --knowledge kn.read` (selection cards + `health`).
2. **Starter, catalogue + links** (first build per site): `data_pages_tool list_pages{limit:100}` until done (saved) → `python3 $S starter --pages …` and `python3 $S links --pages … --locales '<get_site locales>' --href <all doc links> --out links.json`. Run `python3 $S catalogue --pages …` on the same page list to locate `/stylesheet/components` and store its page id in knowledge `catalogue` (later builds: validate it in the same batched `get_page_metadata` call as the Starter). Read the Starter tree `get_all_elements{depth:3}`, save it, and run `python3 $S starter-check --tree F`: it finds the wrapper (the drop target holding the hero, else the main wrapper), Navigation/Hero/Footer by role (names vary per site: "Hero", "Hero S", "Header"…), and **`prefilled`** sections the Starter ships with. It exits 1 with problems if the tree is truncated before the hero (re-read deeper), if there is no wrapper, or if roles are missing/duplicated — then report it; never build on an unvalidated Starter. Prefilled sections are either **reused** (they become a planned section and get written in full) or **removed** from the new page (`remove_element`, the duplicate only); never left with their default copy. Later builds: validate cached Starter/link pageIds with one batched `get_page_metadata` call; re-discover only what fails. Link resolutions:
   - automatic: `exact`, `locale-stripped` (primary locale without subdirectory), `normalized` (case / trailing slash / `.html`), `external`, `anchor`, and knowledge links marked `confirmed`/`manual`;
   - `review` (similar page(s) exist, with `candidates`): **never written unconfirmed**. Confirm a candidate (add it to the plan-check question when one is asked anyway) or keep the intended button visible and unlinked, reporting the candidates;
   - `unresolved` (with `draftMatch` when only a draft matches) and `placeholder` (`#`, empty): never guess — the intended button stays visible and unlinked (`{"unlinked":"<action>"}`) and is reported under *Destinations to configure*.
2b. **Catalogue (every build)**: read the catalogue page's tree (`get_all_elements{depth:-1}` on its page id, saved) and run `python3 $S catalogue --tree F` — the demonstrated components and the settings each example uses. If the page is published, also look at it rendered (staging/public URL, or the authenticated Chrome connection); if not, the tree is the evidence and looks stay unverified. Do this before step 3.
3. **Select components and compose the page** — see DISCOVERY, COMPOSITION and SELECTION below; run `compose` on the draft plan and resolve its advice before step 3b. Write the plan as a table: source section → purpose → component → status (`supported` / `limited` / unresolved) → alternatives rejected and why → planned editorial changes.
3b. **Plan check before any Webflow change**: after execution details (step 4), write the spec with `element:null` and run `writes-build … --plan`. It validates every write and reports each section's status without producing a call. Then **ask the user once, in one batch** (AskUserQuestion), about everything that needs a decision: sections with no suitable component (offer the closest registered candidates and "leave out"), and — only alongside such a question — `review` link candidates. Missing destinations alone are not a reason to ask: those buttons stay visible and unlinked. Only `skip` a section when the user (or a test brief) explicitly says so; record their answer as `skip:"<reason>"`. Do not create the page until the plan has no `unresolved` and no errors.
4. **Execution details** (2 calls typical): `data_component_tool` one `get_component{component_id, options:{includeProps:true, includeVariants:true}}` per selected ID **plus each knowledge `execDeps` ID** → `details.json` (batching keeps the result large enough to be saved). Include close alternatives when the choice depends on their fields (their leftover check is the evidence). Decide which variant props you will write, then `python3 $S exec-needs --selected IDS --details details.json [--trees …] [--variants …] --resolve <variant prop ids> [--investigate <ids with unconfirmed count/layout settings>]`. Fetch requested trees (one `data_element_tool` call, `get_all_elements{depth:-1, scope_component_id}` per ID) and, only if `variantCatalogue:true`, the variant catalogue. Repeat until empty, then `exec-build … --out execution.json`. Prefer writing visible fields over switching variants when both reach the same result (avoids tree fetches).
5. **Create** `data_pages_tool create_page{duplicateOf: starterId, title, slug, draft:true, seo}` (slug from the page name; add a suffix if taken; SEO in the page language). The duplicate keeps the Starter's element IDs. Populate the existing Hero; never add another Navigation/Hero/Footer. Remove prefilled sections the plan does not reuse (`data_element_tool remove_element`, all in one call) — only on the new page.
6. **Insert** all sections in one `data_component_builder` call: `insert_in_element`, `append` to the wrapper, document order, **without** `return_component_info` (the small result still carries every element id; with it the result is ~40× larger). `python3 $S ids --result <file>` → element IDs; exits 1 on any failed insertion. On a Collection List limit error, don't retry: pick a lower-CMS alternative or report. Slot inserts (`insert_in_slot`) return no ID: verify the target slot; never count an insert into the wrong/first slot as success.
7. **Write** content: author `spec.json` (format below), then `python3 $S writes-build --exec execution.json --spec spec.json --links links.json --knowledge kn.read --selection sel.read --out props.call.json --report editorial.md` (`--knowledge` lets confirmed `configs` hide repeats the chosen setting does not show; an inferred config makes the section *limited* with advice to confirm it). It exits 1 (and writes no call) on unsupported props, unknown keys (with "renamed? closest" suggestions), ambiguous keys, unresolved variants, placeholder links, unconfirmed `review`/`unresolved` links, unresolved sections, and **visible component defaults** (leftover eyebrows, quotes, buttons with default links…): write them, hide them with their toggle, or `accept` them with a reason. Its `advice` list (copy targets, sibling balance, generic phrases, markdown markers) is advisory — act on it only where it improves meaning (see EDITORIAL MODE). Its `productionReview` list names the placeholder images (and switched-off default media) that stay on the draft — see IMAGES AND MEDIA; they are not errors and not a reason to change the selection. Send `props.call.json` in one `data_component_props_tool` call.
8. **Verify**: `get_all_elements{depth:3}` of the new page (saved) → `python3 $S verify-page --tree F --call props.call.json --exec execution.json --knowledge kn.read --selection sel.read --spec spec.json --expect '<section names JSON>'` (`--spec` drops leftovers the spec accepted with a reason) checks single Navigation/Hero/Footer, section order, every written value, and lists `leftovers` still visible on the live page (walking every component instance). Any issue or leftover means the page is not complete: fix and re-verify. `get_page_metadata` confirms slug, SEO and `draft:true`.
9. **Update knowledge** with anything new (Starter, links, visuals, purposes, `execDeps`, CMS evidence, `configs` — including confirmed `visibility` relationships from `visibilityControls` — catalogue location); re-stamp reviewed entries.
10. **Report**: page + Designer URL, the selection table with each section's status (from `writes-build`: supported / limited and why / skipped by the user / removed prefilled), anything not completed (from `ids`, `writes-build`, `verify-page`), limitations, the Editorial adjustments report (`editorial.md`, refined by hand), and — separately from errors — **Before publishing**: placeholder images to replace and default media switched off (`productionReview`), **Destinations to configure** (`links.unlinked` from `writes-build`, `unlinked` from `verify-page`, plus `links.unplaced` actions with no control), and the internal-link method (`links.internalMethod`, e.g. the URL fallback).

**Spec format** (`spec.json`): `[{"label","component":"<id>","element":{"component","element"},"set":{…},"accept":{"<key>":"<why it may stay>"},"limits":["<technical limit that applies>"]}]`.
Optional `"shape":{"items":N,"purpose":"…"}` on structured sections feeds `compose`. Other entries: `{"label","component":null,"reason","considered":[…]}` = unresolved (blocks; ask the user); `{"label","component":null,"skip":"<who decided and why>"}` = left out by decision; `{"label","component":"<id>","element":{…},"remove":"<why>"}` = prefilled Starter section removed.
`set` keys are prop IDs or unique `Group.Name` keys (as in `execution.json`). Values: text → string; rich text → plain paragraphs; bool; number; variant → option name or id; `null` → reset; link → path/URL, or `{"href":"<doc link>"}` resolved through `links.json`, or `{"href":…,"confirmed":"<candidate path>"}` after the user confirmed a `review` candidate; add `"action":"<intended action>"` to name the action it carries; `{"unlinked":"<intended action>"}` = a visible button deliberately without a destination. Per section, `"actions":["<intended action>",…]` lists the source's intended actions (writes-build blocks if one is not on a visible button) and `"unplacedActions":[…]` the ones the component cannot represent (reported, never silently dropped). Any value may be wrapped as `{"value":…, "source":"<original text>", "why":"<reason>"}` — that feeds the editorial report. `accept` lists leftovers you deliberately keep, each with a reason (report them); a section with accepted gaps or `limits` is `limited`.

---

# DISCOVERY (what the site's components can actually do)

The catalogue step (BUILD 2b) runs on every build. Deeper investigation (definition trees, rendered checks, test pages) is for components where knowledge is missing, stale or too thin for a decision that matters — focus on components that could materially improve the page, and investigate before rejecting them.

1. **Registry first**: registered `Section —` / `Item —` components, fields, capacity and warnings (`select-context`). It stays authoritative for ids, props and capabilities.
2. **Catalogue** — every SML site has one at **`/stylesheet/components`**: a Webflow page in the current project, not necessarily a public URL. `python3 $S catalogue --pages <pages file>` finds the page — by `publishedPath`, or when that is missing (drafts, unpublished pages) by the page hierarchy and slug (`match`: `hierarchy` / `sibling-path`); a slug-only hit inside an unresolved folder is returned as a `candidate` to confirm with `get_page_metadata`, never as the catalogue; when it is published, open the site domain + that path (WebFetch, or the authenticated Chrome connection) for a visual overview. Whether or not it is published, read the catalogue page's tree through MCP (`get_all_elements{depth:-1}` on its page id, saved) and run `catalogue --tree F`: it lists every demonstrated component and the non-text settings each example uses (counts, layouts, backgrounds). That is configuration evidence, not visual evidence. Record the catalogue location in knowledge `catalogue`.
3. **Settings that change layout or count** (a boolean "Amount of …", a layout switch, a count-switch warning): don't reject the component — investigate. `exec-needs --investigate <id>` requests its definition tree; `exec-build` then reports `repeatVisibility` (which repeats always render, which are conditional or bound to a prop) and a `configHint`. MCP does not expose conditional-visibility rules or boolean option labels, so confirm *which value shows what* with rendered evidence, cheapest first:
   - the public catalogue page;
   - a **published page** that uses the component (find one with `query_elements{component_filter}` on a few likely pages, compare its setting with the rendered DOM in the browser);
   - the person's own **Chrome** (Claude in Chrome, already signed in) when that connection is available — for the Designer or a rendered page; never ask the person to sign in to Webflow in a separate browser;
   - a **disposable draft test page** (duplicate the Starter, insert, write both values, render via one of the above). Remove test sections afterwards; never publish.
   **Visual inspection order**: (1) Webflow MCP — components, props, variants, trees (MCP gives structure, not screenshots); (2) the catalogue on the public or staging domain; (3) the existing authenticated Chrome connection, when available; (4) the catalogue page structure via MCP (`catalogue --tree`, works unpublished); (5) other published pages with an instance; (6) otherwise continue from properties, catalogue structure and knowledge, and mark the visual assumption as **unverified** (`visualBasis`). Visual inspection never blocks an executable draft: if a route is unavailable, say so in the report and carry on.
4. **Visibility across groups**: a boolean in one group can hide content in another (a layout-level "Eyebrow" switch hiding every card eyebrow). Never infer that from names. When `writes-build` reports a leftover such a setting might hide, run `exec-needs --investigate <id>`: with the definition tree, `exec-build` reads direct Visibility bindings (`visibleIf`, `visibilityControls`) and the leftover checks respect them in any group. Conditional rules and nested instances with more than one Visibility prop are ambiguous and ignored (the safe report stays). Store a confirmed relationship as a knowledge config `{"kind":"visibility","prop":"<Group.Name>","hides":["<Group.Name>",…],"status":"confirmed","basis":"definition-tree","evidence":"…"}` — reused only while the component's `sig` is current, like every config.
5. **Store** what you learned in knowledge (`configs`, `visual` + `visualBasis`, `limits`, `bestFor`/`notFor`) and verify the write. Never call something visually verified when only properties were inspected.

---

# COMPOSITION (page level)

Plan the page as a sequence before fixing individual sections: what each section does (introduce, explain, list, compare, prove, conclude), where emphasis belongs, and whether related content should be combined or split.

1. Give each structured spec item a `shape`: `{"items":N,"purpose":"services|process|comparison|faq|…"}`.
2. `python3 $S compose --spec spec-plan.json --selection sel --knowledge kn` lists the section sequence, flags **runs of 3+ identical components** and a page dominated by one component, and for every structured section in a non-repeat component lists repeat components that could carry it — with fit (`fits`, `regroup to 3/6`, `always N`, `investigate count switch`), the basis (confirmed config, fixed count, per-item visibility) and purpose match. It also lists **purpose layouts**: components whose knowledge `bestFor` includes the item's purpose (image layouts included — `placeholderImage:true` only means the image stays a placeholder). Components whose knowledge says `notFor` that purpose are never offered. Confirmed `configs` are used only while the knowledge entry's `sig` matches the component; a stale one is ignored and listed under `reinvestigate`.
3. Reconsider every flagged run: check the offered layouts (and investigate promising unconfirmed ones, see DISCOVERY) before keeping plain text. Grouping is fine when the subjects belong together (four service areas → three boxes when two are clearly one theme, e.g. servers and network as "infrastructure"), and so is distributing content over complementary components — but never invent an item, drop meaningful information, or pad to reach a fixed count.
4. Visual variety is a quality consideration, not a quota: keep similar consecutive sections when the content genuinely calls for the same presentation, and say why in the plan. Alternate backgrounds only as a finishing touch, not as a substitute for a better layout.

---

# SELECTION (purpose first, then fit)

The order is: understand the source → explore the available components and their configurations (DISCOVERY) → develop the page composition (COMPOSITION) → investigate uncertainties that affect promising options → adapt the content → validate and build.

For every source section:

1. **Name its purpose** with the vocabulary above (what the reader should get from it: proof, sequence, comparison, reassurance, action…) and its **shape**: number of items, heading/description pairs, sequence, lists, figures, quotes, links, media.
2. **Candidates** = components whose `bestFor` matches the purpose and whose capacity fits the shape; exclude any whose `notFor` matches. Without knowledge, fall back to the registry fields, but if the decision depends on how a component looks or reads, and its `visual` is missing or `knowledgeStale`, inspect the site's component catalogue (once, then record it in knowledge). Never decide visual suitability from field names alone: a three-card component for buyer challenges and one for product benefits both accept "heading + text", and they are not interchangeable.
3. **Fit check** per candidate, using `select-context` cards (and execution details when fields decide it):
   - every *required* visible element can be filled from the source — elements without a toggle are required (an eyebrow that always shows, a primary button that needs a real link, a quote with name and job title);
   - nothing would show component defaults that misrepresent the page (another customer's quote, default buttons linking to unrelated pages, placeholder "Lorem ipsum");
   - repeats fit (`capacity`, `shownByDefault`, `fixed-count`, `count-switch`, knowledge `configs`) without dropping or inventing items: a fixed-count component (always N items, no per-item toggle) only fits content with exactly N items — or content that can honestly be grouped into N; a count switch offers each confirmed count (unconfirmed → investigate first, see DISCOVERY);
   - every *text, link and setting* field you need is writable (`writable` in `execution.json`; CMS-bound groups, `headingTag` and visibility-type props are not) — images are not part of this check: a default image stays as a placeholder (IMAGES AND MEDIA) — components flagged `cms-content` or `no-writable-content` can't show static source content;
   - the slot you need is uniquely named (`ambiguous-slots`), and anything that must be hideable has a toggle — a visible element with no toggle and no source content means defaults stay visible;
   - `limits` and `warnings` (CMS budget, conditional visibility, external form dependencies) don't block it.
   Classify the result: **supported** (everything fits; placeholder images are fine), **limited** (suitable, with a technical limit you report: plain-text rich text, an accepted gap, an unconfirmed config, accepted default media), **unsuitable** (would show default *text*, quotes or links, drop items or misrepresent the purpose). An image the source doesn't supply never makes a component limited or unsuitable.
4. **Prefer natural fit over compression**: choose the candidate that keeps the content's structure (items stay items, steps stay in sequence, figures stay in a table, safety/limitation qualifiers stay complete) with the least rewriting. Before shortening or restructuring substantially, check whether another candidate would hold the content as written. Long structured content is not automatically compressed into cards; a list of parallel advantages is not flattened into one paragraph; a technical explanation does not lose details for symmetry.
5. **When the first choice is unsuitable**, in this order: (a) another registered component or configuration that fits (after investigating promising settings); (b) an editorial adaptation that preserves meaning — a regrouping onto a suitable layout, or the content distributed across complementary components; plain text (labelled paragraphs, static FAQ as question/answer paragraphs when the FAQ component is CMS-driven) is the fallback, not the default; (c) otherwise the section is **unresolved**: collect it for the batch question in step 3b with the closest candidates and why each fails. Do not compensate with aggressive rewriting, and do not invent content to fill a component. Once the user names a component, use it and report whatever does not fit.
6. Keep it simple: no numeric scoring. Record per section the chosen component and, in a few words, why each serious alternative was rejected.

---

# EDITORIAL MODE (during mapping and population)

The doc is source material, not final copy. Adapt it to each component's purpose and visual hierarchy, after selection — editing never substitutes for choosing the right component. You may, without asking:

- Write a concise, meaningful eyebrow when the component shows one and the doc has none (a topic label: 1–4 words, not a slogan).
- Shorten or rephrase a headline that is too long for its component; move a label-like source heading ("Benefits") to the eyebrow and give the heading the outcome.
- Condense long introductions and descriptions; **move** detail that doesn't fit to the section where it belongs instead of dropping it.
- Balance sibling cards only when it helps the reader: trim a long one that repeats or wanders; never pad a short one with filler, and don't move important information just to even out lengths. Uneven lengths are fine when the content is naturally uneven.
- Remove repetition (including eyebrow/heading echoes and points already made on the page).
- Restructure when the component supports it: subheading → eyebrow/heading, list items → separate paragraphs or items, numbered steps → numbered item headings, labelled parts ("Solution —") inside rich text.
- Shorten CTAs and button labels to a direct action, keeping meaning that matters ("on-site").
- Improve clarity and readability.

Targets (advisory; meaning and accuracy always win; rendered constraints win over character counts when you could inspect them; `writes-build` lists them as `advice`): headlines 1–2 desktop lines (~70 chars, 3 lines triggers a rethink); intros 2–4 lines (~320 chars); eyebrows 1–4 words; card descriptions concise (siblings within ~2× is a hint, not a rule); CTAs short (≤ 4 words). Wrapping depends on type and width: never claim a line count unless you inspected the rendered result.

Boundaries:
- Keep the author's meaning, intent, language and tone. Never edit the Google Doc.
- Never invent facts, capabilities, specifications, statistics, customer quotes, testimonials or links. Keep qualifiers that change meaning ("fictional", "illustrative", "must not", "may require", "not yet measured").
- Do not change meaningful technical terminology just to save space.
- Never drop important information to make content fit. If it can't fit, choose another component or report it.
- No empty promotional language or generic AI marketing phrases ("unlock", "seamless", "cutting-edge", "world-class", "elevate your…") — and never to fill a field.
- Ask only when an edit would materially change meaning or needs missing facts; otherwise edit.

After the build, add an **Editorial adjustments** report: per meaningful change give section, field, original → revised, and why (the `--report` table is the starting point). Explicitly list anything shortened away, moved, or not represented. Group minor edits; skip trivial formatting.

---

# STRUCTURED CONTENT AND RICH TEXT

MCP writes rich text as plain text only: a blank line starts a paragraph, a single newline is a line break; headings, bold, links and list markup are not available (markdown markers render literally — `writes-build` flags them). In order of preference:

1. Choose a component whose **fields** carry the structure (items for list entries or steps, table rows for label/value data, columns for parallel groups, eyebrow + heading for subheadings).
2. Map structure onto available heading/description/item props.
3. Transform inside rich text so meaning survives: one paragraph per list item, labelled paragraphs ("Result — …"), numbered paragraphs for sequences.
4. Report what cannot be represented (true bullet lists, bold emphasis, inline links, nested lists).

Never pour every heading and paragraph of a structured section into one rich-text field when a structured component exists. Element-level rich-text editing (creating headings/lists inside a rich-text prop) would mean creating elements, which SML forbids.

---

# IMAGES AND MEDIA

The Google Doc provides the content; SML provides the layouts **and the default imagery**. Images are optional in the doc.
- **Placeholder images are acceptable on a draft.** Keep every default image unchanged: don't hide it, don't reject or downgrade a component because MCP can't replace it, don't require image URLs in the doc. Image layouts (media + text, image cards…) compete equally with text layouts. Hide or change an image only when the source explicitly asks for it.
- `writes-build` and `verify-page` list kept images under `productionReview` ("replace in the Designer before publishing"); the report shows them under *Before publishing*, not as errors.
- **Default text, quotes and links stay strict**: unrelated default text or another customer's quote must be written, hidden or reported; a `#`, unrelated or unconfirmed link must be resolved, hidden or reported.
- **Default video and embeds are evaluated separately** (they can play unrelated or external content): a default video/embed URL whose on-switch (`…video`, `…lightbox`, `…embed` booleans in the same group) is off is a production note; when it would play or load (switch on, or no switch found), it is a blocking leftover — write the source's own URL, switch it off, or `accept` it with a reason (then *limited*).

---

# ACTIONS AND LINKS

The source's intended actions (download a resource, contact, demo, booking, request information, any explicit or clearly implied call to action) are part of its content. Understand the intent — not labels such as `Resource:` or `Button:` — and keep the freedom to restructure the content into any suitable layout.
1. Recognise each intended action and its role; list them per section in the spec (`actions`).
2. Preserve each action when restructuring: put it on a suitable button or link property of the chosen component.
3. Resolve the destination when possible (`links`); internal pages as verified URL paths (see MCP facts), external ones as URLs.
4. If the destination cannot be determined reliably, keep the button **visible and unlinked** (`{"unlinked":"<action>"}`). Never guess, never keep a default link, never point it at Home or another unrelated page. This is a valid draft state and does not block the build.
5. An action the chosen component has no control for goes into `unplacedActions` with the reason; it is reported, not dropped.
6. Optional component buttons with no matching source action may be hidden. Unrelated default CTAs are replaced or hidden.
7. Report: linked actions with their destinations, unlinked ones under *Destinations to configure*, unplaced ones, and any internal-link fallback.

---

# MCP 2.2 FACTS

- Variant props: write the option ID as a string (`type:"string"`); `base` is the default option.
- Links: native page links (`link_mode:"page"` + page id) are rejected on component props — the server accepts only url, email, phone, popover, modal (retested 2026-11-01 on two sites; the beta server had no site access). Internal destinations are written as verified URL paths. `writes-build --native-links` writes page links for when MCP supports them; if the call is rejected, rerun without it (URL fallback) and report it. A visible button without a destination is written as `{type:"link", link_mode:"url"}` with no `link_to`: MCP stores `{"mode":"url"}` (verified, replaces a default `#` or default page link).
- `{type:"null"}` resets a prop. Image props have no write type: keep placeholders (IMAGES AND MEDIA). Rich text: plain text (see above).
- Conditional `visibility`-type props and `headingTag` are unverified: don't write them.
- `insert_component_instance` cannot anchor before/after an instance; append to the parent.
- `insert_in_slot` matches slot by *name*; duplicate names reach only the first slot.
- Collection Lists inside component instances are not visible to `query_elements`; counts can't be verified via MCP.
- `element_snapshot_tool` needs an open Designer session; without it, rendering (line wrapping) can't be inspected.
- Inline results (< ~60 KB) are not saved to disk; larger ones are.
- `get_all_elements{depth:2}` may stop above sections nested in a drop target (`hasMoreChildren`); `starter-check` detects it. Use depth 3 for Starters and verification.
- `insert_in_element` without `return_component_info` returns ~2 KB per call including element ids.
- `remove_element` on a section of the new page is allowed (it is the duplicate); never on the Starter or other pages.
- Conditional visibility shows as `{"sourceType":"conditional"}` without the rule; boolean option labels (e.g. "Three Boxes / Six Boxes") are not exposed by any MCP read; elements nested in instance slots inside a component definition are not addressable by `query_elements`. Render evidence settles these.
- The catalogue page (`/stylesheet/components`) is a normal page: its tree is readable through MCP even when it is not published.
- `read_instruction` takes `path` only. Occasional upstream `500`/`502`: retry once with the same payload, then report.
