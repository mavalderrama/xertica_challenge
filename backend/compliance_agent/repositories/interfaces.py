from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from compliance_agent.models import (
        Alert,
        AuditLog,
        Decision,
        Investigation,
        RiskAnalysis,
    )


class IAlertRepository(ABC):
    @abstractmethod
    async def get_by_id(self, alert_id: UUID) -> Alert:
        pass

    @abstractmethod
    async def get_by_external_id(self, external_id: str) -> Alert:
        pass

    @abstractmethod
    async def save(self, alert: Alert) -> Alert:
        pass

    @abstractmethod
    async def update_status(self, alert_id: UUID, status: str) -> Alert:
        pass


class IInvestigationRepository(ABC):
    @abstractmethod
    async def get_by_alert_id(self, alert_id: UUID) -> Investigation:
        pass

    @abstractmethod
    async def get_by_id(self, investigation_id: UUID) -> Investigation:
        pass

    @abstractmethod
    async def save(self, investigation: Investigation) -> Investigation:
        pass


class IRiskAnalysisRepository(ABC):
    @abstractmethod
    async def get_by_investigation_id(self, investigation_id: UUID) -> RiskAnalysis:
        pass

    @abstractmethod
    async def get_by_id(self, id: UUID) -> RiskAnalysis:
        pass

    @abstractmethod
    async def save(self, risk_analysis: RiskAnalysis) -> RiskAnalysis:
        pass


class IDecisionRepository(ABC):
    @abstractmethod
    async def get_by_risk_analysis_id(self, risk_analysis_id: UUID) -> Decision:
        pass

    @abstractmethod
    async def save(self, decision: Decision) -> Decision:
        pass


class IAuditLogRepository(ABC):
    @abstractmethod
    async def create(self, **kwargs) -> AuditLog:
        pass

    @abstractmethod
    async def get_by_alert_id(self, alert_id: UUID) -> list[AuditLog]:
        pass
