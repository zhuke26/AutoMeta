from dataclasses import dataclass, field


@dataclass(frozen=True)
class StudyEstimate:
    effect: float
    variance: float
    study_label: str = ""
    year: str | None = None
    title: str | None = None
    outcome: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)

    @property
    def standard_error(self) -> float:
        return self.variance ** 0.5
