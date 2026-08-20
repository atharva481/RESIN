-- Enable pgvector extension (if not already)
CREATE EXTENSION IF NOT EXISTS vector;

-- Create chat_history table for persisting user conversations
CREATE TABLE IF NOT EXISTS public.chat_history (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  folder_id uuid REFERENCES public.folders(id) ON DELETE SET NULL,
  role text NOT NULL CHECK (role IN ('user','assistant')),
  content text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- Index for fast lookup of a user's chat history (ordered by time)
CREATE INDEX IF NOT EXISTS ix_chat_history_user_folder
  ON public.chat_history (user_id, folder_id, created_at);

-- Ensure paper_embeddings embedding column is of type vector (the extension makes it so)
-- If you want to store per-chunk embeddings, you could change the column to vector[] but we keep single vector per paper.
-- Create an ivfflat index for fast similarity search on paper_embeddings
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

-- Optional: allow service role to bypass RLS (not needed if we bypass via service key)
COMMENT ON FUNCTION public.match_paper_embeddings IS 'Return paper_ids and cosine similarity for a query embedding, filtered by user and/or folder.';