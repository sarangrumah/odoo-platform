# -*- coding: utf-8 -*-
"""Per-user storage for the bits of backend layout the web client forgets.

Odoo recomputes list column widths on every mount and derives the chatter
position from the window width alone, so anything the user adjusts by hand is
gone on the next page load -- and was never tied to the user in the first
place.  This model parks those preferences on ``res.users.settings``, i.e. on
the user record, so they follow the user to any browser or device.

The blob is deliberately opaque to the server: it is written by the web client,
read back by the web client, and never interpreted by Python beyond the
sanitising done here.  What the server *does* guarantee is that it stays small
and well-formed, because a preference store that can grow without bound turns
every page load into a slow one.
"""

import json
import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

#: Sections the client is allowed to write, mapped to their value sanitiser.
#: Anything else is dropped silently -- an old client writing a section a newer
#: server no longer knows must not raise in the middle of a page load.
SECTION_COLUMN_WIDTHS = "columnWidths"
SECTION_CHATTER_COLLAPSED = "chatterCollapsed"

#: A single list view never has this many columns; the cap is there to stop a
#: buggy or hostile client from stuffing the blob through one key.
MAX_COLUMNS_PER_VIEW = 200
#: Widths outside this range cannot come from a real drag on a real screen.
MIN_COLUMN_WIDTH = 10
MAX_COLUMN_WIDTH = 3000
#: How many views / models we remember before forgetting the least recently
#: touched ones.  Users cycle through far fewer views than this in practice.
MAX_ENTRIES_PER_SECTION = 300
#: Hard ceiling on the serialised blob, enforced after pruning by count.
MAX_PREFS_BYTES = 128 * 1024


class ResUsersSettings(models.Model):
    _inherit = "res.users.settings"

    layout_prefs = fields.Text(
        string="Backend Layout Preferences",
        default="{}",
        help="JSON blob of per-user backend layout preferences (list column "
        "widths, collapsed chatters). Written and read by the web client.",
    )

    @api.model
    def _get_fields_blacklist(self):
        # Keep the blob out of `_res_users_settings_format`. That payload is
        # embedded in the mail store at boot and re-broadcast over the bus on
        # every settings change; shipping a 100 kB preference blob through it
        # would make every unrelated setting toggle expensive.
        return super()._get_fields_blacklist() + ["layout_prefs"]

    # ------------------------------------------------------------------
    # Client API
    # ------------------------------------------------------------------

    @api.model
    def get_layout_prefs(self):
        """Return the calling user's layout preferences.

        Never creates a settings record: reading a preference must stay a
        read, so that merely opening a list view does not write to the
        database. Returns the empty shape when there is nothing stored yet.
        """
        settings = self._layout_prefs_record(create=False)
        if not settings:
            return self._layout_prefs_empty()
        return self._layout_prefs_load(settings)

    @api.model
    def set_layout_prefs(self, changes):
        """Merge ``changes`` into the calling user's preferences.

        ``changes`` is ``{section: {key: value}}``. A ``None`` value deletes
        the key, which is how the client forgets a view whose widths were
        reset. Only the sections listed above are honoured, and each surviving
        key is moved to the end of its section so that pruning drops the least
        recently touched entries first.
        """
        if not isinstance(changes, dict):
            return False
        settings = self._layout_prefs_record(create=True)
        if not settings:
            return False
        prefs = self._layout_prefs_load(settings)
        touched = False
        for section, entries in changes.items():
            if section not in (SECTION_COLUMN_WIDTHS, SECTION_CHATTER_COLLAPSED):
                continue
            if not isinstance(entries, dict):
                continue
            bucket = prefs.setdefault(section, {})
            for key, value in entries.items():
                if not isinstance(key, str) or not key:
                    continue
                # Pop first, so that a re-written key counts as recently used.
                bucket.pop(key, None)
                touched = True
                if value is None:
                    continue
                clean = self._layout_prefs_sanitise(section, value)
                if clean is not None:
                    bucket[key] = clean
        if not touched:
            return False
        prefs = self._layout_prefs_prune(prefs)
        settings.write({"layout_prefs": json.dumps(prefs)})
        return True

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @api.model
    def _layout_prefs_empty(self):
        return {SECTION_COLUMN_WIDTHS: {}, SECTION_CHATTER_COLLAPSED: {}}

    @api.model
    def _layout_prefs_record(self, create=False):
        """The current user's settings record, in sudo.

        Sudo is safe here and only here: the record is looked up by
        ``self.env.user`` and never by an id coming from the client, so a user
        can only ever reach their own row. Public users get nothing -- they
        have no stable identity to hang a preference on.
        """
        user = self.env.user
        if not user or user._is_public():
            return self.env["res.users.settings"]
        if create:
            return self._find_or_create_for_user(user)
        return user.sudo().res_users_settings_ids[:1]

    @api.model
    def _layout_prefs_load(self, settings):
        raw = settings.layout_prefs or "{}"
        try:
            prefs = json.loads(raw)
        except (TypeError, ValueError):
            _logger.warning("Discarding unparseable layout_prefs for user %s", settings.user_id.id)
            return self._layout_prefs_empty()
        if not isinstance(prefs, dict):
            return self._layout_prefs_empty()
        clean = self._layout_prefs_empty()
        for section in clean:
            bucket = prefs.get(section)
            if isinstance(bucket, dict):
                clean[section] = bucket
        return clean

    @api.model
    def _layout_prefs_sanitise(self, section, value):
        """Coerce a client-supplied value, or return None to drop it."""
        if section == SECTION_CHATTER_COLLAPSED:
            return bool(value)
        if section == SECTION_COLUMN_WIDTHS:
            if not isinstance(value, dict):
                return None
            widths = {}
            for name, width in value.items():
                if len(widths) >= MAX_COLUMNS_PER_VIEW:
                    break
                if not isinstance(name, str) or not name:
                    continue
                if isinstance(width, bool) or not isinstance(width, (int, float)):
                    continue
                rounded = int(round(width))
                if rounded < MIN_COLUMN_WIDTH or rounded > MAX_COLUMN_WIDTH:
                    continue
                widths[name] = rounded
            return widths or None
        return None

    @api.model
    def _layout_prefs_prune(self, prefs):
        """Drop least-recently-touched entries until the blob is small.

        Dicts preserve insertion order and `set_layout_prefs` re-inserts every
        key it touches, so the head of each section is the coldest entry.
        """
        for section, bucket in prefs.items():
            while len(bucket) > MAX_ENTRIES_PER_SECTION:
                bucket.pop(next(iter(bucket)))
        while len(json.dumps(prefs).encode()) > MAX_PREFS_BYTES:
            # Always bite off the biggest section, otherwise a single fat
            # section could survive while we empty the small one.
            section = max(prefs, key=lambda name: len(prefs[name]))
            if not prefs[section]:
                break
            prefs[section].pop(next(iter(prefs[section])))
        return prefs
