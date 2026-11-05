"""PawPal+ core domain model.

Class skeleton generated from diagrams/uml_draft.mmd. Attributes and method
signatures only — the scheduling logic goes in next.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: Higher rank wins when two tasks compete for the same minutes.
PRIORITY_RANK = {"high": 3, "medium": 2, "low": 1}


@dataclass
class TimeSlot:
    """One window during the day when the owner is actually free.

    The owner's availability is a list of these rather than a single block,
    because a real day looks like 07:00-08:00 and 18:00-19:30, not one
    uninterrupted stretch.
    """

    label: str
    start_time: str
    end_time: str

    def minutes(self) -> int:
        """Length of this window in minutes."""
        raise NotImplementedError


@dataclass
class CareTask:
    """One thing the owner needs to do for a pet (walk, feeding, meds, ...).

    This is a reusable template owned by the pet, not a scheduling result.
    ``start_time`` is an *input*: a time the owner requests for this task
    ("meds at 08:00"). Blank means "anywhere the scheduler can fit it".
    The time a task actually lands on is recorded on ``PlanEntry``.
    """

    title: str
    duration_minutes: int
    priority: str
    start_time: str = ""

    def is_pinned(self) -> bool:
        """True if the owner requested a specific start time for this task."""
        raise NotImplementedError

    def weight(self) -> float:
        """Score used to rank this task against the others when planning.

        Priority dominates; duration breaks ties in favour of shorter tasks so
        more of the day's care fits:

            PRIORITY_RANK[priority] * 100 - duration_minutes

        Higher scores are scheduled first.
        """
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
    """The person doing the care, plus the windows they are free today."""

    name: str
    available_timeslots: list[TimeSlot] = field(default_factory=list)
    pets: list[Pet] = field(default_factory=list)

    def add_pet(self, pet: Pet) -> None:
        """Register a pet under this owner."""
        raise NotImplementedError

    def remove_pet(self, pet: Pet) -> None:
        """Unregister a pet (and, with it, that pet's tasks)."""
        raise NotImplementedError

    def total_available_minutes(self) -> int:
        """Sum of every free window — the day's whole care budget."""
        raise NotImplementedError


@dataclass
class PlanEntry:
    """One task placed (or rejected) in the owner's day.

    Carries the scheduling results — which pet, what time it landed, and why —
    so that building a plan never mutates the pet's own ``CareTask`` objects.
    An entry in ``DailyPlan.skipped`` has an empty ``start_time`` and a
    ``reason`` explaining what went wrong.
    """

    pet: Pet
    task: CareTask
    start_time: str = ""
    slot_label: str = ""
    reason: str = ""


@dataclass
class DailyPlan:
    """The schedule built for one owner's whole day, across all their pets.

    The owner's free time is a single shared budget, so the plan has to be
    owner-level: planning each pet separately would spend the same minutes
    twice and double-book the owner.
    """

    owner: Owner
    entries: list[PlanEntry] = field(default_factory=list)
    skipped: list[PlanEntry] = field(default_factory=list)

    @staticmethod
    def build(owner: Owner) -> "DailyPlan":
        """Select, order, and time-stamp every pet's tasks within the owner's windows.

        Pinned tasks are placed first at their requested time; the rest are
        taken in descending ``CareTask.weight()`` order and placed in the
        earliest window with room. Anything that does not fit — or whose
        requested time collides or falls outside every window — is recorded in
        ``skipped`` with a reason.
        """
        raise NotImplementedError

    def explain(self) -> str:
        """Human-readable reasoning for why the plan looks the way it does."""
        raise NotImplementedError

    def to_table(self) -> list[dict]:
        """Flatten the scheduled entries into rows for st.table / st.dataframe."""
        raise NotImplementedError
