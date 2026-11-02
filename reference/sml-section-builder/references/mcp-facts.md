# Webflow MCP facts Section Builder relies on

Tested live against Webflow MCP 2.2.0 on two non-production SML sites on **2026-11-02**.
Retest any line marked ⚠ after an MCP upgrade. Everything else is load-bearing:
if it stops being true, `sbx.py` or the workflow in SKILL.md must change.

## Call envelope

- Every `data_*` call carries `session_id` and `agent_id`. Send `start` once per task, then
  the issued `ses_…` value on every call. `agent_id` is `<model>|<harness>|<suffix>`, fixed for the task.
- Element, component, builder and props tools take top-level `siteId` + `pageId` (camelCase) and `context`.
- Sites, pages and Agent Instructions tools take `site_id` (snake_case) inside each action.
- `data_component_tool.get_all_components` needs a `pageId` even though it is site-wide.

## Large results

- The harness saves a tool result to a file when it is larger than roughly 100K characters
  and returns it inline below that. The saved file is either concatenated JSON objects or a
  JSON array of `{type, text}` blocks. `sbx.py` reads both (`load_mcp`).
- **Force-to-file:** when a read must reach `sbx.py` as a file, repeat the same read action in
  one call until the result crosses the threshold (`get_all_components` ×4 on a 30-component
  site; the finalize call's `get_all_elements` on a busy page is usually enough by itself).
  Duplicated objects are de-duplicated by label.
- A 60K inline result is fine to read; never retype a large result by hand.

## data_component_builder

- `insert_in_element` and `insert_in_slot`, sequential `actions[]`. 40 inserts in one call
  succeeded, in order, with ids (~30KB response).
- With `return_component_info: true` the action returns:
  - the inserted instance's own element id (`data.id.element`), and
  - every nested **container** id via `instanceDetails.slots[].id.element` (the slot's owning instance),
  - default prop values (`hasOverride: false`) of every nested instance.
  It does **not** return ids of nested **leaves** (instances without slots). This is why
  Section Builder inserts leaves that need writes as their own action (waves).
- Without `return_component_info`: `insert_in_element` returns only the root id; `insert_in_slot`
  returns only `{inserted: true}`.
- `creation_position`: `append` and `prepend` work in slots; `before`/`after` in a slot are treated
  as append. Inserting `before`/`after` a component-instance anchor is rejected.
- Slots are addressed by runtime **name**, first match. Duplicate names (innvolve `card grid`: five slots
  named `Slot`) leave slots 2+ unreachable headlessly. Evidence, 2026-11-02 on a draft page:
  - nested `component_schema.slots` with five `Slot` entries → all five children in slot 1, slots 2–5 empty;
  - `insert_in_slot` with `slot_name` = slot id / slot prop id / `Slot 4` / `5` / `Slot[2]` →
    `Slot "…" not found. Available slots: Slot, Slot, Slot, Slot, Slot`;
  - `insert_in_element` with the slot id as element (page, instance or component id as component) → element not found;
  - `move_element` append/prepend to the instance → "Cannot append an element to a component instance";
    anchor `{instance, prop: slot id | slot prop id}` → "Anchor element not found";
    `after` an instance inside slot 1 → "Cannot move an element after a component instance".
  - `data_element_builder` creates plain elements only; `designer_tool` has no insertion action.
  - Slot ids in readback (`slots[].id.slot`) equal the definition's slot element ids and are distinct.
- A page at Webflow's Collection List cap refuses **every** component insert, even a plain `__dev — section`
  ("You cannot have more than 20 Collection Lists on a single page") — seen on the innvolve Components page,
  2026-11-02. Nothing is created; build on another page.
- A wrong (non-existent) parent id in `insert_in_slot` fails that action with `Element with id {…} not found.`;
  other actions in the call still run.
- Runtime slot names come from: the catalogue instance on the build target page, else the
  Slot element's display name, else its first class (e.g. `accordion__max-width`), else a probe insert.
- A failed action returns `status: "error"` with a message (e.g. `Slot "x" not found. Available slots: content`);
  earlier actions in the same call stay applied.

## data_component_props_tool

- One `set_component_instance_prop_values` per instance; all its values in one `values[]`.
- Variant: `{type: "string", string_value: <optionId>}`; `"base"` is a valid option id.
  Invalid ids are rejected with the allowed list.
- `headingTag`, `id`, `textContent`, `string`, image asset id (24 hex): `type: "string"`.
- `richText`: `rich_text_inner_text`, blank line (`\n\n`) between paragraphs. Markdown is not parsed.
- `boolean` **and `visibility`** props (section padding, tab/slide visibility): `type: "boolean"`.
  (v5.3 treated `visibility` as unwritable; it is writable.)
- Link: `{type: "link", link_mode: "url", link_to}`; `email`/`phone` modes also work.
- Result echoes each written value — not used for verification (readback is).

## data_element_tool

- `query_elements` with `element_id` + `children_depth: 1` on the wrapper returns its direct children cheaply
  (used by `rollback-check`).
- `query_elements` with `element_id` + `children_depth: -1` returns the full nested
  `instanceDetails` subtree with current values and `hasOverride` flags, but no ids for nested leaves.
- `query_elements.scope_element_id` returns 0 matches inside slots ⚠. Page-wide `component_filter` works.
- `get_all_elements{depth:-1}` returns the page tree; component instances carry `instanceDetails`.
- `get_all_elements{scope_component_id}` returns a component's **definition** tree: slot elements carry
  ids equal to runtime slot ids; helper bindings appear as `{sourceType: "prop", propId}`.
- Element reads do **not** include display names. `set_display_name` works on component instances;
  `get_display_name` reads one back.
- `remove_element` removes an instance with its whole subtree; a follow-up `query_elements` by id returns 0 matches.
- `move_element` relative to a component instance anchor is rejected ⚠.

## Pages, snapshots

- `create_page{duplicateOf, draft: true}` works headless. There is no page delete action:
  disposable pages must be deleted in the Designer.
- `element_snapshot_tool` fails headless ⚠ (needs the Designer bridge).

## Registry storage

- Agent Instructions `kind: "skill"`, paths under `sml-section-builder-registry/`. `create_instruction` on an existing
  path fails; use `update_instruction`. `read_instruction{resolve_references:false}` returns the stored markdown.
- A 23KB single-file payload stores and reads back byte-identically.
