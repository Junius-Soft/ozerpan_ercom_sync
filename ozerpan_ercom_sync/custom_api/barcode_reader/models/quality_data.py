from dataclasses import dataclass
from enum import Enum
from typing import List, Optional


class QualitySeverity(Enum):
    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"


@dataclass
class QualityCriterion:
    id: str
    name: str
    passed: bool
    notes: Optional[str]
    severity: str


@dataclass
class CorrectionOperation:
    operation: str
    reason: str
    priority: int
    description: str


@dataclass
class QualityData:
    criteria: List[QualityCriterion]
    overall_notes: Optional[str]
    required_operations: Optional[List[CorrectionOperation]] = None

    def has_failures(self) -> bool:
        return any(not criterion.get("passed") for criterion in self.criteria)
