import uuid

from django.db import models


class Alert(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        INVESTIGATING = "INVESTIGATING", "Investigating"
        ESCALATED = "ESCALATED", "Escalated"
        DISMISSED = "DISMISSED", "Dismissed"
        AWAITING_INFO = "AWAITING_INFO", "Awaiting Info"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    external_alert_id = models.CharField(max_length=255, unique=True, db_index=True)
    customer_id = models.CharField(max_length=255, db_index=True)
    is_pep = models.BooleanField(default=False, db_index=True)
    amount = models.DecimalField(max_digits=20, decimal_places=2)
    currency = models.CharField(max_length=3, default="USD")
    transaction_date = models.DateTimeField()
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    xgboost_score = models.FloatField(null=True, blank=True)
    raw_payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "compliance_agent"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Alert {self.external_alert_id} [{self.status}]"
