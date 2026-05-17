"""Slug validation behaviour."""

from __future__ import annotations

import pytest

from app.validators import assert_valid_slug, is_valid_slug


@pytest.mark.parametrize("slug", ["acme", "acme_corp", "tenant1", "a1", "a_b_c"])
def test_valid_slugs(slug):
    assert is_valid_slug(slug)


@pytest.mark.parametrize(
    "slug",
    [
        "",            # empty
        "a",           # too short
        "1acme",       # cannot start with digit
        "Acme",        # no uppercase
        "acme-corp",   # no dash
        "acme.corp",   # no dot
        "a" * 64,      # too long
        "drop table",  # spaces
    ],
)
def test_invalid_slugs(slug):
    assert not is_valid_slug(slug)
    with pytest.raises(ValueError):
        assert_valid_slug(slug)
