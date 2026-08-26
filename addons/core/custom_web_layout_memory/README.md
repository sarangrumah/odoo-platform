# Backend Layout Memory

Remembers, against the **user** (not the browser), two things the Odoo backend
otherwise forgets on every page load.

## List column widths

Drag a column border in any list view — including the line lists inside a form,
such as Journal Items — and the widths come back the next time that view is
opened, on any device the user logs in from.

Double-click a resize handle to go back to Odoo's automatic widths; that also
clears what was stored.

If the saved layout is wider than the window (a smaller laptop, say), the table
keeps the widths and scrolls horizontally rather than silently re-flowing.

## Collapsible chatter

The message / log / follower sidebar gets a chevron in its top bar. Clicking it
folds the chatter into a narrow rail and gives the form sheet the space back;
clicking again brings it back. The choice is remembered **per model**, so
hiding it on journal entries does not hide it on contacts.

## Where it is stored

One JSON blob on `res.users.settings`, fetched once per session and written
back debounced. Nothing is kept in `localStorage`, which is why it follows the
user across browsers and machines.

## Install

```
-i custom_web_layout_memory     # first time
-u custom_web_layout_memory     # after any version bump
```

No configuration, no menu, no access rights to grant: `res.users.settings`
already lets every internal user read and write their own row.
