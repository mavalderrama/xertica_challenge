import uuid

from django.db import models


class Investigation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    alert = models.OneToOneField(
        "compliance_agent.Alert",
        on_delete=models.CASCADE,
        related_name="investigation",
    )
    transaction_history = models.JSONField(default=list)
    documents_analyzed = models.JSONField(default=list)
    structured_context = models.JSONField(default=dict)
    duration_seconds = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "compliance_agent"

    def __str__(self) -> str:
        return f"Investigation for alert {self.alert_id}"
