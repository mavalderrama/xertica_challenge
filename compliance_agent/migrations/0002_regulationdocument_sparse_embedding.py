# Squashed from original 0002 + 0003:
# - Adds sparse_embedding (SparseVectorField 30k-dim) for TF-IDF retrieval
# - Changes embedding dimensions from 768 to 384 (all-MiniLM-L6-v2)
# - Keeps related_articles M2M (originally removed then re-added — kept clean here)

import pgvector.django.sparsevec
import pgvector.django.vector
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('compliance_agent', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='regulationdocument',
            name='sparse_embedding',
            field=pgvector.django.sparsevec.SparseVectorField(blank=True, dimensions=30000, null=True),
        ),
        migrations.AlterField(
            model_name='regulationdocument',
            name='embedding',
            field=pgvector.django.vector.VectorField(blank=True, dimensions=384, null=True),
        ),
    ]
