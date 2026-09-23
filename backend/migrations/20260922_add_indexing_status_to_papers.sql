-- Migration: Add indexing_status and indexing_error to public.papers
-- Allows short-circuiting chat requests on unindexed/failed papers and surfacing diagnostic failure reasons.

ALTER TABLE public.papers ADD COLUMN IF NOT EXISTS indexing_status text;
ALTER TABLE public.papers ADD COLUMN IF NOT EXISTS indexing_error text;

COMMENT ON COLUMN public.papers.indexing_status IS 'Indexing status: in_progress, completed, failed, or null (not attempted)';
COMMENT ON COLUMN public.papers.indexing_error IS 'Stored diagnostic failure reason e.g. PAYWALL_DETECTED, BOT_PROTECTION, EMBEDDING_QUOTA_EXCEEDED, etc.';
