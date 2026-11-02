---
name: sml-section-builder
description: "Build Webflow section layouts from existing SML base components (section, row, col, box, heading, …) via Webflow MCP: initialize the site's SML Section Builder Registry, preview layouts from screenshots or descriptions as SML DSL, build verified sections with rollback, rename them, and decompile existing sections back to DSL. Use for 'initialize SML registry', SML DSL, 'build this section/layout', or turning a mockup into SML structure."
---

# SML Section Builder v6 (Webflow MCP 2.2)

Section Builder turns layouts into nested instances of a site's **existing** SML base
components (`__dev — section`, `row`, `col`, `box`, `heading`, …) and configures their props.
It never creates classes, styles, variants or components, and never edits component definitions.

**Boundary.**
- This skill = how SML works: grammar, visual resolution, build workflow. Site-agnostic.
- `scripts/sbx.py` = every deterministic step: registry generation, parsing, validation, wave planning,
  id mapping, prop writes, verification, rollback, decompile. Standard library only. No site data.
- The site's **SML Section Builder Registry** (Agent Instructions under `sml-section-builder-registry/`) =
  what exists on that site: aliases, component and prop ids, options, defaults, slot names, build target.
  Machine generated.

```
sml-section-builder-registry/
├── SKILL.md            index (title "SML Section Builder Registry")
└── data/
    └── components.md   registry payload, schema 4.0
```

Section Builder is independent of every other skill. It reads no other skill's files.

`references/mcp-facts.md` lists the MCP behaviour this workflow depends on (with test dates).
`references/registry-schema.md` documents the registry.

---

# HARD RULES

1. **Registry is the only vocabulary.** Aliases, prop labels and option labels must exist in the loaded
   registry of the target site. Never reuse values from another site: the same component can carry
   different variants per site. Other Agent Instructions on the site are not registry data.
2. **Resolve the target site fresh** every run, in this order: explicit site id → staging/published URL
   (match the `.webflow.io` shortName in `list_sites`) → exact unique site name (several matches: ask) →
   the open Designer site, only when the person says current/open/selected site. Never cache site ids.
3. **Never touch pre-existing content.** Builds only append or prepend new instances. Rollback and cleanup
   remove only element ids this build recorded in its state file. Never remove, move or rewrite anything else.
4. **Never edit component definitions** (no `scope_component_id` writes, no prop/variant/slot-default changes).
5. **Every call file comes from `sbx.py`.** Send the actions exactly as written in the `.call.json`
   (top-level fields + `actions`). Do not hand-edit ids, prop ids or option ids.
6. **Never retype a large MCP result.** Results reach `sbx.py` as the harness's saved file. The only thing
   transcribed by hand is the compact ids file for an inline wave result (Mode A step 3).
7. **Never drop structure or props** to make a build shorter. **Never reorder components.**
   **Nesting is explicit**, never implied by adjacency.
8. **Unsure → flag, never guess.** Unmappable visuals are flagged under the preview, not invented.
9. **Mode B stops after the preview.** No build calls until the person confirms.
10. **No sleeps, waits or blind retries.** A `429` or transport error is reported, not looped on.
11. **Silent execution in Mode 0 and Mode A.** No narration between calls. One terminal line at the end
    (the `summary` from `sbx.py`), or the failure and what was rolled back.

---

# FLOW

| Request | Mode |
|---|---|
| `initialize SML registry`, `refresh SML registry`, `setup SML` (any capitalization) | **0 — Bootstrap** |
| Screenshot, mockup, description of a layout | **B — Preview** |
| SML DSL (`section:` / `section{` / `section[` / `row:` …), or "go" after a preview | **A — Build** |
| "what's in this section", "turn this section into DSL", "edit section X" | **I — Inspect** (decompile) |
| "rename the sections I built" / "give them names" | **R — Rename** |

Modes A, B, I and R load the registry first: `read_instruction` (`resolve_references: false`)
`sml-section-builder-registry/data/components.md`, then `sbx.py registry-load`. If it is missing, run Mode 0.
Mode 0 creates or refreshes it.

Work in the scratchpad: one folder per run (e.g. `$S/sb/<site>-<time>/`). Copy every saved tool
result into it with a meaningful name before running `sbx.py` on it.

---

# EXECUTION CONTEXT

Headless `data_*` tools only. The Designer bridge (`designer_tool`) is needed only to resolve
"this page / the selected element / the open site".

Every `data_*` call carries:
- `session_id`: `start` on the first call of the task, then the issued `ses_…` value.
- `agent_id`: `<model>|<harness>|<4–6 char suffix>`, chosen once per task.
- `context`: 15–25 words, third person.

| Purpose | Tool | Action |
|---|---|---|
| Site / pages | `data_sites_tool`, `data_pages_tool` | `list_sites`, `list_pages` |
| Component index | `data_component_tool` | `get_all_components` (includeProps, includeVariants) |
| Registry | `data_agent_instructions_tool` | `read_instruction`, `create_instruction`, `update_instruction` |
| Page / definition trees, readback, names, rollback | `data_element_tool` | `get_all_elements`, `query_elements`, `set_display_name`, `get_display_name`, `remove_element` |
| Insert instances | `data_component_builder` | `insert_in_element`, `insert_in_slot` |
| Write props | `data_component_props_tool` | `set_component_instance_prop_values` |

A `.call.json` from `sbx.py` has `tool`, usually `siteId`/`pageId`, and `actions`. Add `session_id`,
`agent_id` and `context`, and send. For `data_agent_instructions_tool` the call is a bare list of actions.

**Results to file.** `sbx.py` reads saved results. When the harness returns a result inline and a step needs
it as a file, follow `references/mcp-facts.md` → *Force-to-file*. Wave results are the exception: if inline,
write the ids file (Mode A step 3).

---

# MODE 0 — BOOTSTRAP

Goal: write the SML Section Builder Registry: `sml-section-builder-registry/data/components.md` (schema 4.0)
and its index `sml-section-builder-registry/SKILL.md`. `registry-build` produces both paths; never rename by hand.

**Ownership.** Section Builder owns `sml-section-builder-registry/` and writes only those two files there.
It never reads, writes or deletes any other folder: not `sml-page-builder-registry/` (SML Page Builder),
not `sml-registry/` (the SML Webflow skill v5.x, and earlier Section Builder installs).

1. Resolve the site (Hard Rule 2). `list_pages` → the build target is the page with slug
   `stylesheet/components` (ask only if absent or ambiguous). In one call, `read_instruction`
   (`resolve_references: false`) `sml-section-builder-registry/SKILL.md` and
   `sml-section-builder-registry/data/components.md`; missing paths return errors. Note which exist. Save the result.
2. `get_all_components` with `includeProps` and `includeVariants`, repeated in one call until the
   result is saved to a file → `components.txt`.
3. `sbx.py bootstrap-elements --components components.txt --page-id <target> --out elements.call.json`
   → send it (page tree + one definition tree per aliasable component) → save as `elements.txt`.
4. `sbx.py registry-build --components components.txt --elements elements.txt --site-id <site>
   --page-id <target> --existing-paths <comma list of existing paths> --current <step 1 file> --out-dir reg/`
   - exit 3 `needs-slot-names`: send `reg/slotnames.call.json` (display names of unnamed slot elements),
     save the result, rerun with `--display-names <file>`.
   - `problems` naming unresolved slots + `reg/slotprobe.call.json`: send it (inserts one instance of each
     affected component at the end of the target wrapper), save the result, rerun with `--probe-result <file>`,
     then send `reg/slotprobe.cleanup.json` (removes exactly those probe instances) and confirm with the result.
     If the target page refuses the probe (e.g. *more than 20 Collection Lists on a single page*), create a
     draft page (`create_page{draft:true}`), read its Body id, rerun with `--probe-page <id> --probe-parent <body id>`
     and ask the person to delete that page afterwards (MCP cannot delete pages).
   - `registryUnchanged: true` means the stored registry already matches (digest re-computed from its body):
     only the index is rewritten.
5. Send `reg/write.call.json` with `data_agent_instructions_tool` exactly as written: the writes, then
   repeated `read_instruction` actions that push the result into a saved file. Payload up to ~35KB per site;
   send it verbatim.
6. `sbx.py registry-verify --readback <saved result> --expected reg/registry.json` must say `ok`
   (it also fails on any write error). Otherwise report the problems; do not build on a mismatched registry.

Terminal line: `SML Section Builder Registry initialized — <n> aliases, digest <digest>.`

Regenerate whenever components, props, variants or slots change, the build target moves, or the
registry was copied from another site (`registry-load` refuses a registry whose site id differs).

---

# MODE B — PREVIEW

Load the registry (`read_instruction` `sml-section-builder-registry/data/components.md` → `sbx.py registry-load --read <file> --site-id <site> --out reg.json`).
Read the visual as structure, write DSL, then run `sbx.py check --registry reg.json --dsl plan.sml`
and fix every error. Warnings either get fixed or become flags.

Preview **the whole request** in one response, however many sections. There is no batch limit;
split only if the person asks.

## Output

Only this block — no preamble, no narration. The DSL sits in its own code fence:

~~~
**Interpretation DSL:**

```
[DSL, all sections]
```

[optional flags, one per line: `* [what] — [why]`]

Confirm or tweak before I build.
~~~

## Rules

- Closest valid mapping immediately, from this registry's option lists only. No valid option → omit the prop, flag it.
- Same visual decision → same values across sections (same two-column layout, same card style, same heading size).
- Unsupported bindings (image asset, video) never drop the leaf: insert it with everything else resolved, flag the binding.
- No clarifying questions before the preview. Flag after.
- Name every section with `[purpose]` (see DSL): `section[Hero · background image]`, `section[Pricing · three plans]`.
- Two or more consecutive `"single paragraph"` of the same resolved size become one `"rich text"`
  (texts joined with `\n\n`; drop the spacers between them). Different sizes stay separate.
- Defaults only where the visual implies no choice. The `base` option is the component's own default look;
  write an option only when the visual differs from it. `sbx.py` drops writes equal to the real default anyway.
- Use an option or toggle only when its label describes what the visual shows. Leave options of unknown
  effect (a section `Style=Hero`, an icon's extra glyph toggles) at their default; flag them only when they
  could visibly matter.

## Visual resolution

Map the visual to a category, then pick the closest option from the prop's actual `options`. The floor is:
image ratio, heading size, column layout (all three breakpoints), above-base paragraph size, and text
alignment (any centred or right-aligned text is wrapped in `text-align`).
Anything else the registry can express structurally is resolved too. Micro-detail (spacer size,
base-or-smaller paragraph size) is not.

Read structure, not just blocks: a hero with an image behind the content, a card grid, an image/text pair,
content anchored to a region. Reach for registry components from visual effects: thin lines between cards →
vertical `"hr dividing line"`; hairlines between rows → horizontal `hr`; arrows and small glyphs → `icon`.
Effects the registry cannot produce are flagged, never invented.

**Card grids are one row of wrapping cols.** Two lines of three cards = one `row` with six `4 / 12` cols.
Use several rows only when lines differ structurally. `hr` inside a row is zero-width; it does not count
toward the 12 columns.

**Vertical spacing.** Inside vertically stacking containers, every visibly separated pair of siblings gets
a bare `spacer` between them. Never write `Size` on a spacer.

**Paragraph size.** Body text (`"single paragraph"`, `"rich text"`) sets `Text size` only when larger than base.
Headings set their size whenever it differs from the default, in either direction.

**Heading scale and tags.** Page title → the largest size and `Tag=h1` (one per page). Section titles → the
next sizes down (`heading-l` / `heading-m` class), `h2` (the usual default). Card and item titles →
`heading-s` / `heading-xs` class, `h3`. Keep the same level the same size across sections.

**Image ratio.** Every image sets its ratio option: ~1:1 square, 4:3 / 3:2 landscape, ~16:9 wide,
21:9+ widest; unclear → the 16:9-class option.

**Section background image.** A section whose image fills its bounds behind content is a pair: the section
gets `Style="Full screen"` and the image is its first child with `"Image ratio"=background`; foreground rows
follow as siblings. Always both.

```
section[Hero · background image]{ Style="Full screen" }:
  image{ "Image ratio"=background }
  row:
    col{ "Layout Desktop"="8 / 12" "Layout Tablet"="6 / 6" "Layout Mobile"="4 / 4" }:
      heading("…"){ Tag=h1 }
```

**Responsive columns.** Every `col` sets `"Layout Desktop"`, `"Layout Tablet"`, `"Layout Mobile"`.
Desktop from the visual; tablet keeps multi-column structure while readable (widen anything under `2 / 6`);
mobile `4 / 4`. Never denser at smaller breakpoints.

**Element alignment vs text alignment.** Two separate decisions, made independently:
- **Element alignment** — `row` / `col` `align` and `justify` position *child elements* inside their
  container (centre a col narrower than 12 columns, centre an icon in a col, vertically centre a text column
  against an image). They never align the *text* inside those elements. Do not centre a row or col just
  because its text is centred.
- **Text alignment** — centred or right-aligned text (headings, paragraphs, rich text, buttons in a centred
  text block) always goes inside the site's `text-align` component (`__dev — text-align`), even when the
  copy fits on one line today: text wraps once it is edited, so the alignment must be structural. Set all
  three breakpoints (`Text align Desktop`, `Text align Tablet`, `Text align Mobile`). Left-aligned text needs
  no `text-align` component unless the layout specifically requires it.

```
row{ justify=center }:                                  # element alignment: centre an 8/12 col
  col{ "Layout Desktop"="8 / 12" "Layout Tablet"="6 / 6" "Layout Mobile"="4 / 4" }:
    "text-align"{ "Text align Desktop"=align-center "Text align Tablet"=align-center "Text align Mobile"=align-center }:
      heading("How we work"){ "Text size"=heading-l }   # text alignment: centred text
      spacer
      "single paragraph"("Three steps from first conversation to stable, secure IT.")
```

**Layout axes** (read from the SML site CSS, 2026-11-02 — `row` slot is a horizontal flex container,
`col` slot is a vertical flex column):
- `row` `align` places cols **vertically**: default `start`; `center` vertically centres a text column
  against a taller image column; `stretch` gives equal-height cols. `row` `justify` places cols horizontally
  (`center` centres a narrower col).
- `col` `Align` places the col's children **horizontally**: default `stretch` (full width); `start` makes them
  hug their content on the left (use it when a lone button or short element must not stretch; it is a real
  write, not a default); `center` centres the child elements (e.g. an icon) — not their text.
  (Read a prop's real default from its registry `default`, not from which option is labelled `base`.)
- `col` `Justify` distributes children vertically; it only has an effect when the col is taller than its
  content (row `align=stretch`).

**Icons.** Phosphor names in `ph-<name>` form: `icon(ph-arrow-right)`, `ph-arrow-up-right`, `ph-caret-down`,
`ph-x`, `ph-check`. A bare `icon` only when the glyph is unreadable (flag it). An icon is an element: position
it with col `Align`, or keep it inside the same `text-align` block as the centred text it belongs to.

**Text.** No all-caps text; sentence case. Uppercase is CSS.

**Row without cols.** A row whose direct children are not cols sets `"horizontal gap size"=no-gap` and spaces
siblings with explicit spacers.

**Horizontal buttons.** Buttons side by side are direct children of a row (never wrapped in cols or boxes).
The spacer between them is hidden on mobile because the buttons wrap and stack there:

```
row{ "horizontal gap size"=no-gap align=center }:
  button("Primary"→/start)
  spacer{ "Responsive visibility"="hidden only on mobile" }
  button("Secondary"→/about){ Variant=Secondary }
```

Vertically stacked buttons follow the normal spacing rule.

**Positional slots** (`grid-N`, `tab-N`, `slide-N`) hold exactly one element; several → wrap in a `box`.

**Boxes and cards.** Labels come from the registry (`Style`, `Variant`…; `Card`, `Card content`, `Regular`…).
A box has one `Style`, so each visual layer is its own box.
- Image flush to the card edge: outer `Card` holds the image; inner `Card content` holds the padded text.
  An image inset like the text goes inside `Card content`.
- Text-only card: a single `Card content` box, no outer `Card`.
- Text-only card with its own outline or fill style (e.g. `Card outline dark`): outer box with that style,
  inner `Card content…` box for the padding.
- Padding sizes (`Card content S/M/L` on some sites): `M` unless the visual is clearly tighter or roomier.
- `Regular` only when a wrapper is structurally needed; no `box` around independent elements.

**Eyebrow vs tag.** An eyebrow is unfilled text directly above a heading: never a spacer between them.
Use an eyebrow alias, or the paragraph's `eyebrow` text size where the site has one.
A tag/label/badge has a filled pill (a `tag pill`-type component where the site has one) and is spaced like any sibling.

**Touching rows.** Stacked items that visually touch (accordion rows, list rows with dividers) take no spacer.

A preview is invalid if a visibly separated vertical pair has no spacer or an image has no ratio.
`sbx.py check` warns on both, plus: all caps, default placeholder text kept, button without link,
col with desktop but not tablet/mobile layout, uneven wrapping widths, multi-element positional slots,
stacked same-size paragraphs, spacer after an eyebrow, an unpaired full-screen/background image,
a button row without `align=center`, a `text-align` that does not set every breakpoint, and several children landing in the
first of several same-named slots.

---

# DSL GRAMMAR

```
section[Name]{ Prop=value "Grouped.Prop"=value }:     # container: trailing colon, children indented
  row:
    col{ "Layout Desktop"="6 / 12" }: heading("Title") "single paragraph"("Body")   # inline leaves
    col:
      button("Learn more"→/about){ Variant=Secondary }
  tabs{ "Tab 1.Visibility"=true }:
    tab-1:                                            # slot header for multi-slot containers
      "rich text"("Para one.\n\nPara two.")
    tab-2:
      "accordion item"("Question?"):
        "single paragraph"("Answer.")
```

- **Aliases** from the registry; quote multi-word ones (`"single paragraph"`, `"rich text"`, `"accordion item"`).
- **Containers** end with `:` and nest in block form only. Leaves may sit inline after a container's colon.
- **Slot headers** (`tab-1:`, `slide-3:`) choose the slot of a multi-slot container; without one, children
  go to its first slot. Single-slot containers need none. When several slots share a name, `"Slot #2":`
  names the second one; only `#1` can be filled through MCP (see LIMITS), so `check` rejects `#2` and up
  and warns when several children would all land in slot 1.
- **Content** `alias("text")` sets the component's `primary` prop (`Text`, `Content`, `Icon code`…).
  `\n` in content is a newline. **Link** `alias("text"→/path)` sets its `link` prop
  (`/page`, `#anchor`, `https://…`, `mailto:…`, `tel:…`).
- **Props** `{ Label=value }`. Quote labels/values with spaces or punctuation. Grouped props:
  `"Top.Padding"`, `"Top :: Padding"`, or a bare label when only one group has it. Labels and option labels
  match case-insensitively. Booleans and visibility: `true/false`, `visible/hidden`, `yes/no`, `on/off`.
- **Display name** `[Name]` after the alias (`section[Hero · intro]`, also on inner nodes). `--prefix "SB · "`
  on `build` prepends a marker to every name.
- `#` starts a comment.
- Order of decorations: `alias[name](content→link){props}`.

---

# MODE A — BUILD

Default target: the registry's build target (`stylesheet/components`), appended at the end of its wrapper.
Other targets: `--page-id <page> --wrapper <element>` (find the wrapper with `get_all_elements` +
`sbx.py target-check --tree <file>`), or `--parent-element <instance id> --slot <name>` to add into an
existing instance's slot. `--position prepend` inserts at the start instead.

1. **Snapshot, load and compile.** Read the target page once: `get_all_elements{depth:-1}` (repeat the action in
   the same call if needed so it is saved to a file) → `before.txt`. `registry-load`, then
   `sbx.py build --registry reg.json --dsl plan.sml --state state.json --out wave1.call.json --page-tree before.txt [--prefix "SB · "] [target options]`.
   `--page-tree` checks that the target wrapper exists and records its current children, so verify and
   rollback-check can prove that pre-existing (catalogue) content is untouched. Errors stop the run (report them).
   Warnings are listed in the output; `--strict` makes them errors.
   Every section without a `[name]` should get one before building (Mode B always names them).
2. **Send the wave.** `wave1.call.json` → `data_component_builder`.
3. **Feed the result back.** `sbx.py next --state state.json (--result <saved file> | --ids idsN.txt) --out wave2.call.json`.
   - Saved file: pass it with `--result`.
   - Inline result: write `idsN.txt`, one line per action in the call, ids in the order `build` printed under
     `expect` (pre-order: the action's root, then nested containers top-down):
     ```
     w1.1 <root id>
     w1.2 <root id> <container id> <container id> …
     w2.3
     w2.4 ERROR <message from the result>
     ```
     The root id is `data.id.element`; container ids are each nested instance's `slots[0].id.element`.
     Actions sent with `return_component_info: false` (leaves that need no id, e.g. plain spacers) return
     `{inserted: true}`: write the label alone. `sbx.py` checks counts and id format; readback catches the rest.
   - `next-wave` → send the new call, repeat step 3. Waves are as deep as the deepest leaf that needs a write
     (typically 2–4 calls for any number of sections).
   - `inserted` → it wrote `<out>.props.json` and `<out>.finalize.json`. Go to 4.
   - exit 2 `build-failed` → send the rollback call it wrote **immediately**, save its result (or write the
     compact form: the `gone …` match counts and the parent's child ids) and run
     `sbx.py rollback-check --state state.json --result <file>`: every removed root must be gone and the
     parent's children must equal the snapshot. Report the failure. Nothing else is touched.
   - Every action failing with *"You cannot have more than 20 Collection Lists on a single page"* means the
     target page is at Webflow's Collection List cap: nothing was created; ask for another target page.
4. **Props.** Send `<out>.props.json` (`data_component_props_tool`, one action per instance, all its values).
   A failed action is not retried blindly: continue to finalize; verification decides.
5. **Finalize.** Send `<out>.finalize.json` (`data_element_tool`: `set_display_name` for named nodes, a page
   `get_all_elements`, and a deep `query_elements` per root). It is usually saved to a file; if inline,
   force it to file (repeat the call's read actions). Then `sbx.py verify --state state.json --registry reg.json --result <file> --out fix.call.json`.

| `verify` exit | Status | Do |
|---|---|---|
| 0 | `verified` | Report the `summary` line (and any `nameWarnings`). `placement.preExistingUntouched` confirms catalogue content; a `preExistingChanged` note means someone else changed the page meanwhile — report it, do not roll back. Done. |
| 3 | `values-mismatch` + `corrective` | Send the corrective props call once, resend the finalize call, verify again. |
| 2 | `structure-mismatch` / repeat `values-mismatch` | Send the rollback call written to `--out`, run `rollback-check`, report. |
| 4 | `unverified` (readback failed) | **Keep the structure.** Retry the finalize call once; if it fails again, report the built sections as unverified with their names and ids. Never roll back for a read failure. |

**Failure classes.** A *build failure* is an insert or structure error (failed action, wrong slot, missing or
extra instance, wrong order): roll back. A *value* problem gets one corrective write before rollback.
A *read failure* (transport error, 5xx, empty or unparseable readback) proves nothing about the page: keep
everything and report it as unverified.

**Rollback scope.** Only roots created by this build, from `state.json`. Removing a root removes its subtree.
When building into an existing slot, the roots are the inserted children, never the parent.
`sbx.py rollback --state state.json --out cleanup.json` writes the same call on demand (e.g. to remove
disposable test sections afterwards).

Terminal line: the `summary` (e.g. `Build complete: 2 sections, 30 instances, 44/44 values verified.`).

---

# MODE I — INSPECT (decompile)

1. Find the section: by display name in the Navigator, by the person's description, or from a recent build's
   `state.json`. `query_elements{element_id, children_depth:-1}` for known ids, or `get_all_elements` for the page.
2. `sbx.py decompile --registry reg.json --tree <saved result> [--ids id1,id2] [--out section.sml]`.
   Output is DSL with only non-default props. Display names are not in element reads; add `[name]` from
   `get_display_name` if needed.
3. To change a section: edit the DSL, build the new version next to it (Mode A), verify, then remove the old
   root only after the person confirms. In-place editing is not part of v6.

---

# MODE R — RENAME

Names describe purpose, not structure: `Hero · background image`, `Features · three cards`, `FAQ · accordion`.
Use `set_display_name` on the section roots (ids from the build's `state.json` or a decompile), one call for all.
`set_display_name` with `""` restores the automatic name. Never rename instances this skill did not create
unless the person names them.

---

# LIMITS (current MCP)

- Leaves nested in a single insert return no ids, hence waves. Each wave is one call regardless of section count.
- **Duplicate slot names (verified 2026-11-02, innvolve `card grid`, 5 slots named `Slot`).** MCP resolves a
  slot by name and always takes the first match, so only slot 1 can be filled headlessly. Tested and failed:
  nested `component_schema.slots` with five `Slot` entries (all children merged into slot 1); `insert_in_slot`
  with the slot id, the slot prop id, `Slot 4`, `5`, `Slot[2]`; the slot id as `insert_in_element` parent
  (with page, instance or component id); `move_element` into the instance (rejected), with a `prop`-scoped
  anchor (not found), or after an in-slot sibling instance (rejected). Not testable headlessly: the Designer
  itself. Readback does expose every slot id, so verification and decompile are exact. Fix at the source by
  giving the slots unique names in the component (not done by this skill), or fill slots 2+ in the Designer.
- Inline wave results need the ids file; everything else moves as saved files.
- Image and video props need asset ids/URLs the person supplies.
- There is no page delete; disposable test pages are deleted in the Designer.

---

# PRINCIPLE

Correct structure from the site's own components, proven by readback, with nothing outside the build touched.
