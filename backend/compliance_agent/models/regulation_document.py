import uuid

from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from django.db import models
from pgvector.django import HnswIndex, VectorField


class RegulationDocument(models.Model):
    class Source(models.TextChoices):
        UIAF = "UIAF", "UIAF (Colombia)"
        CNBV = "CNBV", "CNBV (Mexico)"
        SBS = "SBS", "SBS (Peru)"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source = models.CharField(max_length=10, choices=Source.choices, db_index=True)
    document_ref = models.CharField(max_length=255)
    article_number = models.CharField(max_length=50, blank=True)
    content = models.TextField()
    embedding = VectorField(dimensions=384, null=True, blank=True)
    search_vector = SearchVectorField(null=True)
    chunk_index = models.IntegerField(default=0)
    gcs_uri = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    related_articles = models.ManyToManyField(
        "self",
        symmetrical=False,
        blank=True,
        related_name="referenced_by",
    )

    class Meta:
        app_label = "compliance_agent"
        unique_together = [("document_ref", "chunk_index")]
        indexes = [
            HnswIndex(
                fields=["embedding"],
                name="regulation_embedding_hnsw",
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
            ),
            GinIndex(fields=["search_vector"], name="regulation_search_vector_gin"),
        ]

    def __str__(self) -> str:
        return f"[{self.source}] {self.document_ref} chunk {self.chunk_index}"
