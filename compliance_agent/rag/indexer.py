from compliance_agent.rag.chunking import RegulationChunker
from compliance_agent.rag.embeddings import HFEmbedder
from compliance_agent.rag.interfaces import IIndexer
from compliance_agent.rag.sparse_vectorizer import SparseVectorizer
from compliance_agent.tools.base import GCSToolInterface


class RegulationIndexer(IIndexer):
    """Indexes regulatory PDFs from GCS into the pgvector store."""

    def __init__(
        self,
        gcs_tool: GCSToolInterface,
        embedder: HFEmbedder,
        chunker: RegulationChunker | None = None,
        sparse_vectorizer: SparseVectorizer | None = None,
    ) -> None:
        self.gcs_tool = gcs_tool
        self.embedder = embedder
        self.chunker = chunker or RegulationChunker()
        self.sparse_vectorizer = sparse_vectorizer

    async def index_document(
        self, gcs_uri: str, source: str, document_ref: str
    ) -> int:
        from compliance_agent.models import RegulationDocument

        text = await self.gcs_tool.extract_pdf_text(gcs_uri)
        text_chunks = self.chunker.chunk(text)

        contents = [c.content for c in text_chunks]
        embeddings = self.embedder.embed(contents)

        sparse_embeddings = None
        if self.sparse_vectorizer is not None:
            sparse_embeddings = self.sparse_vectorizer.fit_transform(contents)

        created = 0
        for i, (chunk, embedding) in enumerate(
            zip(text_chunks, embeddings, strict=True)
        ):
            defaults = {
                "source": source,
                "content": chunk.content,
                "embedding": embedding,
                "gcs_uri": gcs_uri,
            }
            if sparse_embeddings is not None:
                defaults["sparse_embedding"] = sparse_embeddings[i]

            _, was_created = await RegulationDocument.objects.aupdate_or_create(
                document_ref=document_ref,
                chunk_index=chunk.chunk_index,
                defaults=defaults,
            )
            if was_created:
                created += 1
        return created

    async def link_related_articles(self) -> int:
        """
        Parse cross-references between regulation chunks and create M2M relationships.
        Scans each chunk's content for "Artículo N" / "Art. N" patterns and links
        to matching articles within the same regulatory source.
        Returns the number of relationships created.
        """
        import re

        from compliance_agent.models import RegulationDocument

        pattern = re.compile(r"Art(?:ículo|iculo|\.)\s*(\d+)", re.IGNORECASE)
        links_created = 0

        async for doc in RegulationDocument.objects.all():
            refs = pattern.findall(doc.content)
            for ref_num in set(refs):
                async for related in RegulationDocument.objects.filter(
                    article_number=ref_num,
                    source=doc.source,
                ).exclude(pk=doc.pk):
                    await doc.related_articles.aadd(related)
                    links_created += 1

        return links_created

    async def bulk_index(
        self,
        gcs_uris: list[str],
        sources: list[str],
        document_refs: list[str],
    ) -> int:
        """Fit vocabulary across all documents before storing sparse embeddings."""
        from compliance_agent.models import RegulationDocument

        all_chunks = []
        all_metas = []
        for gcs_uri, source, document_ref in zip(
            gcs_uris, sources, document_refs, strict=True
        ):
            text = await self.gcs_tool.extract_pdf_text(gcs_uri)
            for chunk in self.chunker.chunk(text):
                all_chunks.append(chunk)
                all_metas.append((gcs_uri, source, document_ref))

        contents = [c.content for c in all_chunks]
        embeddings = self.embedder.embed(contents)

        sparse_embeddings = None
        if self.sparse_vectorizer is not None:
            sparse_embeddings = self.sparse_vectorizer.fit_transform(contents)

        created = 0
        for i, (chunk, embedding) in enumerate(
            zip(all_chunks, embeddings, strict=True)
        ):
            gcs_uri, source, document_ref = all_metas[i]
            defaults = {
                "source": source,
                "content": chunk.content,
                "embedding": embedding,
                "gcs_uri": gcs_uri,
            }
            if sparse_embeddings is not None:
                defaults["sparse_embedding"] = sparse_embeddings[i]

            _, was_created = await RegulationDocument.objects.aupdate_or_create(
                document_ref=document_ref,
                chunk_index=chunk.chunk_index,
                defaults=defaults,
            )
            if was_created:
                created += 1
        return created
