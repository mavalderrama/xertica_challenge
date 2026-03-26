import uuid

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class RiskAnalysis(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    investigation = models.OneToOneField(
        "compliance_agent.Investigation",
        on_delete=models.CASCADE,
        related_name="risk_analysis",
    )
    risk_score = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(10)]
    )
    justification = models.TextField()
    anomalous_patterns = models.JSONField(default=list)
    human_summary = models.TextField()
    model_used = models.CharField(max_length=100)
    token_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "compliance_agent"

    def __str__(self) -> str:
        return f"RiskAnalysis score={self.risk_score} for investigation {self.investigation_id}"
