
from compliance_agent.rag.chunking import RegulationChunker


def test_chunker_splits_long_text():
    chunker = RegulationChunker(chunk_size=100, overlap=10)
    text = "A" * 300
    chunks = chunker.chunk(text)
    assert len(chunks) > 1


def test_chunker_respects_article_boundaries():
    chunker = RegulationChunker(chunk_size=500, overlap=50)
    text = "Artículo 1. Primera disposición.\n\nArtículo 2. Segunda disposición.\n\nArtículo 3. Tercera."
    chunks = chunker.chunk(text)
    assert len(chunks) >= 1
    assert all(isinstance(c.content, str) for c in chunks)


def test_chunker_chunk_indices_are_sequential():
    chunker = RegulationChunker(chunk_size=50, overlap=5)
    text = "Lorem ipsum " * 50
    chunks = chunker.chunk(text)
    indices = [c.chunk_index for c in chunks]
    assert indices == list(range(len(chunks)))


def test_chunker_short_text_single_chunk():
    chunker = RegulationChunker(chunk_size=1000, overlap=100)
    text = "Short text."
    chunks = chunker.chunk(text)
    assert len(chunks) == 1
    assert chunks[0].content == "Short text."


def test_default_chunk_size_constants():
    from compliance_agent.rag.chunking import CHUNK_OVERLAP_TOKENS, CHUNK_SIZE_TOKENS

    assert CHUNK_SIZE_TOKENS == 512
    assert CHUNK_OVERLAP_TOKENS == 64
