import uuid

from django.db import models


class AuditLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    alert = models.ForeignKey(
        "compliance_agent.Alert",
        on_delete=models.CASCADE,
        related_name="audit_logs",
    )
    event_type = models.CharField(max_length=100)
    agent_name = models.CharField(max_length=100)
    input_snapshot = models.JSONField(default=dict)
    output_snapshot = models.JSONField(default=dict)
    langfuse_trace_id = models.CharField(max_length=255, blank=True)
    duration_ms = models.IntegerField(default=0)
    token_cost_usd = models.DecimalField(max_digits=12, decimal_places=8, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "compliance_agent"
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"AuditLog [{self.agent_name}] {self.event_type} @ {self.created_at}"
