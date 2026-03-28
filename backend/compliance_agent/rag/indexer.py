from compliance_agent.rag.chunking import RegulationChunker
from compliance_agent.rag.embeddings import HFEmbedder
from compliance_agent.rag.interfaces import IIndexer
from compliance_agent.tools.base import GCSToolInterface


class RegulationIndexer(IIndexer):
    """Indexes regulatory PDFs from GCS into the pgvector store."""

    def __init__(
        self,
        gcs_tool: GCSToolInterface,
        embedder: HFEmbedder,
        chunker: RegulationChunker | None = None,
    ) -> None:
        self.gcs_tool = gcs_tool
        self.embedder = embedder
        self.chunker = chunker or RegulationChunker()

    async def index_document(
        self, gcs_uri: str, source: str, document_ref: str
    ) -> int:
        from django.contrib.postgres.search import SearchVector

        from compliance_agent.models import RegulationDocument

        text = await self.gcs_tool.extract_pdf_text(gcs_uri)
        text_chunks = self.chunker.chunk(text)

        contents = [c.content for c in text_chunks]
        embeddings = self.embedder.embed(contents)

        created = 0
        for chunk, embedding in zip(text_chunks, embeddings, strict=True):
            _, was_created = await RegulationDocument.objects.aupdate_or_create(
                document_ref=document_ref,
                chunk_index=chunk.chunk_index,
                defaults={
                    "source": source,
                    "content": chunk.content,
                    "embedding": embedding,
                    "gcs_uri": gcs_uri,
                },
            )
            if was_created:
                created += 1

        await RegulationDocument.objects.filter(document_ref=document_ref).aupdate(
            search_vector=SearchVector("content", config="spanish")
        )
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
        """Index all documents, then update search vectors in bulk per document."""
        from django.contrib.postgres.search import SearchVector

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

        created = 0
        for i, (chunk, embedding) in enumerate(
            zip(all_chunks, embeddings, strict=True)
        ):
            gcs_uri, source, document_ref = all_metas[i]
            _, was_created = await RegulationDocument.objects.aupdate_or_create(
                document_ref=document_ref,
                chunk_index=chunk.chunk_index,
                defaults={
                    "source": source,
                    "content": chunk.content,
                    "embedding": embedding,
                    "gcs_uri": gcs_uri,
                },
            )
            if was_created:
                created += 1

        # Update search vectors for all indexed documents in bulk
        for document_ref in document_refs:
            await RegulationDocument.objects.filter(document_ref=document_ref).aupdate(
                search_vector=SearchVector("content", config="spanish")
            )

        return created
