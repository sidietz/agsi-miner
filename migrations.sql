-- ====================================================================
-- Database Migration: Fix Operator Country Assignments & Naming
-- ====================================================================
-- Resolves cross-border operator assignment issues where German-headquartered
-- operators were incorrectly tagged with Austria (AT) due to first-encounter
-- traversal order during scraping.
-- ====================================================================

BEGIN;

-- 1. SEFE Storage (Securing Energy for Europe GmbH, Berlin, Germany)
UPDATE operators
SET country_code = 'DE'
WHERE code = '37X0000000002964';

-- 2. Uniper Energy Storage GmbH (Düsseldorf, Germany)
-- Update country_code to DE and normalize operator name by removing '(AT)'
UPDATE operators
SET country_code = 'DE',
    name = 'Uniper Energy Storage'
WHERE code = '21X000000001127H';

COMMIT;
