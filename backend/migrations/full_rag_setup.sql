-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- 1. Create paper_chunks table
CREATE TABLE IF NOT EXISTS public.paper_chunks (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  paper_id    uuid NOT NULL REFERENCES public.papers(id) ON DELETE CASCADE,
  chunk_index int NOT NULL,
  section_title text,
  content     text NOT NULL,
  embedding   vector(768),  -- Gemini text-embedding-004
  word_count  int,
  created_at  timestamptz DEFAULT now(),
  UNIQUE (paper_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS paper_chunks_embedding_idx
  ON public.paper_chunks USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 100);

CREATE INDEX IF NOT EXISTS paper_chunks_paper_id_idx
  ON public.paper_chunks (paper_id);

-- Optional columns on papers table
ALTER TABLE public.papers ADD COLUMN IF NOT EXISTS indexed_at timestamptz;
ALTER TABLE public.papers ADD COLUMN IF NOT EXISTS full_text text;

-- Stored procedure for chunk vector similarity search
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
  similarity float
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
    1 - (pc.embedding <=> query_embedding) AS similarity
  FROM public.paper_chunks pc
  WHERE
    (filter_paper_id IS NULL OR pc.paper_id = filter_paper_id)
    AND 1 - (pc.embedding <=> query_embedding) > match_threshold
  ORDER BY pc.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;

-- 2. Create paper_embeddings table
CREATE TABLE IF NOT EXISTS public.paper_embeddings (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  paper_id uuid NOT NULL UNIQUE REFERENCES public.papers(id) ON DELETE CASCADE,
  embedding vector(768),
  created_at timestamptz DEFAULT now()
);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'ix_paper_embeddings_embedding') THEN
        CREATE INDEX IF NOT EXISTS ix_paper_embeddings_embedding
          ON public.paper_embeddings USING ivfflat (embedding vector_cosine_ops)
          WITH (lists = 100);
    END IF;
END$$;

-- Function to match paper embeddings with optional user and folder filtering
CREATE OR REPLACE FUNCTION public.match_paper_embeddings(
    query_embedding vector(768),
    match_threshold float DEFAULT 0.3,
    match_count int DEFAULT 5,
    filter_user_id uuid DEFAULT NULL,
    filter_folder_id uuid DEFAULT NULL
)
RETURNS TABLE (
    paper_id uuid,
    similarity float
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        pe.paper_id,
        1 - (pe.embedding <=> query_embedding) AS similarity
    FROM public.paper_embeddings pe
    LEFT JOIN public.user_papers up
           ON up.paper_id = pe.paper_id
    WHERE
        (filter_user_id IS NULL OR up.user_id = filter_user_id)
        AND (filter_folder_id IS NULL OR up.folder_id = filter_folder_id)
        AND 1 - (pe.embedding <=> query_embedding) > match_threshold
    ORDER BY pe.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

-- 3. Create chat_history table
CREATE TABLE IF NOT EXISTS public.chat_history (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  folder_id uuid REFERENCES public.folders(id) ON DELETE SET NULL,
  role text NOT NULL CHECK (role IN ('user','assistant')),
  content text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_chat_history_user_folder
  ON public.chat_history (user_id, folder_id, created_at);

-- Row Level Security (RLS)
ALTER TABLE public.paper_chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.paper_embeddings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.chat_history ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Users can read paper chunks') THEN
    CREATE POLICY "Users can read paper chunks" ON public.paper_chunks FOR SELECT TO authenticated
    USING (EXISTS (SELECT 1 FROM public.user_papers up WHERE up.paper_id = paper_chunks.paper_id AND up.user_id = auth.uid()));
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Users can read paper embeddings') THEN
    CREATE POLICY "Users can read paper embeddings" ON public.paper_embeddings FOR SELECT TO authenticated
    USING (EXISTS (SELECT 1 FROM public.user_papers up WHERE up.paper_id = paper_embeddings.paper_id AND up.user_id = auth.uid()));
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Users can read/write chat history') THEN
    CREATE POLICY "Users can read/write chat history" ON public.chat_history FOR ALL TO authenticated
    USING (user_id = auth.uid());
  END IF;
END$$;
