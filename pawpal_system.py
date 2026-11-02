"""PawPal+ core domain model.

Class skeleton generated from diagrams/uml_draft.mmd. Attributes and method
signatures only — the scheduling logic goes in next.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CareTask:
    """One thing the owner needs to do for a pet (walk, feeding, meds, ...)."""

    title: str
    duration_minutes: int
    priority: str
    start_time: str = ""

    def weight(self) -> float:
        """Score used to rank this task against the others when planning."""
        raise NotImplementedError


@dataclass
class Pet:
    """A pet and the care tasks that belong to it."""

    name: str
    species: str
    age_years: int
    tasks: list[CareTask] = field(default_factory=list)

    def add_task(self, task: CareTask) -> None:
        """Attach a care task to this pet."""
        raise NotImplementedError


@dataclass
class Owner:
    """The person doing the care, plus the time budget they have today."""

    name: str
    start_time: str
    available_minutes: int
    pets: list[Pet] = field(default_factory=list)

    def add_pet(self, pet: Pet) -> None:
        """Register a pet under this owner."""
        raise NotImplementedError


@dataclass
class DailyPlan:
    """The schedule built for one pet: what fit, what didn't."""

    pet: Pet
    entries: list[CareTask] = field(default_factory=list)
    skipped: list[CareTask] = field(default_factory=list)

    @staticmethod
    def build(owner: Owner, pet: Pet) -> "DailyPlan":
        """Select, order, and time-stamp the pet's tasks within the owner's budget."""
        raise NotImplementedError

    def explain(self) -> str:
        """Human-readable reasoning for why the plan looks the way it does."""
        raise NotImplementedError

    def to_table(self) -> list[dict]:
        """Flatten the scheduled entries into rows for st.table / st.dataframe."""
        raise NotImplementedError
