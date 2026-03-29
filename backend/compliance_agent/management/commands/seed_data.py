"""
Django management command: seed synthetic alert data for live testing.

Usage:
    python manage.py seed_data [--clear]

Options:
    --clear    Delete all existing alerts before seeding

Scenarios created:
    1.  Low-risk dismissal candidate           (CUST-LOW-001,    COP, non-PEP, xgb=0.31) → DISMISS
    2.  High-risk escalation candidate         (CUST-HIGH-002,   USD, non-PEP, xgb=0.89) → ESCALATE
    3.  PEP alert — small amount               (CUST-PEP-003,    MXN, is_pep=True, xgb=0.45) → ESCALATE
    4.  PEP alert — large amount               (CUST-PEP-004,    USD, is_pep=True, xgb=0.92) → ESCALATE
    5.  Request-info candidate                 (CUST-MID-005,    PEN, non-PEP, xgb=0.61) → REQUEST_INFO
    6.  Multi-currency suspicious              (CUST-MULTI-006,  USD, non-PEP, xgb=0.77) → ESCALATE
    7.  Corporate account, high volume         (CUST-CORP-007,   COP, non-PEP, xgb=0.83) → ESCALATE
    8.  Returning low-risk customer            (CUST-SAFE-008,   MXN, non-PEP, xgb=0.22) → DISMISS
    9.  COP structuring just-under threshold   (CUST-STRUCT-009, COP, non-PEP, xgb=0.76) → ESCALATE
    10. New account large USD anomaly          (CUST-NEW-010,    USD, non-PEP, xgb=0.56) → REQUEST_INFO
    11. Micro-transaction USD routine          (CUST-MICRO-011,  USD, non-PEP, xgb=0.14) → DISMISS
    12. PEP corporate high-value USD           (CUST-PEP-012,    USD, is_pep=True, xgb=0.87) → ESCALATE
    13. High PEN well above SBS threshold      (CUST-PEN-013,    PEN, non-PEP, xgb=0.79) → ESCALATE
    14. Safe PEN below SBS threshold           (CUST-SAFE-014,   PEN, non-PEP, xgb=0.24) → DISMISS
    15. USD structuring just under CNBV limit  (CUST-STRUCT-015, USD, non-PEP, xgb=0.83) → ESCALATE
    16. International wire FATF jurisdiction   (CUST-WIRE-016,   USD, non-PEP, xgb=0.81) → ESCALATE
    17. SME low-risk MXN below threshold       (CUST-SME-017,    MXN, non-PEP, xgb=0.33) → DISMISS
    18. Identity change above SBS threshold    (CUST-IDCHG-018,  PEN, non-PEP, xgb=0.55) → REQUEST_INFO
    19. Large MXN wire above CNBV threshold    (CUST-MXN-019,    MXN, non-PEP, xgb=0.88) → ESCALATE
    20. Inbound remittance routine             (CUST-REM-020,    USD, non-PEP, xgb=0.16) → DISMISS
    21. Unusual-hour transactions above SBS    (CUST-NIGHT-021,  PEN, non-PEP, xgb=0.63) → REQUEST_INFO
    22. Large USD SME inconsistent profile     (CUST-LARGE-022,  USD, non-PEP, xgb=0.86) → ESCALATE
    23. PEP small PEN — hard rule              (CUST-PEP-023,    PEN, is_pep=True, xgb=0.38) → ESCALATE
    24. Low COP well below SARLAFT threshold   (CUST-LOW-024,    COP, non-PEP, xgb=0.27) → DISMISS
    25. Corporate MXN unusual activity         (CUST-CORP-025,   MXN, non-PEP, xgb=0.59) → REQUEST_INFO
    26. USD money-mule pass-through pattern    (CUST-MULE-026,   USD, non-PEP, xgb=0.84) → ESCALATE
    27. Tiny COP micro-transaction             (CUST-TINY-027,   COP, non-PEP, xgb=0.11) → DISMISS
    28. COP deposit vs declared income gap     (CUST-GAP-028,    COP, non-PEP, xgb=0.67) → REQUEST_INFO
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
                "amount": "3500000.00",  # 3.5M COP — below the 10M threshold
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
                "amount": "85000.00",  # $85,000 USD — well above reporting thresholds
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
                "amount": "12000.00",  # $12,000 MXN — moderate amount
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
                "amount": "750000.00",  # $750,000 USD
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
                "amount": "18500.00",  # S/18,500 PEN — above threshold but not extreme
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
                "amount": "45000.00",  # $45,000 USD equivalent
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
                "amount": "48000000.00",  # 48M COP — well above 10M threshold
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
                "amount": "8500.00",  # MXN $8,500 — below MXN 127K CNBV threshold
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
            # ── Scenario 9 ─────────────────────────────────────────────────────
            # Expected: ESCALATE — structuring pattern: multiple COP deposits at
            # COP 9.8M, just below the SARLAFT 10M individual threshold (CE 029/2014 §4.2.3)
            {
                "external_alert_id": "LIVE-STRUCT-009",
                "customer_id": "CUST-STRUCT-009",
                "is_pep": False,
                "amount": "9800000.00",  # COP 9.8M — 98% of SARLAFT 10M threshold
                "currency": "COP",
                "transaction_date": now - timedelta(hours=5),
                "status": Alert.Status.PENDING,
                "xgboost_score": 0.76,
                "raw_payload": {
                    "source": "xgboost_v3",
                    "alert_type": "STRUCTURING_PATTERN",
                    "segment": "retail_individual",
                    "notes": "Third deposit of COP 9.8M in the same week. Classic fraccionamiento pattern to stay below the SARLAFT reporting threshold.",
                },
            },
            # ── Scenario 10 ────────────────────────────────────────────────────
            # Expected: REQUEST_INFO — account opened only 45 days ago; first
            # large USD transfer raises due-diligence questions before deciding
            {
                "external_alert_id": "LIVE-NEW-ACCT-010",
                "customer_id": "CUST-NEW-010",
                "is_pep": False,
                "amount": "18500.00",  # USD $18,500 — well above CNBV USD 7,500
                "currency": "USD",
                "transaction_date": now - timedelta(hours=10),
                "status": Alert.Status.PENDING,
                "xgboost_score": 0.56,
                "raw_payload": {
                    "source": "xgboost_v3",
                    "alert_type": "NEW_ACCOUNT_ANOMALY",
                    "segment": "retail_individual",
                    "notes": "Account opened 45 days ago. This is the first high-value transfer. Origin of funds not yet documented in KYC file.",
                },
            },
            # ── Scenario 11 ────────────────────────────────────────────────────
            # Expected: DISMISS — micro-transaction, very low xgboost, no risk signals
            {
                "external_alert_id": "LIVE-MICRO-011",
                "customer_id": "CUST-MICRO-011",
                "is_pep": False,
                "amount": "320.00",  # USD $320 — trivial amount
                "currency": "USD",
                "transaction_date": now - timedelta(hours=1),
                "status": Alert.Status.PENDING,
                "xgboost_score": 0.14,
                "raw_payload": {
                    "source": "xgboost_v3",
                    "alert_type": "ROUTINE_CHECK",
                    "segment": "retail_individual",
                    "notes": "Triggered by daily velocity rule. Amount is well below any reporting threshold.",
                },
            },
            # ── Scenario 12 ────────────────────────────────────────────────────
            # Expected: ESCALATE — PEP hard-rule + corporate segment + large USD
            {
                "external_alert_id": "LIVE-PEP-CORP-012",
                "customer_id": "CUST-PEP-012",
                "is_pep": True,
                "amount": "92000.00",  # USD $92,000
                "currency": "USD",
                "transaction_date": now - timedelta(hours=4),
                "status": Alert.Status.PENDING,
                "xgboost_score": 0.87,
                "raw_payload": {
                    "source": "xgboost_v3",
                    "alert_type": "PEP_HIGH_VALUE",
                    "segment": "corporate",
                    "entity_type": "SA",
                    "pep_category": "domestic_official",
                    "notes": "Corporate account controlled by a domestic PEP. Large USD wire with no documented commercial counterpart.",
                },
            },
            # ── Scenario 13 ────────────────────────────────────────────────────
            # Expected: ESCALATE — PEN 43K is 4.3x the SBS PEN 10K threshold,
            # high xgboost, no documented business rationale
            {
                "external_alert_id": "LIVE-HIGH-PEN-013",
                "customer_id": "CUST-PEN-013",
                "is_pep": False,
                "amount": "43000.00",  # PEN 43,000 — 4.3x SBS threshold (~USD 11.6K)
                "currency": "PEN",
                "transaction_date": now - timedelta(hours=7),
                "status": Alert.Status.PENDING,
                "xgboost_score": 0.79,
                "raw_payload": {
                    "source": "xgboost_v3",
                    "alert_type": "HIGH_AMOUNT_TRANSFER",
                    "segment": "retail_individual",
                    "notes": "Single transfer at 4.3x the SBS reporting threshold. No declared business activity justifies this volume.",
                },
            },
            # ── Scenario 14 ────────────────────────────────────────────────────
            # Expected: DISMISS — PEN 3,800 is well below SBS PEN 10K threshold,
            # low xgboost, clean retail profile
            {
                "external_alert_id": "LIVE-SAFE-PEN-014",
                "customer_id": "CUST-SAFE-014",
                "is_pep": False,
                "amount": "3800.00",  # PEN 3,800 — 38% of SBS 10K threshold (~USD 1,027)
                "currency": "PEN",
                "transaction_date": now - timedelta(days=1),
                "status": Alert.Status.PENDING,
                "xgboost_score": 0.24,
                "raw_payload": {
                    "source": "xgboost_v3",
                    "alert_type": "ROUTINE_CHECK",
                    "segment": "retail_individual",
                    "notes": "Amount well below SBS reporting threshold. Low-score routine velocity check.",
                },
            },
            # ── Scenario 15 ────────────────────────────────────────────────────
            # Expected: ESCALATE — recurring USD 7,300 transfers, just below the
            # CNBV USD 7,500 Operación Relevante threshold (structuring / fraccionamiento)
            {
                "external_alert_id": "LIVE-UNDER-THRESH-015",
                "customer_id": "CUST-STRUCT-015",
                "is_pep": False,
                "amount": "7300.00",  # USD $7,300 — 97% of CNBV USD 7,500 threshold
                "currency": "USD",
                "transaction_date": now - timedelta(hours=3),
                "status": Alert.Status.PENDING,
                "xgboost_score": 0.83,
                "raw_payload": {
                    "source": "xgboost_v3",
                    "alert_type": "STRUCTURING_PATTERN",
                    "segment": "retail_individual",
                    "notes": "Fifth transfer this month of exactly USD 7,300 — systematically just below the CNBV Operación Relevante threshold of USD 7,500. Strong fraccionamiento indicator.",
                },
            },
            # ── Scenario 16 ────────────────────────────────────────────────────
            # Expected: ESCALATE — large USD wire to a FATF high-risk jurisdiction,
            # high xgboost score, no documented commercial purpose
            {
                "external_alert_id": "LIVE-INTL-WIRE-016",
                "customer_id": "CUST-WIRE-016",
                "is_pep": False,
                "amount": "34000.00",  # USD $34,000
                "currency": "USD",
                "transaction_date": now - timedelta(hours=9),
                "status": Alert.Status.PENDING,
                "xgboost_score": 0.81,
                "raw_payload": {
                    "source": "xgboost_v3",
                    "alert_type": "INTERNATIONAL_WIRE",
                    "segment": "retail_individual",
                    "notes": "Wire transfer to a jurisdiction listed by FATF as high-risk (non-cooperative). Customer has no documented trade relationships in that region.",
                },
            },
            # ── Scenario 17 ────────────────────────────────────────────────────
            # Expected: DISMISS — SME with consistent MXN activity, low xgboost,
            # amount well below CNBV MXN 127K threshold
            {
                "external_alert_id": "LIVE-SME-LOW-017",
                "customer_id": "CUST-SME-017",
                "is_pep": False,
                "amount": "9200.00",  # MXN $9,200 — 7.2% of CNBV threshold (~USD 541)
                "currency": "MXN",
                "transaction_date": now - timedelta(hours=6),
                "status": Alert.Status.PENDING,
                "xgboost_score": 0.33,
                "raw_payload": {
                    "source": "xgboost_v3",
                    "alert_type": "ROUTINE_CHECK",
                    "segment": "sme",
                    "notes": "Small routine MXN payment, consistent with SME operating expenses. Amount far below CNBV threshold.",
                },
            },
            # ── Scenario 18 ────────────────────────────────────────────────────
            # Expected: REQUEST_INFO — PEN 13,500 is above SBS threshold; combined
            # with recent identity-data changes, more KYC verification is needed
            {
                "external_alert_id": "LIVE-ID-CHANGE-018",
                "customer_id": "CUST-IDCHG-018",
                "is_pep": False,
                "amount": "13500.00",  # PEN 13,500 — 1.35x SBS threshold (~USD 3,649)
                "currency": "PEN",
                "transaction_date": now - timedelta(hours=14),
                "status": Alert.Status.PENDING,
                "xgboost_score": 0.55,
                "raw_payload": {
                    "source": "xgboost_v3",
                    "alert_type": "UNUSUAL_PATTERN",
                    "segment": "retail_individual",
                    "notes": "Address and phone number updated 12 days ago. Transaction is above SBS threshold. Updated KYC documents have not yet been validated.",
                },
            },
            # ── Scenario 19 ────────────────────────────────────────────────────
            # Expected: ESCALATE — MXN 195K (~USD 11,470) is 1.5x the CNBV
            # USD 7,500 Operación Relevante threshold, high xgboost
            {
                "external_alert_id": "LIVE-LARGE-MXN-019",
                "customer_id": "CUST-MXN-019",
                "is_pep": False,
                "amount": "195000.00",  # MXN $195,000 — ~USD 11,470, 1.5x CNBV threshold
                "currency": "MXN",
                "transaction_date": now - timedelta(hours=11),
                "status": Alert.Status.PENDING,
                "xgboost_score": 0.88,
                "raw_payload": {
                    "source": "xgboost_v3",
                    "alert_type": "HIGH_AMOUNT_TRANSFER",
                    "segment": "retail_individual",
                    "notes": "Single MXN wire significantly above the CNBV Operación Relevante threshold. No documented commercial justification on file.",
                },
            },
            # ── Scenario 20 ────────────────────────────────────────────────────
            # Expected: DISMISS — tiny inbound USD remittance, very low xgboost,
            # consistent with declared family remittance profile
            {
                "external_alert_id": "LIVE-REMITTANCE-020",
                "customer_id": "CUST-REM-020",
                "is_pep": False,
                "amount": "280.00",  # USD $280 — routine remittance
                "currency": "USD",
                "transaction_date": now - timedelta(hours=2),
                "status": Alert.Status.PENDING,
                "xgboost_score": 0.16,
                "raw_payload": {
                    "source": "xgboost_v3",
                    "alert_type": "ROUTINE_CHECK",
                    "segment": "retail_individual",
                    "notes": "Regular inbound family remittance. Customer declared remittance income in KYC. Pattern is fully consistent with profile.",
                },
            },
            # ── Scenario 21 ────────────────────────────────────────────────────
            # Expected: REQUEST_INFO — PEN 16K above SBS threshold, combined with
            # transactions clustered between 2-4am, warrants explanation
            {
                "external_alert_id": "LIVE-ODD-TIMING-021",
                "customer_id": "CUST-NIGHT-021",
                "is_pep": False,
                "amount": "16000.00",  # PEN 16,000 — 1.6x SBS threshold (~USD 4,324)
                "currency": "PEN",
                "transaction_date": now - timedelta(hours=20),
                "status": Alert.Status.PENDING,
                "xgboost_score": 0.63,
                "raw_payload": {
                    "source": "xgboost_v3",
                    "alert_type": "UNUSUAL_PATTERN",
                    "segment": "retail_individual",
                    "notes": "Four PEN transactions between 02:00 and 04:00 local time over the past 10 days, above SBS threshold. Customer has no night-shift or hospitality employment on record.",
                },
            },
            # ── Scenario 22 ────────────────────────────────────────────────────
            # Expected: ESCALATE — large USD transfer from an SME account whose
            # declared activity (local retail) does not justify international wires
            {
                "external_alert_id": "LIVE-LARGE-USD-022",
                "customer_id": "CUST-LARGE-022",
                "is_pep": False,
                "amount": "67000.00",  # USD $67,000
                "currency": "USD",
                "transaction_date": now - timedelta(hours=8),
                "status": Alert.Status.PENDING,
                "xgboost_score": 0.86,
                "raw_payload": {
                    "source": "xgboost_v3",
                    "alert_type": "HIGH_AMOUNT_TRANSFER",
                    "segment": "sme",
                    "notes": "USD $67K outbound wire. SME declared activity is local retail commerce — no documented import/export activity to justify this amount.",
                },
            },
            # ── Scenario 23 ────────────────────────────────────────────────────
            # Expected: ESCALATE — PEP hard-rule applies regardless of the small
            # PEN amount or moderate xgboost score
            {
                "external_alert_id": "LIVE-PEP-PEN-023",
                "customer_id": "CUST-PEP-023",
                "is_pep": True,
                "amount": "2800.00",  # PEN 2,800 — below SBS threshold, but PEP overrides
                "currency": "PEN",
                "transaction_date": now - timedelta(hours=3),
                "status": Alert.Status.PENDING,
                "xgboost_score": 0.38,
                "raw_payload": {
                    "source": "xgboost_v3",
                    "alert_type": "PEP_TRANSACTION",
                    "segment": "retail_individual",
                    "pep_category": "domestic_official",
                    "notes": "PEP flag active. Resolución SBS 789-2018 Art. 17 mandates human review for all PEP alerts regardless of amount.",
                },
            },
            # ── Scenario 24 ────────────────────────────────────────────────────
            # Expected: DISMISS — COP 3.2M is 32% of SARLAFT 10M threshold,
            # low xgboost, retail individual with clean profile
            {
                "external_alert_id": "LIVE-BELOW-COP-024",
                "customer_id": "CUST-LOW-024",
                "is_pep": False,
                "amount": "3200000.00",  # COP 3.2M — ~USD 780, 32% of SARLAFT threshold
                "currency": "COP",
                "transaction_date": now - timedelta(days=1),
                "status": Alert.Status.PENDING,
                "xgboost_score": 0.27,
                "raw_payload": {
                    "source": "xgboost_v3",
                    "alert_type": "ROUTINE_CHECK",
                    "segment": "retail_individual",
                    "notes": "COP 3.2M is well below the SARLAFT COP 10M threshold for natural persons. Consistent with monthly salary deposit pattern.",
                },
            },
            # ── Scenario 25 ────────────────────────────────────────────────────
            # Expected: REQUEST_INFO — corporate account with MXN activity
            # inconsistent with its registered business type; borderline xgboost
            {
                "external_alert_id": "LIVE-CORP-MED-025",
                "customer_id": "CUST-CORP-025",
                "is_pep": False,
                "amount": "62000.00",  # MXN $62,000 — ~USD 3,647, below CNBV threshold
                "currency": "MXN",
                "transaction_date": now - timedelta(hours=16),
                "status": Alert.Status.PENDING,
                "xgboost_score": 0.59,
                "raw_payload": {
                    "source": "xgboost_v3",
                    "alert_type": "UNUSUAL_PATTERN",
                    "segment": "corporate",
                    "entity_type": "SRL",
                    "notes": "Corporate SRL registered for software consulting. Receiving cash deposits inconsistent with B2B invoice payments typical for that business type.",
                },
            },
            # ── Scenario 26 ────────────────────────────────────────────────────
            # Expected: ESCALATE — rapid receipt and re-transfer of USD, high
            # xgboost, classic pass-through money-mule pattern
            {
                "external_alert_id": "LIVE-MULE-026",
                "customer_id": "CUST-MULE-026",
                "is_pep": False,
                "amount": "9600.00",  # USD $9,600 — above CNBV USD 7,500 threshold
                "currency": "USD",
                "transaction_date": now - timedelta(hours=6),
                "status": Alert.Status.PENDING,
                "xgboost_score": 0.84,
                "raw_payload": {
                    "source": "xgboost_v3",
                    "alert_type": "STRUCTURING_PATTERN",
                    "segment": "retail_individual",
                    "notes": "Funds received and re-transferred within 2 hours on three separate occasions. Account balance never exceeds USD 500 between cycles. Strong money-mule / pass-through indicator.",
                },
            },
            # ── Scenario 27 ────────────────────────────────────────────────────
            # Expected: DISMISS — tiny COP amount, extremely low xgboost, clearly
            # a low-value routine transaction
            {
                "external_alert_id": "LIVE-TINY-COP-027",
                "customer_id": "CUST-TINY-027",
                "is_pep": False,
                "amount": "480000.00",  # COP 480K — ~USD 117, 4.8% of SARLAFT threshold
                "currency": "COP",
                "transaction_date": now - timedelta(hours=1),
                "status": Alert.Status.PENDING,
                "xgboost_score": 0.11,
                "raw_payload": {
                    "source": "xgboost_v3",
                    "alert_type": "ROUTINE_CHECK",
                    "segment": "retail_individual",
                    "notes": "Low-value utility payment. Triggered only by daily count rule. No risk indicators.",
                },
            },
            # ── Scenario 28 ────────────────────────────────────────────────────
            # Expected: REQUEST_INFO — COP 21.5M is 2.15x the SARLAFT 10M threshold
            # and does not match the customer's declared annual income; xgboost is
            # borderline-high — needs income documentation before deciding
            {
                "external_alert_id": "LIVE-INCOME-GAP-028",
                "customer_id": "CUST-GAP-028",
                "is_pep": False,
                "amount": "21500000.00",  # COP 21.5M — ~USD 5,244, 2.15x SARLAFT threshold
                "currency": "COP",
                "transaction_date": now - timedelta(hours=18),
                "status": Alert.Status.PENDING,
                "xgboost_score": 0.67,
                "raw_payload": {
                    "source": "xgboost_v3",
                    "alert_type": "UNUSUAL_AMOUNT",
                    "segment": "retail_individual",
                    "notes": "Single deposit of COP 21.5M. Customer's declared annual income is COP 48M (~COP 4M/month). This single deposit represents 5 months of declared income. Income verification documents requested but not yet received.",
                },
            },
            # ── Scenario 29 (Edge Case) ────────────────────────────────────
            # Expected: ESCALATE — xgboost is near-maximum (0.97, CRITICAL band)
            # but amount is trivially small ($75 USD, far below any threshold).
            # This tests whether the system correctly prioritizes the ML model's
            # anomaly signal over amount-based heuristics. A naive system would
            # DISMISS because $75 is nothing; a robust system recognizes that
            # 0.97 xgboost is a screaming red flag — it may indicate a probe
            # transaction (criminals test with tiny amounts before large ones)
            # or synthetic identity fraud where the amount is irrelevant.
            {
                "external_alert_id": "LIVE-GHOST-PROBE-029",
                "customer_id": "CUST-PROBE-029",
                "is_pep": False,
                "amount": "75.00",  # USD $75 — far below any threshold
                "currency": "USD",
                "transaction_date": now - timedelta(hours=1),
                "status": Alert.Status.PENDING,
                "xgboost_score": 0.97,
                "raw_payload": {
                    "source": "xgboost_v3",
                    "alert_type": "ANOMALY_SCORE_CRITICAL",
                    "segment": "retail_individual",
                    "notes": "ML model flagged at 0.97 confidence despite trivial $75 USD amount. "
                    "Account was dormant for 11 months, then received 14 micro-transfers from "
                    "8 distinct originators in 48 hours — none individually suspicious, but the "
                    "burst pattern matches known synthetic-identity activation sequences. "
                    "Destination account was opened with minimal KYC (student visa holder, no "
                    "income documentation). No single transfer exceeds $100.",
                },
            },
            # ── Scenario 30 (Edge Case) ────────────────────────────────────
            # Expected: ESCALATE — PEP hard-rule must fire even when EVERY other
            # signal says DISMISS: near-zero amount (EUR 0.01), near-zero xgboost
            # (0.02), unsupported currency (EUR — no LATAM regulatory threshold),
            # verified KYC, zero prior alerts. This is the ultimate PEP invariant
            # test: the system must escalate purely because of the PEP flag,
            # regardless of how innocuous the transaction appears. If any code
            # path bypasses the PEP check (e.g., a "skip trivial" optimization),
            # this scenario catches it.
            {
                "external_alert_id": "LIVE-PEP-PHANTOM-030",
                "customer_id": "CUST-PEP-030",
                "is_pep": True,
                "amount": "0.01",  # EUR 0.01 — near-zero, unsupported currency
                "currency": "EUR",
                "transaction_date": now - timedelta(hours=2),
                "status": Alert.Status.PENDING,
                "xgboost_score": 0.02,
                "raw_payload": {
                    "source": "xgboost_v3",
                    "alert_type": "ROUTINE_CHECK",
                    "segment": "high_value_individual",
                    "notes": "EUR 0.01 cent transfer from a PEP-designated diplomat. Currency is EUR "
                    "(not in any LATAM regulatory threshold table). XGBoost score is 0.02 — "
                    "the model considers this transaction harmless. KYC is fully verified, "
                    "zero prior alerts. Every signal says DISMISS except the PEP flag. "
                    "Regulation mandates 100% human escalation for PEPs regardless of amount, "
                    "currency, or risk score.",
                },
            },
        ]
