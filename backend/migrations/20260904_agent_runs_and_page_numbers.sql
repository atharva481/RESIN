-- Migration: Add page numbers, document_id, agent_runs, and tool_calls tables

-- 1. Alter paper_chunks to support page_number and document_id
ALTER TABLE public.paper_chunks ADD COLUMN IF NOT EXISTS page_number int;
ALTER TABLE public.paper_chunks ADD COLUMN IF NOT EXISTS document_id text;

-- 2. Create agent_runs table
CREATE TABLE IF NOT EXISTS public.agent_runs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    status text NOT NULL DEFAULT 'RUNNING',
    started_at timestamptz DEFAULT now(),
    completed_at timestamptz
);

CREATE INDEX IF NOT EXISTS ix_agent_runs_user_id ON public.agent_runs (user_id, started_at);

-- 3. Create tool_calls table
CREATE TABLE IF NOT EXISTS public.tool_calls (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_run_id uuid NOT NULL REFERENCES public.agent_runs(id) ON DELETE CASCADE,
    tool_name text NOT NULL,
    arguments jsonb DEFAULT '{}'::jsonb,
    result jsonb DEFAULT '{}'::jsonb,
    status text NOT NULL DEFAULT 'SUCCESS',
    created_at timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_tool_calls_agent_run_id ON public.tool_calls (agent_run_id, created_at);

-- 4. Enable Row-Level Security (RLS)
ALTER TABLE public.agent_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.tool_calls ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Users can view their agent runs') THEN
        CREATE POLICY "Users can view their agent runs" ON public.agent_runs FOR ALL TO authenticated
        USING (user_id = auth.uid());
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Users can view tool calls for their agent runs') THEN
        CREATE POLICY "Users can view tool calls for their agent runs" ON public.tool_calls FOR ALL TO authenticated
        USING (EXISTS (SELECT 1 FROM public.agent_runs ar WHERE ar.id = tool_calls.agent_run_id AND ar.user_id = auth.uid()));
    END IF;
END$$;

-- 5. Updated match_paper_chunks function to return page_number and document_id
CREATE OR REPLACE FUNCTION public.match_paper_chunks(
  query_embedding vector(768),
  match_threshold float,
  match_count int,
  filter_paper_id uuid DEFAULT NULL
)
RETURNS TABLE (
  id uuid,
  paper_id uuid,
  chunk_index int,
  section_title text,
  content text,
  similarity float,
  page_number int,
  document_id text
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT
    pc.id,
    pc.paper_id,
    pc.chunk_index,
    pc.section_title,
    pc.content,
    1 - (pc.embedding <=> query_embedding) AS similarity,
    pc.page_number,
    pc.document_id
  FROM public.paper_chunks pc
  WHERE
    (filter_paper_id IS NULL OR pc.paper_id = filter_paper_id)
    AND 1 - (pc.embedding <=> query_embedding) > match_threshold
  ORDER BY pc.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;
