---
status: draft
generated_at: 2026-08-27T00:00:00Z
generator: hand-written
module: custom_web_layout_memory
manifest_version: 19.0.1.0.0
---

# custom_web_layout_memory

## Purpose
Persists two pieces of backend layout state that Odoo 19 recomputes from
scratch on every page load, and ties them to the **user record** rather than to
the browser, so they follow the user across devices:

1. **List column widths** — per view, restored on the next visit.
2. **Chatter collapsed state** — per model, folding the message/log sidebar into
   a narrow rail so the form sheet gets the width back.

Both are stored in one JSON blob, `res.users.settings.layout_prefs`.

## Why this is a patch and not configuration
Neither behaviour is configurable in Odoo 19 core:

- `web/static/src/views/list/column_width_hook.js` (`useMagicColumnWidths`)
  computes widths on mount, allows a drag (`onStartResize`), and keeps the
  result in a **closure variable**. It also calls `unsetWidths()` on window
  resize, on a column-set change, and when a previously empty list gains rows.
  Nothing is written anywhere, so a reload starts over.
- `mail/static/src/chatter/web/form_renderer.js` (`mailLayout()`) returns
  `SIDE_CHATTER` when `uiService.size >= SIZES.XXL` and `BOTTOM_CHATTER`
  otherwise. No user input takes part. (Mail's own SCSS reserves
  `--Chatter-asideExtraWidth` "to take into account more items, e.g. 'close'
  chatter feature", so core anticipates the idea but does not ship it.)

## Business Flow
- On first list render or first chatter render of a session, the
  `custom_web_layout_memory.prefs` service issues **one** `get_layout_prefs`
  call and caches the result. Components `await layoutPrefs.ready()` in
  `onWillStart`; every later caller gets the settled promise.
- `ListRenderer.processAllColumn` (patched) injects each saved width into the
  column as `attrs.width`. That is the exact key `getWidthSpecs()` reads for an
  arch-declared `<field width="80px"/>`, so the core layout algorithm treats
  the column as fixed and the rest of its maths (shrink others to their
  minimum, show a horizontal scrollbar when there is not enough room) applies
  unchanged.
- When a drag ends, `saveColumnWidths()` snapshots **every** `thead th[data-name]`
  minus its horizontal padding — the same convention the core hook uses
  internally — and hands the map to the service.
- Double-clicking a resize handle calls core `resetWidths()`; the patch also
  deletes the stored entry for that view, so "reset" survives the reload.
- The chatter toggle flips `layoutMemoryState.collapsed` and stores it under
  the thread's model name.
- Writes are coalesced and flushed 800 ms later, plus immediately on
  `visibilitychange → hidden` so a drag followed by a tab switch is not lost.

## Key Models
- `res.users.settings` (inherited) — gains `layout_prefs` plus the client API.

## Important Fields
- `res.users.settings.layout_prefs` (Text, default `"{}"`) — JSON with exactly
  two sections: `columnWidths` (`{viewKey: {fieldName: px}}`) and
  `chatterCollapsed` (`{model: bool}`). Added to `_get_fields_blacklist()` so it
  is **not** included in `_res_users_settings_format()`; that payload rides in
  the mail store at boot and is re-broadcast over the bus on every settings
  change, and a 100 kB blob has no business in it.

## Public Methods
- `res.users.settings.get_layout_prefs()` (`@api.model`) — returns the calling
  user's blob. Deliberately **never creates** the settings row: reading a
  preference must not turn a page load into a write.
- `res.users.settings.set_layout_prefs(changes)` (`@api.model`) — merges
  `{section: {key: value}}`; a `None` value deletes the key. Unknown sections
  and malformed values are dropped silently, never raised — an old client must
  not be able to break a settings write.
- `_layout_prefs_record(create=False)` — the current user's row, in sudo. Sudo
  is safe only because the lookup goes through `self.env.user` and never
  through a client-supplied id.
- `_layout_prefs_sanitise(section, value)` — coerces widths to ints in
  10…3000 px, chatter flags to bool.
- `_layout_prefs_prune(prefs)` — caps each section at 300 entries and the whole
  blob at 128 kB. Dicts keep insertion order and `set_layout_prefs` pops a key
  before re-inserting it, so the head of a section is the least recently
  touched entry and is the first to go.

## Frontend
- `static/src/layout_prefs_service.js` — the session cache (service name
  `custom_web_layout_memory.prefs`). Every RPC failure is swallowed: layout
  memory is a convenience, and a view must still render without it.
- `static/src/list_column_width.js` — patches `ListRenderer.setup`,
  `processAllColumn`, and wraps the `columnWidths` API object returned by
  `useMagicColumnWidths` (the hook itself is a plain exported function and
  cannot be patched).
- `static/src/chatter_collapse.js` / `.xml` — patches `Chatter` and appends the
  toggle button at the **end** of `.o-mail-Chatter-topbar`. It must not go at
  the front: the first two children there are a `t-if`/`t-else` pair (search
  input vs. buttons) and inserting between them breaks the chain.
- `static/src/layout_memory.scss` — collapses the chatter with `:has()` from
  the toggle button. The collapsed flag lives on the button because the chatter
  root's classes are assembled by mail's templates and the form compiler, so we
  do not own them.

## Gotchas
- **The view key is the field set.** `createViewKey()` includes every field
  name in the arch, so adding a field to a list view produces a new key and the
  user's widths for that view start fresh. This matches how Odoo already keys
  remembered optional columns; it is not a bug to "fix" by loosening the key,
  or widths would be replayed onto a column layout they were never measured
  against. The stored key is `model|viewId|djb2(viewKey)` to keep the blob small.
- **Widths stretch on a wider screen.** Once every column has a saved (i.e.
  fixed) width, core's final fallback in `computeWidths` adds `diff / n` to each
  column to fill 100 % of the table. On a narrower screen the reverse does not
  happen — nothing is shrinkable below its minimum, so a scrollbar appears and
  the layout is preserved exactly. That asymmetry is intended.
- **Image-ish widgets are skipped.** `image`, `image_url`, `signature`,
  `binary`, `many2many_binary` and `pdf_viewer` read `attrs.width` to size their
  own content, so pinning a column width there would resize the picture.
- **An arch width wins.** A column that already declares `width=` in the arch is
  never overridden; the developer's intent outranks a stray drag.
- **The collapsed chatter is still mounted.** It is reduced to a rail by CSS,
  not unmounted — otherwise the toggle would disappear with it and there would
  be no way back. Messages therefore still load in the background.
- **Shared addon.** This installs in every tenant database that gets it, and it
  patches core web/mail components. Follow the platform rule for shared addons:
  bump the manifest version and run `-u custom_web_layout_memory` on every
  database that has it, or the assets bundle and the Python side drift apart.
