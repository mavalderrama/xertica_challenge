"""
Django management command: index regulatory documents into the vector store.

Reads the fixture regulatory documents (UIAF, CNBV, SBS) from
tests/fixtures/regulatory_docs/ and indexes them via RegulationIndexer
into the pgvector store. Uses PostgreSQL native full-text search (tsvector)
for BM25-equivalent sparse retrieval and builds the cross-reference graph layer.

Usage:
    python manage.py index_regulations [--clear] [--no-graph]

Options:
    --clear       Delete all existing RegulationDocument rows before indexing
    --no-graph    Skip cross-reference graph link building
"""

import asyncio
from pathlib import Path

from django.core.management.base import BaseCommand

from compliance_agent.models import RegulationDocument
from compliance_agent.rag.chunking import RegulationChunker
from compliance_agent.rag.embeddings import HFEmbedder
from compliance_agent.rag.indexer import RegulationIndexer
from compliance_agent.tools.gcs_tools import MockGCSTool

# Fixture regulatory documents — paths relative to the backend/ directory
_BACKEND_DIR = Path(__file__).resolve().parents[3]  # backend/
_FIXTURES_DIR = _BACKEND_DIR / "tests" / "fixtures" / "regulatory_docs"

REGULATION_FILES = [
    {
        "path": _FIXTURES_DIR / "uiaf_sarlaft_sfc_ce029_2014.txt",
        "source": RegulationDocument.Source.UIAF,
        "document_ref": "uiaf_sarlaft_sfc_ce029_2014",
        "gcs_uri": "gs://compliance-docs/regulations/uiaf_sarlaft_sfc_ce029_2014.txt",
    },
    {
        "path": _FIXTURES_DIR / "uiaf_decreto_830_2021.txt",
        "source": RegulationDocument.Source.UIAF,
        "document_ref": "uiaf_decreto_830_2021",
        "gcs_uri": "gs://compliance-docs/regulations/uiaf_decreto_830_2021.txt",
    },
    {
        "path": _FIXTURES_DIR / "cnbv_dcg_art115.txt",
        "source": RegulationDocument.Source.CNBV,
        "document_ref": "cnbv_dcg_art115",
        "gcs_uri": "gs://compliance-docs/regulations/cnbv_dcg_art115.txt",
    },
    {
        "path": _FIXTURES_DIR / "sbs_resolucion_789_2018.txt",
        "source": RegulationDocument.Source.SBS,
        "document_ref": "sbs_resolucion_789_2018",
        "gcs_uri": "gs://compliance-docs/regulations/sbs_resolucion_789_2018.txt",
    },
    {
        "path": _FIXTURES_DIR / "sbs_ley_27693_uif.txt",
        "source": RegulationDocument.Source.SBS,
        "document_ref": "sbs_ley_27693_uif",
        "gcs_uri": "gs://compliance-docs/regulations/sbs_ley_27693_uif.txt",
    },
]


class _TextFileMockGCS(MockGCSTool):
    """GCS mock that reads real .txt fixture files instead of returning boilerplate."""

    async def extract_pdf_text(self, gcs_uri: str) -> str:
        # gcs_uri → map back to local fixture path
        for reg in REGULATION_FILES:
            if reg["gcs_uri"] == gcs_uri:
                return reg["path"].read_text(encoding="utf-8")
        # fallback: return parent mock behaviour
        return await super().extract_pdf_text(gcs_uri)


class Command(BaseCommand):
    help = "Index regulatory documents into the pgvector store for RAG retrieval"

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete all existing RegulationDocument rows before indexing",
        )
        parser.add_argument(
            "--no-graph",
            action="store_true",
            help="Skip cross-reference graph link building",
        )

    def handle(self, *args, **options):
        if options["clear"]:
            deleted, _ = RegulationDocument.objects.all().delete()
            self.stdout.write(
                self.style.WARNING(f"Deleted {deleted} existing regulation chunks")
            )

        asyncio.run(self._run(options))

    async def _run(self, options: dict) -> None:
        gcs_tool = _TextFileMockGCS()
        embedder = HFEmbedder()
        chunker = RegulationChunker()

        indexer = RegulationIndexer(
            gcs_tool=gcs_tool,
            embedder=embedder,
            chunker=chunker,
        )

        self.stdout.write("Loading embedding model (first run may download weights)...")
        embedder.embed(["warm up"])

        gcs_uris = [r["gcs_uri"] for r in REGULATION_FILES]
        sources = [r["source"] for r in REGULATION_FILES]
        document_refs = [r["document_ref"] for r in REGULATION_FILES]

        self.stdout.write(
            f"Indexing {len(REGULATION_FILES)} regulatory documents "
            f"(dense embeddings + PostgreSQL BM25 full-text search)..."
        )

        total_chunks = await indexer.bulk_index(
            gcs_uris=gcs_uris,
            sources=sources,
            document_refs=document_refs,
        )

        self.stdout.write(
            self.style.SUCCESS(f"Indexed {total_chunks} new chunks total")
        )

        for reg in REGULATION_FILES:
            count = await RegulationDocument.objects.filter(
                document_ref=reg["document_ref"]
            ).acount()
            self.stdout.write(
                f"  [{reg['source']:<4}] {reg['document_ref']:<35} {count} chunks"
            )

        if not options["no_graph"]:
            self.stdout.write("Building cross-reference graph layer...")
            links = await indexer.link_related_articles()
            self.stdout.write(
                self.style.SUCCESS(f"Created {links} article cross-reference links")
            )

        total = await RegulationDocument.objects.acount()
        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"Vector store ready: {total} chunks across "
                f"{len(REGULATION_FILES)} documents"
            )
        )
