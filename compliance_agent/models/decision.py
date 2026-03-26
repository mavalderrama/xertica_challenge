import uuid

from django.db import models


class Decision(models.Model):
    class DecisionType(models.TextChoices):
        ESCALATE = "ESCALATE", "Escalate"
        DISMISS = "DISMISS", "Dismiss"
        REQUEST_INFO = "REQUEST_INFO", "Request Info"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    risk_analysis = models.OneToOneField(
        "compliance_agent.RiskAnalysis",
        on_delete=models.CASCADE,
        related_name="decision",
    )
    decision_type = models.CharField(max_length=20, choices=DecisionType.choices)
    confidence = models.FloatField()
    regulations_cited = models.JSONField(default=list)
    step_by_step_reasoning = models.TextField()
    is_pep_override_applied = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "compliance_agent"

    def __str__(self) -> str:
        return f"Decision {self.decision_type} (confidence={self.confidence:.2f})"
