# -*- coding: utf-8 -*-
from . import models


def post_init_hook(env):
    """Seed the Operating-Unit analytic + per-store journals + account mapping.

    Idempotent; runs only on fresh install. Already-installed Levi's DBs are
    provisioned by ``scripts/tenants/levis/40_setup_trade_ou.py``.
    """
    from .models.setup import seed_trade_ou

    seed_trade_ou(env)
