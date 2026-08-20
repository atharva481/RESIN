-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Create paper_chunks table
CREATE TABLE IF NOT EXISTS paper_chunks (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  paper_id    uuid NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
  chunk_index int NOT NULL,
  section_title text,
  content     text NOT NULL,
  embedding   vector(768),  -- Gemini text-embedding-004
  word_count  int,
  created_at  timestamptz DEFAULT now(),
  UNIQUE (paper_id, chunk_index)
);

-- Index for vector cosine similarity search
CREATE INDEX IF NOT EXISTS paper_chunks_embedding_idx
  ON paper_chunks USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 100);

-- Index for paper_id lookup
CREATE INDEX IF NOT EXISTS paper_chunks_paper_id_idx
  ON paper_chunks (paper_id);

-- Optional columns on papers table
ALTER TABLE papers ADD COLUMN IF NOT EXISTS indexed_at timestamptz;
ALTER TABLE papers ADD COLUMN IF NOT EXISTS full_text text;

-- Stored procedure for vector similarity search
CREATE OR REPLACE FUNCTION match_paper_chunks(
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
  FROM paper_chunks pc
  WHERE
    (filter_paper_id IS NULL OR pc.paper_id = filter_paper_id)
    AND 1 - (pc.embedding <=> query_embedding) > match_threshold
  ORDER BY pc.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;

-- Row Level Security for paper_chunks
ALTER TABLE paper_chunks ENABLE ROW LEVEL SECURITY;

-- Select policy: users can read chunks for papers in their library
CREATE POLICY "Users can read paper chunks"
  ON paper_chunks FOR SELECT
  TO authenticated
  USING (
    EXISTS (
      SELECT 1 FROM user_papers up
      WHERE up.paper_id = paper_chunks.paper_id
        AND up.user_id = auth.uid()
    )
  );

-- Service role bypasses RLS for writes automatically in Supabase
