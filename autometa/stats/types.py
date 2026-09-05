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
        return self.variance**0.5


@dataclass(frozen=True)
class PoolingResult:
    model_used: str
    effect: float
    standard_error: float
    ci_lower: float
    ci_upper: float
    q: float
    q_p_value: float | None
    i2_percent: float
    tau2: float
    tau: float
    weights: tuple[float, ...]
    prediction_lower: float | None = None
    prediction_upper: float | None = None


@dataclass(frozen=True)
class InfluenceResult:
    omitted_study: str
    pool: PoolingResult


@dataclass(frozen=True)
class SubgroupPool:
    label: str
    study_count: int
    pool: PoolingResult


@dataclass(frozen=True)
class SubgroupResult:
    groups: tuple[SubgroupPool, ...]
    between_group_q: float
    between_group_df: int
    between_group_p_value: float
