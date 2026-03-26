"""
Chunking strategy justification:
- Chunk size: 512 tokens — balances regulatory article granularity (most articles
  fit in one chunk) with embedding quality (larger chunks degrade retrieval recall).
- Overlap: 64 tokens (~12.5%) — ensures article headers and cross-references at
  chunk boundaries are not silently dropped.
- Separators: ["\n\nArtículo", "\n\n", "\n"] — splits first on article boundaries
  (regulatory documents are structured around articles), then paragraphs, then lines.
  This preserves semantic coherence of regulatory clauses.
"""

from dataclasses import dataclass

CHUNK_SIZE_TOKENS = 512
CHUNK_OVERLAP_TOKENS = 64
SEPARATORS = ["\n\nArtículo", "\n\n", "\n", " "]

# Approximation: 1 token ≈ 4 characters for Spanish regulatory text
CHARS_PER_TOKEN = 4
CHUNK_SIZE_CHARS = CHUNK_SIZE_TOKENS * CHARS_PER_TOKEN
OVERLAP_CHARS = CHUNK_OVERLAP_TOKENS * CHARS_PER_TOKEN


@dataclass
class TextChunk:
    content: str
    chunk_index: int


class RegulationChunker:
    def __init__(
        self,
        chunk_size: int = CHUNK_SIZE_CHARS,
        overlap: int = OVERLAP_CHARS,
        separators: list[str] | None = None,
    ) -> None:
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.separators = separators or SEPARATORS

    def chunk(self, text: str) -> list[TextChunk]:
        chunks = self._split_recursive(text, self.separators)
        return [TextChunk(content=c, chunk_index=i) for i, c in enumerate(chunks)]

    def _split_recursive(self, text: str, separators: list[str]) -> list[str]:
        if not separators:
            return self._split_by_size(text)

        separator = separators[0]
        remaining = separators[1:]

        if separator not in text:
            return self._split_recursive(text, remaining)

        parts = text.split(separator)
        chunks: list[str] = []
        current = ""

        for i, part in enumerate(parts):
            piece = (separator + part) if i > 0 else part
            if len(current) + len(piece) <= self.chunk_size:
                current += piece
            else:
                if current:
                    chunks.append(current.strip())
                if len(piece) > self.chunk_size:
                    sub_chunks = self._split_recursive(piece, remaining)
                    chunks.extend(sub_chunks[:-1])
                    current = sub_chunks[-1] if sub_chunks else ""
                else:
                    current = piece

        if current.strip():
            chunks.append(current.strip())

        return self._apply_overlap(chunks)

    def _split_by_size(self, text: str) -> list[str]:
        chunks = []
        start = 0
        while start < len(text):
            end = start + self.chunk_size
            chunks.append(text[start:end])
            start = end - self.overlap
        return chunks

    def _apply_overlap(self, chunks: list[str]) -> list[str]:
        if len(chunks) <= 1:
            return chunks
        result = [chunks[0]]
        for i in range(1, len(chunks)):
            overlap_text = chunks[i - 1][-self.overlap :] if self.overlap else ""
            result.append(overlap_text + chunks[i])
        return result
