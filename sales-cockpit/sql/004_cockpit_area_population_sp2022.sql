-- =============================================================================
-- Market figures, part 1: population by age, from BPS.
--
--   psql -U odoo -d prd_levis_begbal -f 004_cockpit_area_population_sp2022.sql
--
-- Source: BPS Long Form Sensus Penduduk 2020 (published as SP2022), table
-- "Jumlah Penduduk menurut Kelompok Umur dan Jenis Kelamin", read per
-- kabupaten/kota from sensus.bps.go.id on 20-Aug-2026. population_15_44 is the
-- sum of the six five-year bands 15-19 … 40-44; `population` is the table's own
-- total, kept so the two can be sanity-checked against each other (the 15-44
-- share lands at 46,5–51,0% everywhere, as it should).
--
-- Why this source and not the provincial BPS sites: every other bps.go.id host
-- (www, jakarta, bandungkota, …) answers 403 to anything that is not a browser.
-- sensus.bps.go.id serves the same census tables and does not.
--
-- expenditure_apparel_capita is still NULL — Susenas apparel spend is published
-- on the hosts that block us. Until it is filled, the fair-share rule weighs
-- markets by POPULATION ALONE and says so on the card.
-- =============================================================================

UPDATE cockpit_area SET data_year=2022, population=1079995, population_15_44=508892, source='BPS Long Form SP2020 (SP2022), Jumlah Penduduk menurut Kelompok Umur dan Jenis Kelamin, sensus.bps.go.id', updated_at=now() WHERE code='3171';
UPDATE cockpit_area SET data_year=2022, population=1793550, population_15_44=875582, source='BPS Long Form SP2020 (SP2022), Jumlah Penduduk menurut Kelompok Umur dan Jenis Kelamin, sensus.bps.go.id', updated_at=now() WHERE code='3172';
UPDATE cockpit_area SET data_year=2022, population=2448975, population_15_44=1191310, source='BPS Long Form SP2020 (SP2022), Jumlah Penduduk menurut Kelompok Umur dan Jenis Kelamin, sensus.bps.go.id', updated_at=now() WHERE code='3173';
UPDATE cockpit_area SET data_year=2022, population=2244623, population_15_44=1069538, source='BPS Long Form SP2020 (SP2022), Jumlah Penduduk menurut Kelompok Umur dan Jenis Kelamin, sensus.bps.go.id', updated_at=now() WHERE code='3174';
UPDATE cockpit_area SET data_year=2022, population=2590257, population_15_44=1282556, source='BPS Long Form SP2020 (SP2022), Jumlah Penduduk menurut Kelompok Umur dan Jenis Kelamin, sensus.bps.go.id', updated_at=now() WHERE code='3275';
UPDATE cockpit_area SET data_year=2022, population=2461553, population_15_44=1162006, source='BPS Long Form SP2020 (SP2022), Jumlah Penduduk menurut Kelompok Umur dan Jenis Kelamin, sensus.bps.go.id', updated_at=now() WHERE code='3273';
UPDATE cockpit_area SET data_year=2022, population=2887223, population_15_44=1342144, source='BPS Long Form SP2020 (SP2022), Jumlah Penduduk menurut Kelompok Umur dan Jenis Kelamin, sensus.bps.go.id', updated_at=now() WHERE code='3578';
UPDATE cockpit_area SET data_year=2022, population=3352472, population_15_44=1710953, source='BPS Long Form SP2020 (SP2022), Jumlah Penduduk menurut Kelompok Umur dan Jenis Kelamin, sensus.bps.go.id', updated_at=now() WHERE code='3603';
