# Compliance AI: Business Case
### For CFO Review — Xertica Financial Intelligence Platform

---

## Executive Summary

We propose deploying a multi-agent AI system to automate fraud alert triage, reducing resolution time from **4.2 hours to under 30 minutes** while cutting analyst cost per alert by 71%. The system maintains full regulatory compliance with UIAF, CNBV, and SBS requirements. Total implementation investment: **$60,940** over 8 weeks. Payback period: **~3.5 months** from project start.

---

## Cost Model

### Assumptions (explicit)

- **Analyst salary:** $6,000/month base salary per compliance analyst. The "fully loaded" cost (salary + benefits + office + equipment + management overhead) is typically **1.3–1.5× base** in Latin America. We use a 1.0× multiplier here for a conservative estimate — the actual savings will be higher.
- **Alert volume:** 2,000 alerts/month, derived from the problem statement (XGBoost model generates the initial alerts; 68% are false positives).
- **Analyst capacity:** Each analyst works ~160 hours/month (8h × 20 business days). At 4.2 hours per alert, one analyst resolves ~38 alerts/month. To handle 2,000 alerts: `2,000 ÷ 38 ≈ 53 analyst-months` needed — but analysts aren't 100% utilized on alert resolution (they also do reporting, training, meetings). At ~60% utilization on alerts: `53 ÷ 0.60 ≈ 8 analysts`. That's how we get 8 FTEs.
- **Senior analyst salary:** $6,000/month — same level but fewer people. These 2 analysts handle only the escalated alerts (high-risk + PEP) that the AI flags for human review, plus system oversight.
- **Developer rate:** $10,000/month per senior engineer (market rate for compliance-domain Python/ML engineers in LATAM). One lead + one support engineer for 8 weeks.
- **AI coding tools:** $200/month per developer seat (e.g., Claude Code or equivalent). Included as a recurring operational cost once the system is in maintenance mode (1 dev seat). During the build phase, 2 seats for 2 months.
- **Build timeline:** 8 weeks total — 6 weeks active development (3 agents + RAG + API + infra) + 2 weeks integration testing and compliance sign-off.

### Current State (Manual)
| Item | Calculation | Monthly |
|------|-------------|---------|
| 8 compliance analysts | 8 analysts × $6,000/month | $48,000 |
| Alert volume | 2,000 alerts/month | — |
| **Cost per alert** | **$48,000 ÷ 2,000 alerts** | **$24.00** |
| Average resolution time | — | 4.2 hours |

**What "cost per alert" means:** It's the total monthly spend on compliance operations divided by the number of alerts processed that month. It captures *everything* it costs the organization to resolve one alert — analyst time, whether the alert is a false positive or not. Currently, every alert costs $24 to process because a human must review it from scratch, even the 68% that turn out to be false positives.

### Proposed State (AI-Assisted) — Recurring Monthly Costs
| Item | Calculation | Monthly |
|------|-------------|---------|
| 2 senior analysts (escalations only) | 2 × $6,000/month | $12,000 |
| GCP infrastructure | Cloud Run + Cloud SQL (PostgreSQL + pgvector) + networking | $1,800 |
| LLM cost (Gemini Flash) | ~$0.003/alert × 2,000 alerts (see below) | $6 |
| Langfuse observability | Hosted plan, <10K traces/month | $200 |
| AI coding tools (maintenance) | 1 dev seat × $200/month (Claude Code) | $200 |
| **Total recurring** | | **$14,206** |
| **Cost per alert** | **$14,206 ÷ 2,000 alerts** | **$7.10** |

**How \$0.003/alert is calculated:** Each alert triggers three LLM calls — one per agent (Investigador, Risk Analyzer, Decision Agent). At Gemini 2.0 Flash pricing (\$0.000075/1K input tokens, \$0.0003/1K output tokens), a typical call uses ~2K input + ~1K output tokens: `(2 × $0.000075) + (1 × $0.0003) = $0.00045` per call × 3 calls ≈ **\$0.0014/alert**. Rounding up to \$0.003 accounts for longer prompts on complex cases. PEP alerts cost even less — the Decision Agent skips the LLM entirely (deterministic hard-rule), so only 2 LLM calls occur.

---

### Implementation Cost (One-Time)
| Item | Calculation | One-Time Cost |
|------|-------------|---------------|
| Lead developer (8 weeks) | 2 months × $10,000/month | $20,000 |
| Support developer (8 weeks) | 2 months × $8,000/month | $16,000 |
| AI coding tools during build | 2 developers × $200/month × 2 months | $800 |
| GCP setup + staging environment | 2 months of infra while building | $3,600 |
| Compliance review + legal sign-off | External compliance consultant, flat fee | $15,000 |
| Integration testing + QA | Included in dev time above | $0 |
| Contingency (10%) | 10% of subtotal $55,400 | $5,540 |
| **Total implementation** | | **$60,940** |

> **What these costs mean:**
> - **Lead developer:** The engineer who designs and builds the system — agents, RAG pipeline, API, infrastructure. Senior-level because compliance systems require domain judgment, not just code.
> - **Support developer:** Handles infrastructure (Terraform, CI/CD), tests, and integration work in parallel so the build doesn't serialize.
> - **AI coding tools (\$800):** Both developers use Claude Code (\$200/seat/month) during the 8-week build. This accelerates delivery — the build timeline is 8 weeks *because* of AI-assisted development; without it, estimate 14–16 weeks and ~$35,000 more in developer time.
> - **Compliance review ($15,000):** A qualified compliance consultant (not the dev team) reviews the system against UIAF, CNBV, and SBS requirements before go-live. Non-negotiable — the system makes regulatory decisions.
> - **Contingency (10%):** Standard engineering project buffer for scope creep, integration surprises, and regulatory feedback requiring rework.

---

## ROI Projection

| Metric | Before | After | Delta |
|--------|--------|-------|-------|
| Resolution time | 4.2 hrs | 28 min | -89% |
| Cost per alert | $24.00 | $7.10 | -70% |
| Analyst headcount | 8 | 2 | -6 FTE |
| False positive rate | ~35% | ~18% (est.) | -49% |
| Regulatory SLA breaches | 3–5/month | <1/month | -80% |

**Monthly savings: \$33,794 | Annual savings: \$405,528**

**Break-even calculation:**
- Implementation cost: **$60,940** (one-time)
- Monthly savings after go-live: **$33,794**
- Break-even: \$60,940 ÷ \$33,794 = **~1.8 months after launch** (month 3-4 from project start)

---

## Primary Risk & Mitigation

**Risk: AI sub-escalation of PEP alerts**
Regulatory requirement mandates 100% human review of Politically Exposed Persons. An LLM-based system could incorrectly dismiss these, creating regulatory liability of up to $2M per incident (CNBV).

**Mitigation:**
1. PEP escalation is enforced as deterministic code, not LLM judgment. The AI cannot dismiss a PEP alert under any circumstances.
2. A synthetic PEP canary alert runs daily in production to verify the invariant.
3. Every decision stores `is_pep_override_applied` for external auditor inspection.
4. Real-time monitoring alerts if PEP escalation rate drops below 100%.

This is a defense-in-depth approach: three independent safety layers prevent the highest-consequence failure mode.
