# Webflow Client-First Reference — rules for Claude

This project is the persistent reference for how Blake builds Webflow sites. It is **brand-agnostic**: no brand colors, fonts, or components live here. When a website project links to this reference, follow these rules.

## Prime directives
1. Every Webflow site starts from the **Relume Style Guide** (Client-First flavor). Assume its classes, variables, and structure already exist in the project. **Where Relume and Finsweet docs differ, default to Relume's usage** (e.g. `padding-section-*` nested inside the container).
2. **Never create a new class when an existing utility or documented custom-class pattern can do the job.** Follow the class-creation ladder in `README.md`.
3. **Variables, never hexes.** All colors in new classes link Webflow variables (Primitives → Color Schemes). Same for radius/border via UI Styles variables and fonts via Typography variables.
4. Section theming is done by **color scheme** (Scheme 1–5 variable groups), never ad-hoc colors per section.
5. **Rem, not px** (1rem = 16px, inherited from browser); em for type-relative sizes. **Line-height is a Styles variable in rem or em on the 0.125 grid** (1 · 1.125 · 1.25 … 1.75) — never unitless, `%` or px; em for headings, rem for body/rich text. Exceptions: 14px type = .875rem, 2px tiny spacing, 1px borders stay 1px.
6. Primitives never link directly to classes — they feed **semantic tokens** (`[element]-[style]-[identifier]`, e.g. background-color-dark); classes link the semantic token. Never name a token after its color.
7. Class creation order matters (CSS specificity): spacing **size classes before direction classes**; the Global Styles embed symbol stays on every page.
8. **Vertical spacing is a utility, never a custom-class margin.** A gap between blocks is a `[margin]-[direction]` + `[margin]-[size]` wrapper or a `gap` on a layout class — never a margin baked into a grid/header class. Use the canonical headline ladder and the two section anatomies in `README.md` §6/§6a; layout gaps come from the rem gap scale only.
9. **No unnamed Div Blocks.** Every div gets a spacing-utility combo, a named custom class, or at minimum a Navigator name; a pure grouper gets `margin-bottom margin-0`. If it can't be named, delete it and let the parent's `gap` work.
10. **Every section carries a colour mode class**; no section hard-sets a text colour (no `text-color-white` combos sprinkled per section).
11. **A colour that doesn't exist yet** gets client approval → added to Brand Colors primitives → aliased into Color Modes → linked. Never typed inline.
12. **New classes go into the site's Style Guide page immediately**, not at the end of the build.
13. `heading-style-*` sets the look, the tag sets the outline — a card title is an `h3` with `heading-style-h6`, never a Div Block with a heading class.
14. **One section class per section.** `section_[name]` is named for that section and is never reused across unrelated sections or pages. "Reuse before creating" governs utilities and components, never section classes; two identical sections become a Component. (README §1)
15. **Style Guide first — utilities stack.** Query the Style Guide for an existing utility before creating any class; several existing globals on one element (`subheading max-width-small align-center`) is the preferred solution. A new class or combo never carries a property a utility owns (width → `max-width-*`, centring → `align-center`, icon size → `icon-1x1-*`, type → `text-*`, column count → `is-N-col`). (README §3)
16. **Text colour comes from the Colour Mode.** Never on a text element or custom class; the only escape is an EXISTING `text-color-*` utility. Never create a new `text-color-*`; never a light/dark variant combo (`is-inverse`, `is-dark`, `is-on-dark` …) — inverting anything is a Colour Mode swap, and a mode can be set on any class (base mode on a white card inside a dark section). (README §12b)
17. **Repeating-item containers use the shared vocabulary**: `keypoint-row` / `keypoint-list` / `keypoint-grid` / `card-grid`, column count always an `is-N-col` combo, `-list` = one column, `-grid` = two or more; bullet lists are Rich Text with one shared list class; `section-header` is centred by default, `is-left` combo otherwise. Never a per-section `[name]_grid`/`_list`. (README §17)
18. **Section backgrounds — one mechanism**: `section_[name]` + `.section-bg` combo, Background Patterns component as first child, Colour Mode + Surface Treatment as variable modes on the section, layers `z-index: 0` / content `z-index: 1`, never a gradient on a layer class. (README §18)
19. **Cards are the Card component**, never hand-rolled from markup, memory or a screenshot; extend the component if the variant is missing. Icons are never omitted — missing asset → stop and ask. (README §15b)
20. **Webflow-native, hard rule**: no new custom code without the user approving the specific snippet (then one known place, mirrored to a project file); every state visible natively as an `is-*` combo; every CTA is the Button component; icons only from the approved SVG set; variable-link at class creation, never "later". (README §15a)
21. **Page shell on every page** — Body → `page-wrapper` → `main-wrapper` → sections; `page-wrapper` uses `overflow: clip`, never `hidden` (kills sticky). (README §1)
22. **Base tag styles do the rich-text work** — scale/weight/line-height on `h2`/`h3`/`p`/`li`/`blockquote` tags; never a `text-align` on a base tag. (README §5)
23. **Never delete user-supplied reference material** — a copied section/component/CMS list/card IS the spec; reuse it in place. **Build the whole section**, never part of it with "the rest flagged".
24. **Units by what they scale with** (README §20). rem is the default. em is for type-relative values inside components. % is for parent-relative widths, fr for grid tracks, px for 1px borders only.
    - **Font size has three tiers.** Body, UI and small text: fixed rem, never vw. Normal headings: fixed rem, stepped per breakpoint (the Client-First default). Display type only (deliberately screen-scaled editorial headlines): vw allowed, on a heading or display style only, with a rem ceiling at large breakpoints and a mobile floor, and documented on the Style Guide page.
    - `clamp()` is optional, for display type only, when stepped overrides can't hold the design.
    - Full-height uses `min-height` in `svh`/`dvh`, never `vh`.
25. **Every section is a Component** named `Section — [Name]`, and repeating items are `Item — [Name]` (README §21). Client-First classes stay inside.
    - Every text, image and link element is a prop. Every button has label, link and visibility props. Every optional element has a visibility toggle.
    - Colour Mode, Surface Treatment and layouts are **named variants**, never booleans.
    - Slot names are unique. Structured content goes in fields or items, not rich text. Defaults describe the field: no fake quotes or stats, no `#` links.
    - Every site ships a draft **Starter** page and a **`/stylesheet/components`** catalogue page showing every component in every variant.

## Section done checklist
A section is not "built" until all five are true IN THE SAME TURN:
1. `section_[unique-name]` — named for that section, used nowhere else.
2. The `.section-bg` combo applied to it.
3. A Background Patterns component instance as the section's FIRST child.
4. Colour Mode set on the section.
5. Content wrapper has `position: relative; z-index: 1`.

Missing any one is a defect to report in chat — never a silent "owed later" line in a plan file.

## Process rules
0. **A design pattern is never a copy instruction.** When one mockup "covers" several pages, it covers the LAYOUT — each page keeps its own live copy and functional embeds (schedulers, forms). Deleting a page's distinct content to clone another page's copy is the same defect as deleting reference material. If layout and live content conflict, stop and ask.
1. **Re-read the mockup fresh, in the same turn, before any build.** Users edit files between turns. Restate the section list and per-section spec (columns, gaps, counts, sizes) from THAT read; build only what exists in the current file; say what was verified vs what needs a visual check.
2. **Never map element ids to sections by assumed build order.** Query the actual text/children of a target before editing; after filling a page, read back every section's `h2` + first body element and verify each header matches its body against the mockup. Verification is reading real text back, not remembering what you built.
3. **Copying an existing pattern? Read its element tree first** (`query_elements`, depth 5–6), then reproduce element-for-element, tags included, and read its bindings. Never rebuild a known pattern from a screenshot, class-name guess or memory. If the pattern already exists on another page, **ask the user to copy-paste it in the Designer** — far cheaper than rebuilding via API.
4. **Report defects in chat, in the turn they happen** — with the exact Designer click needed. Never bury an owed item in a plan file.
5. Webflow MCP/API gotchas (`set_style` replaces the class list, `grid-row-gap` not `row-gap`, longhands only, no variable creation via API …) are in `README.md` §19 — read it before any API build.
6. **Connect each project on its own.** Before the first MCP/API build on a site, set up a project-scoped Webflow server per `docs/webflow-project-connection.md`; never repoint the shared claude.ai connector.

## Built for handoff (doctrine)
These sites are handed to the client to manage.
- **If it can be done in Webflow, it is done in Webflow.** Custom code is a last resort, never a shortcut — "can this be a native element, interaction, component, or variable?" must be a genuine no. Unavoidable code carries a comment saying what it does and why it couldn't be native.
- **Components, not copies.** Every section ships as a `Section — [Name]` Component with props (directive 25). When two sections are the same, or marginally different but structurally the same, they're **one Component with a variant**. Differing only in copy, colour mode, column count or image side = one component.
- **Clients compose, they don't build.** Hand off through Build Mode: clients duplicate the Starter, add section components and edit props. Initialize the page-builder registry on the site and ship a short client guide (README §21).
- **Pages from content**: never leave visible default text or `#` links. An unknown destination stays an unlinked visible button, and is reported. Never silently drop a source section. Draft only, never publish.
- **Animations are Webflow Interactions**, not GSAP/scripts/keyframe embeds, unless genuinely impossible natively.

## Mockups vs Webflow builds
- **Claude Design mockups**: make them visually correct for the brand. Do NOT annotate with class names or force class-name fidelity — naming does not matter at mockup stage.
- **When converting to Webflow** (build specs, class lists, "how do I build this" answers): use exact Client-First naming per `README.md` and `Style Guide.dc.html`. Structure every page as `page-wrapper → main-wrapper → section_[name] → padding-global → container-* → padding-section-*`.

## Naming quick reference
- Custom: `[component]_[element]`, lowercase, hyphens inside words, underscore = folder separator. Sections: `section_home-hero`.
- Utilities: dashes only (`heading-style-h2`, `text-size-medium`, `padding-global`).
- Variants: `is-*` combo stacked on a base class (`button is-secondary`). Max ~2 combos.
- No abbreviations, no shorthand. Read a class name and know its purpose.

## Source of truth
- `README.md` is the **only** source of rules: structure, type scale, spacing scale, buttons, forms, utilities, breakpoints, variables, class policy, handoff doctrine, container vocabulary (§17), section backgrounds (§18), Webflow API gotchas (§19), units + font-size tiers (§20), section components + client editing (§21), repo layout + brand wiring (§22).
- `views/Style Guide.html` and `views/Build Standards.html` are visual renderings of the README. If one disagrees with the README, the README wins.
- `docs/webflow-project-connection.md` is the per-project Webflow connection setup (procedure, not build rules).
- `reference/` (SML page/section builder) is comparison material only. Never follow it as a rule.
- Canon: Finsweet Client-First docs (finsweet.com/client-first/docs) + Relume Style Guide for Webflow. Relume's guide = Client-First with a differently organized style-guide page; components in Relume Library follow the naming used here.
