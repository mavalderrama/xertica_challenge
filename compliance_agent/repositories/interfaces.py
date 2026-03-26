from abc import ABC, abstractmethod
from typing import Any
from uuid import UUID


class IAlertRepository(ABC):
    @abstractmethod
    def get_by_id(self, alert_id: UUID) -> Any:
        pass

    @abstractmethod
    def get_by_external_id(self, external_id: str) -> Any:
        pass

    @abstractmethod
    def save(self, alert: Any) -> Any:
        pass

    @abstractmethod
    def update_status(self, alert_id: UUID, status: str) -> Any:
        pass


class IInvestigationRepository(ABC):
    @abstractmethod
    def get_by_alert_id(self, alert_id: UUID) -> Any:
        pass

    @abstractmethod
    def save(self, investigation: Any) -> Any:
        pass


class IRiskAnalysisRepository(ABC):
    @abstractmethod
    def get_by_investigation_id(self, investigation_id: UUID) -> Any:
        pass

    @abstractmethod
    def save(self, risk_analysis: Any) -> Any:
        pass


class IDecisionRepository(ABC):
    @abstractmethod
    def get_by_risk_analysis_id(self, risk_analysis_id: UUID) -> Any:
        pass

    @abstractmethod
    def save(self, decision: Any) -> Any:
        pass


class IAuditLogRepository(ABC):
    @abstractmethod
    def create(self, **kwargs: Any) -> Any:
        pass

    @abstractmethod
    def get_by_alert_id(self, alert_id: UUID) -> list[Any]:
        pass
