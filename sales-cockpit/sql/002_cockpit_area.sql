-- =============================================================================
-- Market context for the recommendation engine.
--
--   psql -U odoo -d prd_levis_begbal -f 002_cockpit_area.sql
--
-- Two reference tables that Odoo neither knows about nor touches. They exist
-- because prd_levis_begbal has NO address data at all: operating_unit.partner_id
-- is null on every row, so there is no way to derive a store's city from the
-- database. The mapping below was written by hand from the mall names.
--
-- The tables are created EMPTY of market figures on purpose. Every rule that
-- depends on them stays silent until the numbers are filled in, so an unfilled
-- table costs nothing and a half-filled one cannot produce a half-true finding.
--
-- Idempotent: re-running never overwrites figures already entered.
-- =============================================================================

CREATE TABLE IF NOT EXISTS cockpit_area (
    code                        text PRIMARY KEY,   -- BPS kabupaten/kota code, e.g. '3174'
    name                        text NOT NULL,
    agglomeration               text NOT NULL,      -- the market a mall really draws from
    data_year                   integer,
    population                  bigint,
    population_15_44            bigint,             -- the age band that buys denim
    expenditure_apparel_capita  numeric(14, 2),     -- Susenas, rupiah per capita per YEAR
    gdrp_capita                 numeric(16, 2),     -- PDRB per kapita, rupiah per year
    source                      text,               -- exact table + release, for audit
    updated_at                  timestamptz DEFAULT now()
);

COMMENT ON TABLE cockpit_area IS
  'Market context per kabupaten/kota. Figures are entered by hand from BPS; the
   cockpit never writes here. expenditure_apparel_capita is preferred over
   gdrp_capita: PDRB per kapita in DKI is inflated by corporate head offices and
   says little about what a resident spends on clothing.';

CREATE TABLE IF NOT EXISTS cockpit_store_area (
    pos_config_id     integer PRIMARY KEY,
    area_code         text NOT NULL REFERENCES cockpit_area(code),
    -- A mall's catchment is not its city. Weight < 1 means part of the market
    -- is shared with neighbouring stores; weight > 1 means the mall draws from
    -- beyond its own city. Left at 1.00 until someone with local knowledge
    -- tunes it.
    catchment_weight  numeric(5, 2) NOT NULL DEFAULT 1.00,
    confidence        text NOT NULL DEFAULT 'tinggi'
                      CHECK (confidence IN ('tinggi', 'perlu verifikasi')),
    note              text
);

COMMENT ON TABLE cockpit_store_area IS
  'pos_config -> kabupaten/kota. Hand-written from mall names because the
   database holds no store addresses. Rows marked "perlu verifikasi" sit on an
   administrative boundary and should be confirmed before the numbers are used.';

-- --- Areas -------------------------------------------------------------------
-- Agglomeration matters more than the city here: Grand Indonesia draws from all
-- of Jabodetabek, so comparing it against Jakarta Pusat residents alone would
-- understate its market by an order of magnitude. Rules aggregate to the
-- agglomeration; the city code is kept because BPS publishes at that level.

INSERT INTO cockpit_area (code, name, agglomeration) VALUES
    ('3171', 'Kota Jakarta Pusat',      'JABODETABEK'),
    ('3172', 'Kota Jakarta Utara',      'JABODETABEK'),
    ('3173', 'Kota Jakarta Barat',      'JABODETABEK'),
    ('3174', 'Kota Jakarta Selatan',    'JABODETABEK'),
    ('3275', 'Kota Bekasi',             'JABODETABEK'),
    ('3276', 'Kota Depok',              'JABODETABEK'),
    ('3673', 'Kota Tangerang Selatan',  'JABODETABEK'),
    ('3273', 'Kota Bandung',            'BANDUNG RAYA'),
    ('3578', 'Kota Surabaya',           'SURABAYA RAYA')
ON CONFLICT (code) DO NOTHING;

-- --- Stores ------------------------------------------------------------------

INSERT INTO cockpit_store_area (pos_config_id, area_code, confidence, note) VALUES
    ( 2, '3578', 'tinggi',           'Tunjungan Plaza 3'),
    ( 3, '3174', 'tinggi',           'Pondok Indah Mall 1'),
    ( 4, '3174', 'tinggi',           'Pondok Indah Mall 2'),
    ( 5, '3172', 'tinggi',           'Kelapa Gading Mall'),
    ( 6, '3171', 'tinggi',           'Senayan City — Tanah Abang'),
    ( 7, '3171', 'tinggi',           'Grand Indonesia — Thamrin'),
    ( 8, '3273', 'tinggi',           'Trans Studio Mall Bandung'),
    ( 9, '3173', 'tinggi',           'Central Park — Tanjung Duren'),
    (10, '3174', 'tinggi',           'Lotte Shopping Avenue — Kuningan'),
    (11, '3275', 'tinggi',           'Grand Metropolitan Bekasi'),
    (12, '3673', 'tinggi',           'AEON BSD City'),
    (13, '3273', 'tinggi',           'Paris Van Java'),
    (14, '3578', 'tinggi',           'Pakuwon Mall Surabaya'),
    (15, '3174', 'tinggi',           'Pacific Place — SCBD'),
    (16, '3276', 'perlu verifikasi', 'Trans Studio Cibubur — Cibubur duduk di batas Depok/Bekasi/Jaktim'),
    (17, '3578', 'tinggi',           'Galaxy Mall 3'),
    (18, '3275', 'tinggi',           'Metropolitan Mall Bekasi'),
    (19, '3172', 'tinggi',           'Mall of Indonesia — Kelapa Gading'),
    (20, '3171', 'tinggi',           'Plaza Senayan — Tanah Abang'),
    (21, '3273', 'tinggi',           '23 Paskal Bandung'),
    (22, '3174', 'tinggi',           'Gandaria City'),
    (23, '3273', 'tinggi',           'Summarecon Mall Bandung — Gedebage'),
    (24, '3273', 'tinggi',           'Bandung Indah Plaza')
ON CONFLICT (pos_config_id) DO NOTHING;

-- --- Grants ------------------------------------------------------------------

GRANT SELECT ON cockpit_area, cockpit_store_area TO cockpit_ro;

-- --- How to fill it ----------------------------------------------------------
-- One UPDATE per area, e.g.:
--
--   UPDATE cockpit_area SET
--       data_year = 2025,
--       population = 2_200_000,
--       population_15_44 = 1_050_000,
--       expenditure_apparel_capita = 1_450_000,
--       source = 'BPS Susenas 2025, Tabel 4.2 + Proyeksi Penduduk 2025',
--       updated_at = now()
--   WHERE code = '3174';
--
-- Fill population_15_44 AND expenditure_apparel_capita for every area, or the
-- fair-share rule stays off — a market index computed from half the network
-- ranks stores against a benchmark that does not include them.
