# Webflow Client-First Reference (Relume Style Guide format)

Brand-agnostic reference for building every Webflow project on **Finsweet Client-First** conventions as shipped in the **Relume Style Guide**. Rendered specimens: `Style Guide.dc.html`. Build rules from real-build audits, rendered: `Build Standards.dc.html`. Values verified against finsweet.com/client-first/docs (2026-08).

## 1 · Page structure
Every page, always:

```
page-wrapper
└─ main-wrapper                     (main tag)
   └─ section_[name]                (section tag, e.g. section_home-hero)
      └─ padding-global             (left/right padding: 5%)
         └─ container-large|medium|small   (max-width, margin auto)
            └─ padding-section-large|medium|small   (top/bottom padding)
               └─ …content…
```

Six core-structure classes total. **Default: the Relume pattern** — `padding-section-[size]` nested inside the container (as in the tree above), matching Relume's Webflow templates. (Finsweet's docs put it on the same div as `padding-global` to reduce nesting; only follow that when a project already does.)

- `page-wrapper` — outermost div; barely styled. Exists so `body` styles stay limited to typography + background-color, and for page-level needs like overflow:hidden (caution: kills nested CSS sticky).
- `main-wrapper` — `<main>` tag for accessibility. Nav and footer live OUTSIDE it.
- `section_[name]` — `<section>` tag; a Navigator "sitemap" for clients. Avoid styling it; unique section padding may go here. Recurring section treatments use a global add-on class (e.g. `section-style-dark`) stacked on the custom `section_` class — never re-declare the same properties per section.
- `padding-global` — ONLY padding-left/right (5%). Never other properties, never for content-item spacing. Decoupled from container so either can be used independently (parent or child of `container-*`).
- Containers: `container-large` 80rem · `container-medium` 64rem · `container-small` 48rem — width 100%, margin auto. Edit/add/remove sizes per project.
- Section padding (desktop → mobile): `padding-section-large` 7rem → 4rem · `medium` 5rem → 3rem · `small` 3rem → 2rem (Relume defaults; edit values, keep names).
- The **Global Styles embed** (see §13) ships with the cloneable — keep the symbol on every page.

**One section class per section.** `section_[name]` is named for THAT section and is not a shared shell. Never reuse a section class across unrelated sections or pages. The failure: one `section_form-hero` applied to seven form pages plus two unrelated pages — every later tweak to it (colour mode, padding, the background combo) silently changed every other page. The "reuse before creating" rule (§3) governs UTILITIES and COMPONENTS, never section classes. Two sections that are genuinely the same thing become a Component (§15), not one shared class.

**Page shell on every page: Body → `page-wrapper` → `main-wrapper` → sections.** Never insert sections directly into Body; when rebuilding a legacy page whose tree lacks the wrappers, create them first. `page-wrapper` containment is **`overflow: clip`, never `hidden`** (or `overflow-x: hidden`, which forces `overflow-y: auto`) — `hidden` makes the wrapper the scroll container and disables `position: sticky` site-wide. Check this first whenever a sticky element refuses to stick.

## 2 · Class naming
- **Custom classes** contain `_` : `[component]_[element]` — `home-hero_content`, `faq_item`, `footer_link`. Underscore = folder separator (Finsweet Extension folders); hyphens join words inside a segment. Lowercase, no abbreviations.
- **Utility classes** contain no `_` : `text-size-medium`, `padding-global`, `hide-tablet`.
- **Combo classes**: `is-*` variants stacked on a base (`button is-secondary`). A combo only adds styles on top of its base. Never stack more than ~2.
- Never rename or restyle core Client-First utility classes to solve a one-off.

## 3 · Class-creation ladder (avoid new classes)
When styling an element, in order:
1. **No class** — inherit from body/parent.
2. **Existing utility** — structure, spacing, typography utilities below.
3. **Existing custom class** — reuse global custom classes (`faq_item` across all FAQ sections).
4. **`is-*` combo** on an existing base for a variant.
5. **New custom class** `[component]_[element]` — only when the element needs CSS the utilities can't express (grids, unique spacing across breakpoints, component styling). This is normal Client-First — custom classes are encouraged for components — but never duplicate what a utility already does.

**Style Guide first.** Before creating ANY class, query the Style Guide for an existing utility. The Relume guide already ships `max-width-*` (xxsmall→xxlarge + full), `align-center`, `icon-1x1-*`, `text-size-*`, `text-weight-*`, `text-align-*` and the spacing utilities.

- **Utilities stack.** Several existing globals on one element (`subheading max-width-small align-center`) is a legal, preferred solution and is how a "new" need is usually met. Check for a stack before reaching for step 4 or 5.
- **A new class or combo must never carry a property a utility owns.** Width → `max-width-*`; centring → `align-center`; icon size → `icon-1x1-*`; type → `text-*`; column count → `is-N-col` (§17).

Recorded anti-patterns (each reverted at the client's expense): a `button-group.is-center` combo when `.button-group.align-center` existed · a `.subheading.align-center` combo carrying a max-width (should have been the utility stack) · a bespoke row class when `keypoint-row` + an icon utility + `text-size-medium` covered it.

Never: hard-coded hex in a new class (link a variable) · editing a utility's styles for one instance · utility-only "Tailwind-style" stacking for whole components.

**Every new class goes into the site's Style Guide page immediately** — not at the end of the build, not "once it settles." A class that exists only inside one section on one page is invisible to whoever builds the next page, and gets rebuilt under a second name. The Style Guide page is the client's inventory of what they own.

## 3a · No unnamed Div Blocks
Every div gets, in order of preference: (1) a spacing-utility combo, (2) a named custom class, (3) at minimum a Navigator display name. A purely structural grouper that needs no space of its own gets `margin-bottom margin-0` — zero visual effect, but it reads as a deliberate wrapper instead of a mystery div, and costs no new class. If it can't be named, delete it and let the parent's `gap` do the work.

Why they appear (all three are legitimate structure — the mistake is leaving them anonymous):
- Grid/flex parents need children grouped so the `gap` lands in the right place, and a grouper carrying no styles "doesn't need a class."
- Pasted markup arrives with classless wrappers.
- Title+copy pairs get wrapped so a card's `gap` spaces icon-vs-text separately from title-vs-body.

Name them `[component]_content`, `[component]_item-text`.

## 4 · Variables (Webflow ▸ Variables)
Always link variables, never raw values, in new classes.

**When the colour you need doesn't exist**: it gets added to the Brand Colors primitives collection **with client approval**, then aliased into Color Modes, then linked. Never typed inline as a one-off. A stray hex never fails review because it looks right — and it is exactly what makes a site un-rebrandable.
- **Primitives**: White, Black, Neutral ramp (Lightest → Darkest), `Brand/*` group for brand colors (e.g. `Brand/Primary-500`).
- **Color Schemes 1–5**: each scheme = Background · Foreground · Text · Border · Accent, linked to primitives. Theme a section by applying its scheme (scheme class `color-scheme-[n]` or scheme variables on the section) — never ad-hoc colors.
- **Typography**: Heading font · Body font (map brand fonts here).
- **UI Styles**: Radius small/medium/large · Border width · Divider width.

## 4a · Sizes and rem
- Work in **rem** for sizes; **em** for type-relative sizes (letter-spacing, heading line-height); **line-height is a rem/em Styles variable** on the 0.125 grid (§12b) — never unitless, `%` or px. Browser default 16px = 1rem, inherited from the browser (never set a px font-size on `html`) — this is what makes browser font-size settings and zoom accessible.
- Prefer clean values (.5, 1, 1.5, 2, 2.5, 3, 4, 5…): px ÷ 16 = rem. Type `100/16rem` in a Designer input to auto-calculate.
- Exceptions: 14px type = .875rem is fine; tiny spacing may use 2px = .125rem; **1px borders stay 1px** (never rem — retina scaling).

## 5 · Typography
Headings default to their HTML tag; use `heading-style-h1…h6` only when style ≠ semantic tag (e.g. H2 styled as H3 for SEO). One H1 per page.

Corollary (the one that keeps getting broken): a card title is an `h3` carrying `heading-style-h6` — never a Div Block carrying a heading class. `heading-style-*` sets the look; the tag sets the document outline.

**Base tag styles do the rich-text work.** Base HTML tag styles (`h2`, `h3`, `blockquote`, `p`, `li`) are the mechanism for giving CMS rich text brand type without nested selectors or per-post classes — set scale, weight and line-height on the tags and let `heading-style-*` utilities override where applied. Corollaries: never leave a `text-align` on a base tag (an `h1` tag style carrying `text-align: left` fought every centred hero); tag weights follow the brand's heading weight, not the template's 700.

Default scale (desktop, 1rem = 16px — override values per brand, keep class names):
- h1 3.5rem · h2 3rem · h3 2.5rem · h4 2rem · h5 1.5rem · h6 1.25rem — headings 700, line-height 1.25em (h4–h6 1.375em). Mobile: h1 2.5rem · h2 2.25rem · h3 2rem · h4 1.5rem.
- `text-size-large` 1.25rem · `medium` 1.125rem · `regular` 1rem · `small` .875rem · `tiny` .75rem — body line-height 1.5rem (variable; see §12b for the line-height grid).
- `text-weight-light` 300 · `normal` 400 · `medium` 500 · `semibold` 600 · `bold` 700 · `xbold` 800.
- `text-style-italic` · `strikethrough` · `allcaps` · `nowrap` · `quote` · `link` · `muted` · `2lines` · `3lines` (line clamp).
- `text-align-left` / `center` / `right`.
- `text-color-primary` / `secondary` / `alternate` + `background-color-primary` / `secondary` / `tertiary` / `alternate` — each linked to its semantic color variable, never a raw hex.
- `text-rich-text` on every Rich Text element.

## 6 · Spacing
Two systems, both from the cloneable — pick per situation, values in rem:

**Scale** (official values, shared by margin/padding/spacer): `0` 0 · `tiny` .125 · `xxsmall` .25 · `xsmall` .5 · `small` 1 · `medium` 2 · `large` 3 · `xlarge` 4 · `xxlarge` 5 · `huge` 6 · `xhuge` 8 · `xxhuge` 12 · `custom1` 1.5 · `custom2` 2.5 · `custom3` 3.5 (rem).

- **Spacing wrappers**: `[margin|padding]-[direction]` + `[margin|padding]-[size]` combo — directions: `top` `bottom` `left` `right` `vertical` `horizontal`. Applied to a wrapper div around the element, or directly per spacing strategy.
- **Spacer blocks**: `spacer-[size]` empty div creates vertical space between siblings.
- Prefer CSS grid/flex `gap` on a parent (custom class) for lists of children; use spacing utilities for one-off rhythm.

**Vertical spacing is a utility, never a custom-class margin.** A vertical gap between blocks is a `[margin]-[direction]` + `[margin]-[size]` wrapper, or a `gap` on a layout class. Nothing else. Margin on a custom class is reserved for genuinely unique per-breakpoint spacing a wrapper cannot express, and it must sit on the spacing scale.

Why: a margin baked into a grid class is invisible in the Navigator, unreachable for a client, and gets copied into the next section as a new class. A `margin-bottom margin-large` wrapper reads itself out loud and is the same object on every page. (Audit, Aug 2026: seven sections, five different mechanisms producing the same header→body gap — a margin-top inside a grid class, an 88px margin on a header class, a px value, a rem value, and nothing at all.)

**Gap scale for layout classes**: column/row gaps come from `0.5 / 1 / 1.5 / 2 / 3 / 4 / 5rem` only, always rem. Mixed px gaps don't respond to the root font-size step-down at tablet — which is why some sections tighten correctly on mid-size screens and others don't.

## 6a · Headline ladder (canonical)
The relationships, not just the scale:

| Relationship | Wrapper | Value |
|---|---|---|
| eyebrow → heading | none — the eyebrow class owns its own bottom margin | — |
| [eyebrow + heading] → subheadline | `margin-bottom margin-xsmall` | 0.5rem |
| headline block → body, **centered** sections | `margin-bottom margin-large` | 3rem |
| headline block → body, **split two-column** sections | `margin-bottom margin-small` | 1rem |
| body → button group | `margin-top margin-large` | 3rem |
| card internals (icon → title → copy) | `gap` on the card's own class | scale |

Most sections are one of two anatomies. Copy these trees rather than inventing a third:

**A · Centered header + grid**
```
section_[name]
└─ padding-global › container-large › padding-section-large
   ├─ margin-bottom margin-large        (header wrapper)
   │  └─ section-header                 (shared class: max-width + text-align-center)
   │     ├─ [eyebrow]                   (owns its own bottom margin)
   │     ├─ h2
   │     └─ margin-bottom margin-xsmall › subheadline
   ├─ [name]_grid                       (gap from the gap scale)
   │  └─ [name]_card ×n                 (gap on the card class for internals)
   └─ margin-top margin-large           (button wrapper)
      └─ button-group
```

**B · Split two-column**
```
section_[name]
└─ padding-global › container-large › padding-section-large
   └─ [name]_layout                     (grid 1fr 1fr, gap from the gap scale)
      ├─ [name]_visual
      └─ [name]_content
         ├─ [eyebrow]
         ├─ h2
         ├─ margin-bottom margin-small  (headline block → body)
         │  └─ subheadline
         ├─ [name]_content-body
         └─ margin-top margin-large › button-group
```

## 7 · Buttons
Official Client-First cloneable ships `button` · `button is-secondary` · `button is-text`. The **Relume set** (what we assume) extends the same pattern:
- `button` — primary. Default: dark bg, light text, padding .75rem 1.5rem, radius = UI Styles radius.
- `button is-secondary` — transparent bg, 1px border currentColor.
- `button is-link` — no padding/bg, text + underline treatment.
- `button is-icon` — flex row, .75rem gap for icon + label.
- `button is-small` — padding .5rem 1.25rem.
- `is-alternate` / `is-secondary-alternate` / `is-link-alternate` — inverted versions for dark scheme sections.
- Form **submit buttons do not inherit** `button` hover states — restyle explicitly.

## 8 · Forms
`form_component` (wrapper) → `form_form` → fields:
- `form_field-label` · `form_input` (min-height ~3rem) · `form_input is-text-area` · `form_checkbox` (+ `form_checkbox-icon`, `form_checkbox-label`) · `form_radio` · `form_message-success` · `form_message-error`.
- Style states: focus (via global embed), error, success. Placeholder color from neutrals.

## 9 · Icons
`icon-height-small` 1rem · `medium` 2rem · `large` 3rem (height only) · `icon-1x1-small/medium/large` (height + width). SVGs inherit color via `inherit-color` + `currentColor`.

## 10 · Misc utilities
- `hide` · `hide-tablet` · `hide-mobile-landscape` · `hide-mobile-portrait` — display:none at that breakpoint and below (enforced with !important in the global embed).
- `display-inlineflex` — inline-flex (not natively settable in Webflow); lets flex elements behave inline, e.g. buttons.
- `overflow-visible/hidden/auto/scroll` · `pointer-events-auto/none` · `spacing-clean` (all margin+padding 0 — great for resetting native Webflow components) · `align-center` (margin l/r auto) · `z-index-1/2` · `inherit-color` (children inherit color — pairs with currentColor SVGs and color-linked text) · `aspect-ratio-square` 1:1 / `portrait` 2:3 / `landscape` 3:2 / `widescreen` 16:9.
- `layer` — position:absolute, 0 on all sides, fills parent (parent needs non-static position).
- `max-width-xxlarge` 80rem · `xlarge` 64rem · `large` 48rem · `medium` 32rem · `small` 20rem · `xsmall` 16rem · `xxsmall` 12rem · `max-width-full` (max-width:none) + `-full-tablet` / `-full-mobile-landscape` / `-full-mobile-portrait`. Use `container-*` for outer page width; `max-width-*` for content nested inside a container.

## 11 · Breakpoints
- **Base = Desktop (992–1279)** — all base styles live here. Style **down** only.
- 1280 / 1440 / 1920 — leave empty by default; rem-based sizing scales instead. Never put base styles on larger breakpoints.
- Tablet ≤991 · Mobile landscape ≤767 · Mobile portrait ≤479.
- Use rem for type/space/size; px only for borders/hairlines. 1rem = 16px. Full unit rules incl. font-size tiers: §20. Exception to "leave large breakpoints empty": tier-3 display type sets its rem ceiling there.

## 12a · Variables strategy (primitives vs semantic)
- **Primitives** ("Base Color" prefix in the cloneable) are raw values: Brand colors, Neutral colors, System colors groups. **Avoid linking primitives directly to classes** — link them into semantic tokens first.
- **Semantic tokens** name purpose, not color: `[element]-[style]-[identifier]` → `background-color-dark`, `text-color-primary`, `border-color-brand`. Never name a semantic token after its color (breaks theming). Classes and the `text-color-*`/`background-color-*` utilities link semantic tokens.
- Primary/alternate concept: `alternate` = the inverse of primary for opposite grounds (dark section text, etc.).
- Avoid linking a color directly on text elements when children should inherit — set color on the parent; use `inherit-color` to force inheritance where a linked color is in the way.
- If the client has an established color system/naming, follow theirs.

## 12b · Variables — Modes architecture
Organize Webflow Variables into **four collections**, not one flat set:
- **Brand Colors** — primitives only, grouped `Core/`, `Accent/`, `Accessible/`, `Extended/`. Raw hex values live ONLY here.
- **Fonts** — one font-family variable per role (`Headings`, `Body`, `Secondary`). A rebrand is a value swap — no relinking anywhere.
- **Styles** — size/number variables: radius, spacing scale, font sizes, button padding, **line-heights** (rem/em, 0.125 grid).
- **Color Modes** — semantic color variables grouped `Text/` (Heading, Body, Muted), `Section/` (Background, Accent), `Button/` (Background, Text). Every value ALIASES a Brand Colors primitive — never raw hex. One mode per color scheme: **Base** + named modes (e.g. Smoke, Midnight), each overriding only the values that differ from Base.

Wiring rules:
- Tag selectors and classes link ONLY Color Modes semantic variables — never primitives directly.
- `color-scheme-[n]` classes carry the background+color links AND pin the collection's mode — applying the class to a `section_` flips every semantic variable inside it. The client themes sections from a dropdown.
- Buttons and accents linked to `Button/*` and `Section/Accent` invert automatically per mode.
- Units: padding/margins/font-size in **rem**, letter-spacing in **em**, line-height a **Styles variable in rem or em, stepped in 0.125 increments** (1 · 1.125 · 1.25 · 1.375 · 1.5 · 1.625 · 1.75) — never raw `%`, never px, never a typed unitless number on a class. A unitless value can't be a Webflow variable, so the scale's line-heights couldn't be swapped in a rebrand or kept consistent across heading utilities and base tag styles. `em` where the value tracks its own font size (headings); `rem` where it must hold regardless of size (body, rich text).

**Every section carries a colour mode.** Every `section_[name]` gets a colour-mode class, so text, headings, links, borders and buttons invert from the background automatically — and **no section hard-sets a text colour**. Failure mode to watch for: `heading-style-h2 text-color-white` combos multiplying across a site because sections were themed by hand.

**Text colour comes from the section's Colour Mode.** Never put a text colour on a text element or a custom class. When ONE element genuinely needs a different colour inside a mode, the only sanctioned escape is an EXISTING `text-color-*` utility (each links a semantic variable and leaves the mode's other values intact). Never create a new `text-color-*`. Never a light/dark VARIANT COMBO (`is-inverse`, `is-dark`, `is-on-dark`, `is-midnight` …) — inverting a section, card or panel is a Colour Mode swap, never a class. A Colour Mode can be set on ANY class, not just a section: putting the base mode on a white card class is the native way to keep dark text inside a dark section.

## 13 · Global Styles embed
A symbol with an Embed block of site-wide CSS — on every page, inside Designer (visible on canvas; NOT site-settings custom code). It ships with: text antialiasing; unified keyboard focus-visible outline; rich-text first/last-child margin removal; `container-*` margin-auto !important lock; `inherit-color`; **!important declarations** locking `hide*`, `margin/padding-0`, and every direction class so utilities always win. (An optional, off-by-default snippet makes native Webflow elements inherit styles — enabling it disables "All links"-style global edits.) Don't delete lines you don't understand.

## 14 · CSS specificity (order of creation)
Webflow writes classes to the stylesheet in creation order; **later classes win conflicts**. Practical rules:
- The spacing system only works because size classes (`margin-large`) were created BEFORE direction classes (`margin-top`). When copying the system between projects, paste **sizes first, then directions** (or use the official cloneable / Finsweet Extension, which order correctly).
- A truly global utility (e.g. `display-none`-style workflow classes) must sit LATE in the stylesheet to override anything; the global embed's !important declarations are the failsafe.
- Finsweet Extension ▸ CSS Styles Reorder fixes creation-order problems after the fact.

## 15 · Built for handoff
These sites get handed to the client to manage. Every build decision is judged on whether they can still run it.
- **If it can be done in Webflow, it is done in Webflow.** Custom code is a last resort, never a shortcut. Before writing any: "can this be a native element, an interaction, a component, or a variable?" has to be a genuine no. When unavoidable (third-party embed, form, calculator), it carries a comment saying what it does and why it couldn't be native.
- **Components, not copies.** Anything appearing more than once is a Component with props. Two sections differing only in copy, colour mode, or column count are one component. Standing instruction for Claude: when two sections are the same — or marginally different but structurally the same — **flag it and propose one Component with a variant** instead of building the near-duplicate.
- **Animations are Webflow Interactions** — not GSAP, not a script, not a CSS keyframe block in an embed, unless the effect is genuinely impossible natively. An interaction is visible, editable and disable-able by the client in the Designer; a scripted animation is a black box they will eventually break and can't fix.

### 15a · Webflow-native first — hard rules
- **No new custom code** — no HtmlEmbeds, style tags or JS — unless the user approves that specific snippet first. When approved it lives in ONE known place (site head/footer code, or one named page embed) and is mirrored to a file in the project.
- **Every state must be visible in the Designer natively.** Interactive states are combo classes (`is-active` etc.) carrying real Designer properties; the first/default state renders with JS off. Embed-only CSS states are a defect.
- **Every CTA is the Button component** — never a styled TextLink, div or anchor embed.
- **Icons come only from the approved SVG icon-asset set** — never legacy PNGs, never improvised glyphs. Missing asset → upload it or stop and say so; never substitute.
- **Variable-link at build time.** Colours, fonts, radii and line-heights link variables when the class is created. "Variable pass owed later" is not acceptable.
- Page shell and `overflow: clip` rules: see §1.

### 15b · Cards are a Component, never hand-rolled
The card is the most-repeated element on any marketing site and the most broken when improvised.
- **Never build a card from markup, memory or a screenshot.** The only legal way to place a card is an instance of the site's Card component (props + variants cover CMS, photo, icon, static and feature cards). If the variant needed doesn't exist, extend the component.
- A card's decorative behaviour (masks, hover reveals, image zoom) lives in ONE sitewide place (site head code), never in a page embed — page-scoped CSS leaves every card on every other page square and static.
- **Icons are never omitted.** If the design carries an icon and the approved asset isn't uploaded, stop and ask. An icon-less card is a defect, not a simplification.
- **Never delete user-supplied reference material.** When the user copies a section, component, CMS list or card into a page for reference, that copy IS the spec — reuse it in place (retitle, rebind, restyle within its own classes). Removing it and building a replacement is never acceptable, even when the new content is static and the reference is CMS-bound.
- **Build the whole section.** Restate the section's full block list from the mockup and build all of it; shipping part of a section and "flagging the rest" is not a scope call to self-authorise.

## 16 · Applying a brand
This reference stays neutral. A brand maps onto it by: linking brand primitives into the Color Scheme variables, setting Typography variables (Heading/Body font) and heading/text sizes on the existing classes, setting UI Styles radius/borders, and restyling `button` combos — **without renaming any class**. See the linked brand design system for values; see this project for names and structure.

## 17 · Repeating-item containers — one vocabulary
Any container holding a repeating set of items uses one of four shared, unprefixed classes. A section never gets its own `[name]_grid` / `[name]_list` again.

| Class | What it is | Layout |
|---|---|---|
| `keypoint-row` | one icon/chip + text item | flex, align start, 1rem gap |
| `keypoint-list` | those rows STACKED in one column | flex column, 1.5rem row gap |
| `keypoint-grid` | the same rows in COLUMNS | grid, 2-up default, 2rem gaps |
| `card-grid` | a grid of card/tile elements | grid, 2-up default, 1.5rem gaps, align stretch |

- Cards keep their own `[name]_card` class for the surface; the grid is shared.
- **Column count is ALWAYS an `is-N-col` combo** (`card-grid is-3-col`, `keypoint-grid is-3-col`). Never a new class, never a re-declared `grid-template-columns` on a custom class.
- **Naming law**: `-list` = single stacked column; `-grid` = two or more columns. A multi-column container named `_list` is a defect.
- **Choosing**: stacked when items are read in sequence beside a supporting image; gridded when scanned as a set.
- **Bullet lists are none of these.** A plain bullet list is a Rich Text (or `ul`) carrying one shared list class — never keypoint-rows with empty chips, never a new list class per section.
- `section-header` is CENTRED by default (max-width + margin auto + text-align center). Left-aligned header = the `section-header is-left` combo — never a new header class, never a per-element text-align.
- Gaps: keypoint containers 1.5rem stacked / 2rem gridded; card containers 1.5rem; rem only, from the §6 gap scale.

## 18 · Section backgrounds — three controls, fixed mechanisms
Every section is built the same one way, no new mechanisms: `section_[name]` + the `.section-bg` combo, a **Background Patterns** component instance as first child, Colour Mode set on the section.

- `.section-bg` = `position: relative` + `overflow: hidden` + `background-color` bound to the `Section/Background` variable. Added AFTER the section class, never instead of it — the section class still owns padding/height/layout. The section's fill lives on `.section-bg`, never baked into the section class.
- The content wrapper gets `position: relative; z-index: 1`, or the opaque layers cover the copy ("my text disappeared").
- **Three controls, each with a FIXED mechanism.** A variable mode can only swap a value, never change `display`, so anything DRAWN lives in a component variant and anything COLOURED lives in a variable mode:
  - **Colour Mode** = variable mode on the section. Drives fill, all text, eyebrow, border, button colour and every `Surface/*` alias the layers read.
  - **Surface Treatment** = variable mode on the section (None / vignette / bloom left / bloom right). Recolours the layers; a transparent layer is an absent layer.
  - **Background Pattern** = variant on the Background Patterns component (None / patterns…). One instance, first child, pick the variant, leave it alone. Treatment and pattern are independent.
- **Stacking**: layers `z-index: 0`, content `z-index: 1`. Only those two numbers, never `-1`. Anything else absolutely positioned inside the section (decorative dots, floating cards, badges) also needs `z-index: 1`.
- **Never draw a gradient on `.section-bg` or any layer class** — Webflow bakes gradient stops at draw time, so the layer stops responding to modes. Layer colours are always a `background-color` bound to a variable. Never show/hide a layer by hand.
- Order of operations: shell → add `.section-bg` → Colour Mode + Surface Treatment → drop the Background Patterns instance as first child → content wrapper `relative; z-index 1`.
- Symptom → cause: pattern layers stretching the whole page = the section is missing `.section-bg` (the component is absolutely positioned and escaped to `page-wrapper`). Fix by adding the class, never by hand-setting `position` on the section class.
- New colours for layers → primitives with approval, then aliased into Color Modes as `Surface/*` semantic variables that the layers read.

**Section done checklist** — a section is not "built" until all five are true in the same turn: (1) `section_[unique-name]`, used nowhere else · (2) `.section-bg` combo applied · (3) Background Patterns instance as FIRST child · (4) Colour Mode set on the section · (5) content wrapper `position: relative; z-index: 1`. Missing any one is a defect to report in chat.

## 19 · Webflow MCP / API gotchas
Tool-specific, but they recur on every site.
- **`set_style` REPLACES an element's whole class list** — read `styleNames` first, never pass a partial list (a blind `is-left` combo wiped `padding-global` off a hero wrapper).
- `set_style` only accepts an EXISTING base+combo chain; two independent globals fail. Create the combo (`create_style` with `parent_style_names`) first — or, for a stack of existing globals, use the element builder's `class` attribute, which accepts several.
- **Gaps must be written `grid-row-gap` / `grid-column-gap`.** Plain `row-gap` / `column-gap` land in the class's Custom Properties panel instead of the native gap control — invisible to anyone editing in the Designer. Same trap as shorthands: `flex`, `transition`, `padding` shorthands are rejected or mis-filed; write longhands only.
- `box-shadow` cannot be written via `update_style` (stores, never renders) — Designer-only.
- `create_color_variable` fails in every collection — new variables are a Designer job; reads, renames, updates and `variable_as_value` links work. `variable_as_value` needs the `variable-` prefix and must not be batched with plain-value properties in one call; `set_style_variable_mode` needs the `collection-` prefix and takes `parent_style_names` INSIDE the action object.
- `rgba()` variable values error — use 8-digit hex.
- Component variants cannot be created via API. Component `link` props accept only url/email/phone (no `page` mode — pass the path).
- `move_element` cannot anchor before/after a ComponentInstance — reordering around instances is a Designer drag.
- The element builder's `set_text` does NOT apply to `TextBlock` — set its child `String` node, and always read text back after a build.
- Build wrappers as `DivBlock`, never `DOM` (DOM rejects image/link binding on children).
- Collection lists: type `CMSCollection`; bind with `set_settings` key `source` + `{"collectionId": …}` on the WRAPPER; images bind via `assetId`.
- Delete is `remove_element`. Interactions, Lightbox media, Background Video and YouTube URLs cannot be authored via API. Pseudo overrides (`first-child`) can; `box-decoration-break` cannot.
- If the Custom Code API returns 406/404, hand the approved snippet to the user for a manual paste and mirror it to a project file — never leave it unrecorded.
- **Component props via MCP**: rich-text props take plain text only (`\n\n` = new paragraph; headings, bold, links, lists and markdown don't survive). Image props have no write type — placeholders stay until the Designer. `visibility` props ARE writable (as boolean). `headingTag` and conditional-visibility props: don't write.
- `insert_in_slot` resolves slots by **name, first match** — duplicate slot names make slots 2+ unreachable headlessly (tested every workaround; none work).
- A page at Webflow's **20 Collection List cap** (Navigation/Footer included) rejects every component insert, even ones with no CMS.
- There is no page delete via MCP — disposable test pages are deleted in the Designer. Build on `draft:true` duplicates of the Starter, never publish.
- `get_all_elements{depth:2}` can stop above sections nested in a wrapper — use depth 3 for page reads and verification. `insert_in_element` without `return_component_info` still returns element ids at ~1/40th the payload.

## 20 · Units — which unit, when
The unit decides **what a value scales with**. Pick by that, not habit.

| Unit | Scales with | Use for | Never for |
|---|---|---|---|
| `rem` | the user's browser font-size setting | **Default for everything**: font-size, spacing, padding, gaps, max-widths, icon sizes, radius | — |
| `em` | the element's own font-size | letter-spacing, heading line-height, padding/gap *inside* a component that should grow with its text (button, pill, tag) | layout spacing between blocks — compounds when nested |
| `%` | the parent's width | `padding-global` (5%), `width: 100%`, image/embed fill, absolute positioning offsets | font-size, vertical spacing |
| `fr` | remaining grid space | grid column tracks | anything outside a grid |
| `px` | nothing | **1px borders and hairlines only**; box-shadow offsets | type, spacing, widths |
| `vw` | viewport width | **display type only** (tier 3 below), with a rem ceiling; full-bleed widths (`100vw` sparingly — causes horizontal scroll with scrollbars) | body, UI or small text; normal headings |
| `svh` / `dvh` | viewport height (mobile-safe) | full-height heroes, always as `min-height` | `height` on anything holding text; never `vh` (mobile URL bar crops it) |
| unitless | — | `z-index`, `opacity`, `flex-grow`, `aspect-ratio` | line-height (§4a — rem/em variable), any length |

**Font size: three tiers.** Pick the tier by what the text is, not by what is easiest.

1. **Body, UI and small text** (`text-size-*`, captions, pills, tags, labels, buttons, form text): **fixed rem**, with tablet/mobile overrides where needed. **Never vw.** Small text sized by the screen shrinks below readable size on smaller screens and ignores the visitor's browser text-size setting (WCAG 1.4.4 Resize Text). This is where the accessibility failure is real.
2. **Normal headings** (`h1`–`h6` / `heading-style-*`): **fixed rem, stepped per breakpoint.** This is the Client-First default: desktop value, then tablet and mobile overrides (§5 scale). Anyone can click a breakpoint in the Designer and read a plain number.
3. **Display type** (deliberately screen-scaled editorial headlines: huge, often uppercase, meant to span the same share of the layout at every width): **vw is allowed**, under these conditions:
   - **Placement.** It goes on a heading style or ONE named display style (`heading-style-display`), never on scattered custom classes (`cg-h1`, `inq-h3`). Those create parallel type scales.
   - **Ceiling.** It must have a ceiling: a rem override at the large breakpoints (1280/1440/1920), so it stops growing on big monitors.
   - **Floor.** It must have a floor: a rem or vw override at mobile so it stays legible.
   - **Documented.** It's noted on the Style Guide page as an intentional exception.

**`clamp()`** (`clamp(MIN, rem + vw, MAX)`): one value that slides smoothly between a floor and a ceiling. It's optional, and only for tier 3, when stepped overrides can't hold the design between breakpoints (e.g. a word that must fill the viewport edge to edge at every width). If used:
- All three parts are required, and the rem in the middle term keeps text-zoom working.
- It replaces that style's breakpoint overrides; a value is never both clamped and stepped.
- Formula (px values, viewport 480→1440): `slope = (maxPx − minPx) / 960` → vw term = slope × 100; `intercept = minPx − slope × 480` → ÷16 for the rem term. Example: 40→80px = `clamp(2.5rem, 1.25rem + 4.17vw, 5rem)`.

**Always:**
- Font sizes live in Styles variables linked to the tag or class wherever the value is a fixed rem (directive 3).
- No one-sided `min()`/`max()` (`min(48px, 3.6vw)`). Use a stepped override or `clamp()`.
- No fluid root font-size tricks (`html { font-size: … }` in the embed) unless the whole system was designed for it and the user approved it.

**Audit:** `query_styles` → property `font-size` value `vw`.
- Any match on body, UI or small text is a defect.
- Any match on a heading or display style without a ceiling, or outside the heading/display styles, is a defect.

## 21 · Section components and client editing
Build for the client managing the site **after you're gone**: they compose pages from approved sections and edit content through props. They never touch classes. The same contract lets an agent build pages from a doc safely, because it fills props and never creates elements or styles. The internals stay pure Client-First.

**Every section is a Component.**
- **Naming.** Name it `Section — [Name]` with an em dash (`Section — Home Hero`, `Section — FAQ`). Repeating items are `Item — [Name]` (`Item — Service Card`). The component name is what clients and agents see. Inside, the class is still `section_[name]` with the full shell (§1) and the done checklist (§18).
- **Duplicates.** Two sections that differ only in copy, Colour Mode, column count or image side are ONE component with variants (§15). This replaces "build it, then componentize if it repeats".
- **Description.** Give every component a description line saying what it's **for**, and what it's not for. Example: "Three parallel benefits, heading + short text each. Not for steps or testimonials."

**Props: everything a client should change, nothing they shouldn't.**
1. **Text, rich text, image, link.** Every one of these elements gets a prop. Group props in Webflow's prop groups by element (`Heading`, `Body`, `Button 1`, `Card 2`).
2. **Buttons.** Every button has three props: label, link and a visibility toggle. Every optional element (eyebrow, subheading, second button, image caption) has a visibility toggle.
3. **Variants for treatments.** Colour Mode, Surface Treatment and layout choices are **variants with descriptive option names** (`Dark`, `Light`, `Image left`, `3 columns`, `6 columns`).
   - Never use a boolean to switch counts or layouts. Neither the client nor an agent can tell what `true` shows.
   - Variants switch the class combo or variable mode internally, natively, with no data-attribute CSS.
4. **Slot names.** Every slot in a component has a **unique name** (§19).
5. **Structure belongs in fields, not rich text.** Lists of steps, specs or features become `Item — …` instances or numbered prop groups, not bullet lists in one rich-text prop. Clients can't break the layout this way, and MCP can write it.
6. **Defaults.**
   - Default text describes the field ("Section heading: state the outcome in one line") so a leftover is obvious on review.
   - Never ship a fake quote, customer name, statistic or `#` link as a default.
   - Default link: empty.
   - Default image: a neutral placeholder.
7. **What stays out of props.** Classes, spacing, font sizes and colours are never props. Those are the system, and they stay locked.

**Every site ships these pages:**
- **Starter** (draft): navigation, an empty hero, footer and the `main-wrapper` drop zone. New pages are duplicates of it.
- **Component catalogue** at `/stylesheet/components` (can stay draft/unpublished): every `Section —` / `Item —` component, shown in every variant. It's the client's visual menu and the agent's evidence of what each option looks like. The Style Guide page (classes, variables) sits next to it under the same folder.
- **CMS budget**: max 20 Collection Lists per page, Navigation and Footer included. Note each CMS-driven component's list count in its description.

**Handoff.**
- **Build Mode.** Expose section components and their content props. Keep the Designer for you.
- **Registry.** Initialize the page-builder registry on the site (Agent Instructions), so the component inventory, purposes and known limits travel with the site, not with you.
- **Client guide.** One page or doc covering: how to duplicate the Starter, add a section, edit props, and what to replace before publishing.

**Building a page from content** (agent or person):
1. Choose each section by **purpose** first, then fit.
2. Never leave visible default text or a default/`#` link.
3. A button whose destination is unknown stays visible and **unlinked**, and is reported.
4. Never silently drop a source section. It's built, adapted (reported) or resolved with the user.
5. Draft only, never publish.

## 22 · Where this reference lives, and how brands inherit it
**This file is the single source of truth.** `CLAUDE.md` is the short rule list; `SKILL.md` tells Claude when to load both. The HTML files in `views/` (Style Guide, Build Standards) are visual renderings. If a view and this README disagree, the README wins, and the view gets fixed.

**Repo layout**
- `README.md`: full spec (this file)
- `CLAUDE.md`: prime directives, the section done checklist and process rules
- `SKILL.md`: skill entry point (Claude.ai skills and Claude Code)
- `views/`: standalone HTML renderings, open in any browser
- `reference/`: third-party material kept for comparison only (SML page/section builder). Never a source of rules.

**Wiring a brand to this reference (once per brand).** Paste this into the brand's design-system project or repo:

> Add a "Webflow · Client-First" section to this design system's guide. All Webflow builds follow the Webflow Client-First Reference at https://github.com/one4four/webflow-client-first. The full spec is in README.md and CLAUDE.md there; link the repo in the section. Record: (1) page structure is page-wrapper → main-wrapper → section_[name] → padding-global → container-* → padding-section-*; (2) never create a new class when a Client-First utility or documented pattern exists; (3) colours, fonts and radii link variables, never raw values: map this brand's tokens into Primitives → Color Schemes 1–5, Typography and UI Styles; (4) custom classes are [component]_[element], lowercase, is-* combos for variants; (5) mockups only need to be visually correct; exact Client-First naming applies when converting to Webflow. For every other rule, read the repo. Don't copy it here.

**Updating.** Rules change in this repo only. Brands link it rather than copying rules, so there's nothing to push to each brand after an edit.
