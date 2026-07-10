# Seed demo_levis with POS retail sales (run via: odoo shell -d demo_levis).
# Opens a session on 3 stores, rings up cash orders, then closes & posts the sessions.
from datetime import datetime

env = env
log = lambda m: print("[pos] " + m)

if env["pos.session"].search_count([]):
    log("pos sessions already present - aborting to avoid double seed")
else:
    company = env["res.company"].browse(1)
    currency = company.currency_id
    PRODUCT_IDS = [195132, 195136, 195141, 195145, 195155, 195165]
    products = env["product.product"].browse(PRODUCT_IDS).exists()
    when = datetime(2026, 6, 12, 10, 30, 0)

    # config_id -> cash payment_method_id (from probe)
    CONFIGS = {2: 2, 3: 12, 4: 13}

    for cid, cash_pm in CONFIGS.items():
        cfg = env["pos.config"].browse(cid)
        session = env["pos.session"].create({"config_id": cid, "user_id": env.uid})
        if session.state != "opened":
            session.set_opening_control(0, None)
        log("POS %s session %s state=%s" % (cid, session.id, session.state))

        total_cash = 0.0
        for k, p in enumerate(products[:3]):
            qty = k + 1
            taxes = p.taxes_id
            res = taxes.compute_all(p.lst_price, currency, qty, product=p, partner=False)
            incl = res["total_included"]
            excl = res["total_excluded"]
            order = env["pos.order"].create(
                {
                    "session_id": session.id,
                    "company_id": company.id,
                    "pricelist_id": cfg.pricelist_id.id,
                    "date_order": when,
                    "amount_tax": incl - excl,
                    "amount_total": incl,
                    "amount_paid": incl,
                    "amount_return": 0.0,
                    "lines": [
                        (
                            0,
                            0,
                            {
                                "product_id": p.id,
                                "qty": qty,
                                "price_unit": p.lst_price,
                                "price_subtotal": excl,
                                "price_subtotal_incl": incl,
                                "tax_ids": [(6, 0, taxes.ids)],
                                "full_product_name": p.display_name,
                            },
                        )
                    ],
                }
            )
            env["pos.payment"].create(
                {
                    "pos_order_id": order.id,
                    "amount": incl,
                    "payment_method_id": cash_pm,
                    "payment_date": when,
                }
            )
            order.action_pos_order_paid()
            total_cash += incl
        log("POS %s orders=%d cash=%.0f" % (cid, len(session.order_ids), total_cash))

        # close & post
        session.action_pos_session_closing_control()
        try:
            session.post_closing_cash_details(total_cash)
        except Exception as e:
            log("post_closing_cash_details warn: %s" % e)
        try:
            session.close_session_from_ui()
        except TypeError:
            session.close_session_from_ui([])
        log("POS %s closed -> state=%s" % (cid, session.state))
        env.cr.commit()

    log("==== POS SUMMARY ====")
    log("pos.session : %d" % env["pos.session"].search_count([]))
    log("pos.order   : %d" % env["pos.order"].search_count([]))
    log("closed sess : %d" % env["pos.session"].search_count([("state", "=", "closed")]))
    log("pos moves   : %d" % env["account.move"].search_count([("journal_id.code", "in", ["CSHPS", "POSS"])]))
    log("==== DONE ====")
