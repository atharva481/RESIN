from app.services.chunking import TextChunker


def test_chunk_text_overlap():
    chunker = TextChunker(chunk_size=10, overlap_size=2)
    sample_text = "word1 word2 word3 word4 word5 word6 word7 word8 word9 word10 word11 word12 word13"
    chunks = chunker.chunk_text(text=sample_text, paper_id="test-id")
    assert len(chunks) == 2
    assert chunks[0].chunk_index == 0
    assert chunks[0].word_count == 10
    assert chunks[1].chunk_index == 1


def test_chunk_sections():
    chunker = TextChunker(chunk_size=50, overlap_size=10)
    sections = {
        "Abstract": "This is the abstract section of the paper.",
        "Methodology": "Here we describe the novel methodology and dataset preprocessing.",
    }
    chunks = chunker.chunk_paper(
        paper_id="test-id-123",
        title="Test Paper",
        abstract="Abstract text",
        sections=sections,
    )
    assert len(chunks) == 2
    assert chunks[0].section_title == "Abstract"
    assert chunks[1].section_title == "Methodology"
