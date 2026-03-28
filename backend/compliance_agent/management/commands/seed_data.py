"""
Django management command: seed synthetic alert data for live testing.

Usage:
    python manage.py seed_data [--clear]

Options:
    --clear    Delete all existing alerts before seeding

Scenarios created:
    1. Low-risk dismissal candidate       (CUST-LOW-001,   COP, non-PEP, xgb=0.31)
    2. High-risk escalation candidate     (CUST-HIGH-002,  USD, non-PEP, xgb=0.89)
    3. PEP alert — small amount           (CUST-PEP-003,   MXN, is_pep=True, xgb=0.45)
    4. PEP alert — large amount           (CUST-PEP-004,   USD, is_pep=True, xgb=0.92)
    5. Request-info candidate             (CUST-MID-005,   PEN, non-PEP, xgb=0.61)
    6. Multi-currency suspicious          (CUST-MULTI-006, USD, non-PEP, xgb=0.77)
    7. Corporate account, high volume     (CUST-CORP-007,  COP, non-PEP, xgb=0.83)
    8. Returning low-risk customer        (CUST-SAFE-008,  MXN, non-PEP, xgb=0.22)
"""

from datetime import UTC, datetime, timedelta

from django.core.management.base import BaseCommand

from compliance_agent.models import Alert


class Command(BaseCommand):
    help = "Seed synthetic alert data for live demo and manual testing"

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete all existing alerts before seeding",
        )

    def handle(self, *args, **options):
        if options["clear"]:
            deleted, _ = Alert.objects.all().delete()
            self.stdout.write(self.style.WARNING(f"Deleted {deleted} existing alerts"))

        now = datetime.now(tz=UTC)
        alerts = self._build_scenarios(now)

        created = 0
        skipped = 0
        ids = {}

        for scenario in alerts:
            external_id = scenario.pop("external_alert_id")
            obj, was_created = Alert.objects.get_or_create(
                external_alert_id=external_id,
                defaults=scenario,
            )
            if was_created:
                created += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  Created [{external_id}]  customer={obj.customer_id}"
                        f"  amount={obj.amount} {obj.currency}"
                        f"  pep={obj.is_pep}  xgb={obj.xgboost_score}"
                        f"  → id={obj.id}"
                    )
                )
            else:
                skipped += 1
                self.stdout.write(
                    f"  Skipped [{external_id}] (already exists → id={obj.id})"
                )
            ids[external_id] = str(obj.id)

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(f"Done — {created} created, {skipped} skipped.")
        )
        self.stdout.write("")
        self.stdout.write("Alert UUIDs (copy for curl / live test script):")
        self.stdout.write("-" * 60)
        for ext_id, uuid in ids.items():
            self.stdout.write(f"  {ext_id:<30} {uuid}")
        self.stdout.write("-" * 60)
        self.stdout.write("")
        self.stdout.write("Quick test:")
        first_uuid = next(iter(ids.values()))
        self.stdout.write(
            f"  curl -s -X POST http://localhost:8000/api/v1/alerts/{first_uuid}/investigate | python3 -m json.tool"
        )

    def _build_scenarios(self, now: datetime) -> list[dict]:
        return [
            # ── Scenario 1 ─────────────────────────────────────────────────────
            # Expected: DISMISS — low transaction amounts, consistent COP activity,
            # clean profile, low xgboost score
            {
                "external_alert_id": "LIVE-LOW-RISK-001",
                "customer_id": "CUST-LOW-001",
                "is_pep": False,
                "amount": "3500000.00",     # 3.5M COP — below the 10M threshold
                "currency": "COP",
                "transaction_date": now - timedelta(hours=2),
                "status": Alert.Status.PENDING,
                "xgboost_score": 0.31,
                "raw_payload": {
                    "source": "xgboost_v3",
                    "alert_type": "UNUSUAL_AMOUNT",
                    "segment": "retail_individual",
                    "notes": "Amount slightly above customer average but within normal range",
                },
            },
            # ── Scenario 2 ─────────────────────────────────────────────────────
            # Expected: ESCALATE — high USD amount, high xgboost score, the mock
            # BigQuery tool for CUST-HIGH-002 will generate 10-30 transactions;
            # the customer_id seed produces enough variety to look suspicious
            {
                "external_alert_id": "LIVE-HIGH-RISK-002",
                "customer_id": "CUST-HIGH-002",
                "is_pep": False,
                "amount": "85000.00",       # $85,000 USD — well above reporting thresholds
                "currency": "USD",
                "transaction_date": now - timedelta(hours=6),
                "status": Alert.Status.PENDING,
                "xgboost_score": 0.89,
                "raw_payload": {
                    "source": "xgboost_v3",
                    "alert_type": "HIGH_AMOUNT_TRANSFER",
                    "segment": "sme",
                    "notes": "Single transfer significantly above customer 90-day average",
                },
            },
            # ── Scenario 3 ─────────────────────────────────────────────────────
            # Expected: ESCALATE (PEP hard-rule) — small amount but mandatory
            # escalation because is_pep=True. No LLM or RAG involved.
            {
                "external_alert_id": "LIVE-PEP-SMALL-003",
                "customer_id": "CUST-PEP-003",
                "is_pep": True,
                "amount": "12000.00",       # $12,000 MXN — moderate amount
                "currency": "MXN",
                "transaction_date": now - timedelta(hours=1),
                "status": Alert.Status.PENDING,
                "xgboost_score": 0.45,
                "raw_payload": {
                    "source": "xgboost_v3",
                    "alert_type": "PEP_TRANSACTION",
                    "segment": "high_value_individual",
                    "pep_category": "domestic_official",
                    "notes": "Customer flagged as PEP in national registry",
                },
            },
            # ── Scenario 4 ─────────────────────────────────────────────────────
            # Expected: ESCALATE (PEP hard-rule + high risk) — both triggers fire
            {
                "external_alert_id": "LIVE-PEP-LARGE-004",
                "customer_id": "CUST-PEP-004",
                "is_pep": True,
                "amount": "750000.00",      # $750,000 USD
                "currency": "USD",
                "transaction_date": now - timedelta(days=1),
                "status": Alert.Status.PENDING,
                "xgboost_score": 0.92,
                "raw_payload": {
                    "source": "xgboost_v3",
                    "alert_type": "PEP_HIGH_VALUE",
                    "segment": "high_value_individual",
                    "pep_category": "foreign_official",
                    "notes": "Large wire transfer. Customer is a foreign PEP (senior government official).",
                },
            },
            # ── Scenario 5 ─────────────────────────────────────────────────────
            # Expected: REQUEST_INFO — medium risk, ambiguous patterns; the LLM
            # may request additional documentation before deciding
            {
                "external_alert_id": "LIVE-MID-RISK-005",
                "customer_id": "CUST-MID-005",
                "is_pep": False,
                "amount": "18500.00",       # S/18,500 PEN — above threshold but not extreme
                "currency": "PEN",
                "transaction_date": now - timedelta(hours=12),
                "status": Alert.Status.PENDING,
                "xgboost_score": 0.61,
                "raw_payload": {
                    "source": "xgboost_v3",
                    "alert_type": "UNUSUAL_PATTERN",
                    "segment": "retail_individual",
                    "notes": "Moderate score. Customer recently changed declared profession.",
                },
            },
            # ── Scenario 6 ─────────────────────────────────────────────────────
            # Expected: ESCALATE — multi-currency activity. The mock BQ tool
            # generates mixed COP/MXN/PEN/USD for CUST-MULTI-006, which combined
            # with the high xgboost score should push toward escalation
            {
                "external_alert_id": "LIVE-MULTI-CCY-006",
                "customer_id": "CUST-MULTI-006",
                "is_pep": False,
                "amount": "45000.00",       # $45,000 USD equivalent
                "currency": "USD",
                "transaction_date": now - timedelta(hours=8),
                "status": Alert.Status.PENDING,
                "xgboost_score": 0.77,
                "raw_payload": {
                    "source": "xgboost_v3",
                    "alert_type": "MULTI_CURRENCY",
                    "segment": "retail_individual",
                    "notes": "Customer shows transactions in 4 currencies over 90 days",
                },
            },
            # ── Scenario 7 ─────────────────────────────────────────────────────
            # Expected: ESCALATE — corporate account, large COP amount above
            # COP 50M SARLAFT threshold for legal entities (CE 029/2014), high xgboost score
            {
                "external_alert_id": "LIVE-CORP-007",
                "customer_id": "CUST-CORP-007",
                "is_pep": False,
                "amount": "48000000.00",    # 48M COP — well above 10M threshold
                "currency": "COP",
                "transaction_date": now - timedelta(hours=3),
                "status": Alert.Status.PENDING,
                "xgboost_score": 0.83,
                "raw_payload": {
                    "source": "xgboost_v3",
                    "alert_type": "HIGH_AMOUNT_CASH",
                    "segment": "corporate",
                    "entity_type": "SAS",
                    "notes": "Cash deposit significantly above corporate customer baseline",
                },
            },
            # ── Scenario 8 ─────────────────────────────────────────────────────
            # Expected: DISMISS — very low risk score, MXN retail customer,
            # consistent with known profile
            {
                "external_alert_id": "LIVE-SAFE-008",
                "customer_id": "CUST-SAFE-008",
                "is_pep": False,
                "amount": "8500.00",        # MXN $8,500 — below $10,000 threshold
                "currency": "MXN",
                "transaction_date": now - timedelta(days=2),
                "status": Alert.Status.PENDING,
                "xgboost_score": 0.22,
                "raw_payload": {
                    "source": "xgboost_v3",
                    "alert_type": "ROUTINE_CHECK",
                    "segment": "retail_individual",
                    "notes": "Low-score routine check. Triggered by velocity rule, not amount.",
                },
            },
        ]
