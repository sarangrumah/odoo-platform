# -*- coding: utf-8 -*-
from . import models
from . import wizard


def post_init_hook(env):
    """Seed the Operating-Unit analytic + per-store journals + account mapping.

    Idempotent; runs only on fresh install. Already-installed Levi's DBs are
    provisioned by ``scripts/tenants/levis/40_setup_trade_ou.py``.
    """
    from .models.setup import seed_bank_journals, seed_clearing_config, seed_trade_ou

    seed_trade_ou(env)
    seed_bank_journals(env)
    seed_clearing_config(env)
