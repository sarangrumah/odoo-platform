-- =============================================================================
-- Corrections to the area mapping, and the grants the cockpit needs to read a
-- store's address straight from Odoo.
--
--   psql -U odoo -d prd_levis_begbal -f 003_cockpit_area_from_odoo.sql
--
-- Two mappings in 002 were wrong. They were written from mall names alone; the
-- scraped addresses corrected them:
--
--   * AEON BSD City is in Pagedangan, KABUPATEN Tangerang (15345) — not Kota
--     Tangerang Selatan. BSD City straddles the boundary and the mall sits on
--     the Kabupaten side.
--   * Trans Studio Cibubur is at Jatikarya, Jatisampurna, KOTA BEKASI (17435).
--     It was mapped to Depok and flagged "perlu verifikasi"; several listing
--     sites do place it in Cimanggis, Depok, but the mall's own address and the
--     kelurahan are Bekasi.
--
-- Kota Depok and Kota Tangerang Selatan stay in cockpit_area with no store
-- attached: harmless, since every query starts from cockpit_store_area.
-- =============================================================================

INSERT INTO cockpit_area (code, name, agglomeration) VALUES
    ('3603', 'Kabupaten Tangerang', 'JABODETABEK')
ON CONFLICT (code) DO NOTHING;

UPDATE cockpit_store_area
   SET area_code = '3603', confidence = 'tinggi',
       note = 'AEON Mall BSD City — Jl. BSD Raya Utama, Pagedangan, Kab. Tangerang 15345'
 WHERE pos_config_id = 12;

UPDATE cockpit_store_area
   SET area_code = '3275', confidence = 'tinggi',
       note = 'Trans Studio Cibubur — Jl. Alternatif Cibubur, Jatikarya, Jatisampurna, Kota Bekasi 17435'
 WHERE pos_config_id = 16;

-- --- Grants ------------------------------------------------------------------
-- operating_unit was not in the 001 list, so the cockpit could not walk
-- pos_config -> operating_unit -> res_partner to reach a store address.
-- res_partner was already granted.
-- res_country_state comes with it: without the state name the address table
-- renders a province-less address, and a denied SELECT (42501) is swallowed by
-- the loader, so the whole address block silently disappears instead of erroring.
GRANT SELECT ON public.operating_unit, public.res_country_state, public.res_country TO cockpit_ro;
