"""PawPal+ core domain model and scheduling brain.

Four classes carry the system:

* ``CareTask`` — one activity: what it is, how long it takes, when the owner
  wants it, how often it repeats, and whether it is done yet.
* ``Pet`` — the pet's details plus the care tasks that belong to it.
* ``Owner`` — the person doing the care: their pets, the windows they are free,
  and :meth:`Owner.get_all_tasks`, which hands back every pet's tasks together.
* ``Scheduler`` — the brain. It reads the owner's *whole* task list via
  :meth:`Owner.get_all_tasks`, ranks it, and places it in the owner's free
  windows. It deliberately never reads ``pet.tasks`` directly: the owner's free
  time is one shared budget, so planning has to happen at the owner level or the
  same minutes get spent once per pet.

``TimeSlot``, ``PlanEntry`` and ``DailyPlan`` are the supporting value types.
Design diagram: ``diagrams/uml_draft.mmd``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: Higher rank wins when two tasks compete for the same minutes.
PRIORITY_RANK = {"high": 3, "medium": 2, "low": 1}

#: Accepted values for ``CareTask.frequency``.
FREQUENCIES = ("daily", "weekly", "once")


def _to_minutes(clock: str) -> int | None:
    """Parse ``"HH:MM"`` into minutes past midnight, or ``None`` if malformed."""
    if not isinstance(clock, str):
        return None
    hours, sep, mins = clock.strip().partition(":")
    if not sep:
        return None
    try:
        hour, minute = int(hours), int(mins)
    except ValueError:
        return None
    if not (0 <= hour < 24 and 0 <= minute < 60):
        return None
    return hour * 60 + minute


def _to_clock(minutes: int) -> str:
    """Format minutes past midnight back into ``"HH:MM"``."""
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


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
        """Length of this window in minutes (0 if the times are unusable)."""
        start = _to_minutes(self.start_time)
        end = _to_minutes(self.end_time)
        if start is None or end is None or end <= start:
            return 0
        return end - start


@dataclass
class CareTask:
    """One thing the owner needs to do for a pet (walk, feeding, meds, ...).

    This is a reusable template owned by the pet, not a scheduling result.
    ``start_time`` is an *input*: a time the owner requests for this task
    ("meds at 08:00"). Blank means "anywhere the scheduler can fit it".
    The time a task actually lands on is recorded on ``PlanEntry``.

    ``frequency`` is one of ``FREQUENCIES``. A ``"weekly"`` task may name the
    ``day_of_week`` it belongs on; left blank, it is treated as due any day.
    ``completed`` is the task's own state — the scheduler leaves finished tasks
    out of the plan instead of booking the owner's time twice.
    """

    title: str
    duration_minutes: int
    priority: str
    start_time: str = ""
    frequency: str = "daily"
    day_of_week: str = ""
    completed: bool = False
    #: Back-reference, set by :meth:`Pet.add_task`, so a task carries its pet
    #: around once the scheduler has flattened every pet's list into one.
    #: Excluded from ``__eq__``/``__repr__`` to keep the cycle Pet <-> CareTask
    #: from recursing.
    pet: "Pet | None" = field(default=None, repr=False, compare=False)

    def is_pinned(self) -> bool:
        """True if the owner requested a specific start time for this task."""
        return _to_minutes(self.start_time) is not None

    def rank(self) -> int:
        """Numeric priority. An unrecognised priority is treated as low."""
        return PRIORITY_RANK.get(str(self.priority).strip().lower(), 1)

    def weight(self) -> float:
        """Score used to rank this task against the others when planning.

        Priority dominates; duration breaks ties in favour of shorter tasks so
        more of the day's care fits:

            PRIORITY_RANK[priority] * 100 - duration_minutes

        Higher scores are scheduled first.
        """
        return self.rank() * 100 - self.duration_minutes

    def is_due(self, weekday: str | None = None) -> bool:
        """Whether this task belongs in the plan for ``weekday``.

        Daily and one-off tasks are due whenever asked. A weekly task is due
        only on its ``day_of_week`` — unless it names no day, or no day was
        asked about, in which case it is due.
        """
        if str(self.frequency).strip().lower() != "weekly":
            return True
        if not self.day_of_week.strip() or weekday is None:
            return True
        return self.day_of_week.strip().lower() == str(weekday).strip().lower()

    def mark_complete(self) -> None:
        """Record that this task has been done."""
        self.completed = True

    def reopen(self) -> None:
        """Undo :meth:`mark_complete` — e.g. at the start of the next day."""
        self.completed = False

    def pet_name(self) -> str:
        """Name of the pet this task belongs to, or ``""`` if unattached."""
        return self.pet.name if self.pet is not None else ""


#: The brief calls this class "Task"; the model keeps the more specific name.
Task = CareTask


@dataclass
class Pet:
    """A pet and the care tasks that belong to it."""

    name: str
    species: str
    age_years: int
    tasks: list[CareTask] = field(default_factory=list)

    def add_task(self, task: CareTask) -> None:
        """Attach a care task to this pet (idempotent).

        Membership is tested by identity, not equality: two tasks can legitimately
        look alike ("Feeding, 10 min, high" twice in a day) and both belong.
        """
        task.pet = self
        if not any(existing is task for existing in self.tasks):
            self.tasks.append(task)

    def remove_task(self, task: CareTask) -> None:
        """Detach a care task. Unknown tasks are ignored."""
        for index, existing in enumerate(self.tasks):
            if existing is task:
                del self.tasks[index]
                if task.pet is self:
                    task.pet = None
                return

    def pending_tasks(self) -> list[CareTask]:
        """This pet's tasks that are not finished yet."""
        return [task for task in self.tasks if not task.completed]


@dataclass
class Owner:
    """The person doing the care, plus the windows they are free today."""

    name: str
    available_timeslots: list[TimeSlot] = field(default_factory=list)
    pets: list[Pet] = field(default_factory=list)

    def add_pet(self, pet: Pet) -> None:
        """Register a pet under this owner (idempotent, by identity)."""
        if not any(existing is pet for existing in self.pets):
            self.pets.append(pet)

    def remove_pet(self, pet: Pet) -> None:
        """Unregister a pet (and, with it, that pet's tasks)."""
        for index, existing in enumerate(self.pets):
            if existing is pet:
                del self.pets[index]
                return

    def total_available_minutes(self) -> int:
        """Sum of every free window — the day's whole care budget."""
        return sum(slot.minutes() for slot in self.available_timeslots)

    def get_all_tasks(self) -> list[CareTask]:
        """Every pet's tasks, flattened into one list in pet order.

        This is the single door the ``Scheduler`` goes through. Returning the
        owner's whole workload here — rather than letting the scheduler walk
        ``pet.tasks`` itself — is what keeps the plan multi-pet: one list, one
        ranking, one shared time budget.

        The pet back-reference on each task is refreshed on the way out, so a
        task appended straight to ``pet.tasks`` (bypassing ``Pet.add_task``)
        still knows which pet it belongs to.
        """
        all_tasks: list[CareTask] = []
        for pet in self.pets:
            for task in pet.tasks:
                task.pet = pet
                all_tasks.append(task)
        return all_tasks

    def get_pending_tasks(self) -> list[CareTask]:
        """Every pet's unfinished tasks."""
        return [task for task in self.get_all_tasks() if not task.completed]


@dataclass
class PlanEntry:
    """One task placed (or rejected) in the owner's day.

    Carries the scheduling results — which pet, what time it landed, and why —
    so that building a plan never mutates the pet's own ``CareTask`` objects.
    An entry in ``DailyPlan.skipped`` has an empty ``start_time`` and a
    ``reason`` explaining what went wrong.
    """

    pet: "Pet | None"
    task: CareTask
    start_time: str = ""
    slot_label: str = ""
    reason: str = ""

    def end_time(self) -> str:
        """When this entry finishes, or ``""`` if it was never placed."""
        start = _to_minutes(self.start_time)
        if start is None:
            return ""
        return _to_clock(start + self.task.duration_minutes)

    def describe(self) -> str:
        """One-line summary used by :meth:`DailyPlan.explain`."""
        who = self.pet.name if self.pet is not None else "unassigned"
        return (
            f"{who} · {self.task.title} "
            f"({self.task.duration_minutes} min, {self.task.priority})"
        )


@dataclass
class Scheduler:
    """The brain: turns an owner's whole task list into a timed daily plan.

    The scheduler holds an ``Owner``, never a single ``Pet``. Every read of the
    work to be done goes through :meth:`Owner.get_all_tasks`, so adding a second
    pet changes the plan without changing the scheduler.

    Placement runs in two passes:

    1. **Pinned tasks** (the owner asked for a specific ``start_time``) are
       placed first, earliest request first, so explicit wishes win over scores.
    2. **Flexible tasks** are sorted by :meth:`CareTask.weight` and dropped into
       the earliest free window that still has room.

    Anything that cannot be placed lands in ``DailyPlan.skipped`` with a reason.
    """

    owner: Owner

    # -- retrieval ---------------------------------------------------------

    def get_all_tasks(self) -> list[CareTask]:
        """Every task across every pet — read straight from the owner."""
        return self.owner.get_all_tasks()

    def pending_tasks(self, weekday: str | None = None) -> list[CareTask]:
        """Unfinished tasks that are due on ``weekday``."""
        return [
            task
            for task in self.get_all_tasks()
            if not task.completed and task.is_due(weekday)
        ]

    def ranked_tasks(self, weekday: str | None = None) -> list[CareTask]:
        """Due tasks in the order the scheduler would try to place them."""
        return sorted(
            self.pending_tasks(weekday),
            key=lambda task: (not task.is_pinned(), -task.weight(), task.title),
        )

    def tasks_for(self, pet: Pet) -> list[CareTask]:
        """One pet's slice of the owner's task list (for display, not planning)."""
        return [task for task in self.get_all_tasks() if task.pet is pet]

    # -- management --------------------------------------------------------

    def add_task(self, pet: Pet, task: CareTask) -> CareTask:
        """Give a pet a new task, registering the pet with the owner if needed."""
        self.owner.add_pet(pet)
        pet.add_task(task)
        return task

    def complete_task(self, task: CareTask) -> None:
        """Mark a task done so later plans leave it out."""
        task.mark_complete()

    def reset_day(self) -> None:
        """Reopen every task — the start of a new day."""
        for task in self.get_all_tasks():
            task.reopen()

    # -- planning ----------------------------------------------------------

    def build_plan(self, weekday: str | None = None) -> "DailyPlan":
        """Select, order, and time-stamp every pet's tasks within the owner's windows."""
        plan = DailyPlan(owner=self.owner)
        windows = self._windows()
        free = [list(window) for window in windows]

        pinned: list[CareTask] = []
        flexible: list[CareTask] = []
        for task in self.get_all_tasks():
            if task.completed:
                plan.skipped.append(self._reject(task, "already done today"))
            elif not task.is_due(weekday):
                plan.skipped.append(
                    self._reject(task, f"{task.frequency} task, not due on {weekday}")
                )
            elif task.duration_minutes <= 0:
                plan.skipped.append(
                    self._reject(task, "duration must be at least 1 minute")
                )
            elif task.is_pinned():
                pinned.append(task)
            else:
                flexible.append(task)

        # Pass 1: honour requested times, earliest request first.
        for task in sorted(pinned, key=lambda t: _to_minutes(t.start_time) or 0):
            start = _to_minutes(task.start_time)
            index = self._fit_at(free, start, task.duration_minutes)
            if index is None:
                plan.skipped.append(self._reject(task, self._why_pin_failed(windows, task)))
                continue
            label = free[index][0]
            self._consume(free, index, start, task.duration_minutes)
            plan.entries.append(
                PlanEntry(
                    pet=task.pet,
                    task=task,
                    start_time=_to_clock(start),
                    slot_label=label,
                    reason=f"owner asked for {task.start_time}",
                )
            )

        # Pass 2: everything else, best score first, into the earliest opening.
        for task in sorted(flexible, key=lambda t: (-t.weight(), t.title)):
            index = self._first_fit(free, task.duration_minutes)
            if index is None:
                plan.skipped.append(
                    self._reject(
                        task,
                        f"no window had {task.duration_minutes} free minutes left",
                    )
                )
                continue
            label, start, _ = free[index]
            self._consume(free, index, start, task.duration_minutes)
            plan.entries.append(
                PlanEntry(
                    pet=task.pet,
                    task=task,
                    start_time=_to_clock(start),
                    slot_label=label,
                    reason=(
                        f"{task.priority} priority (score {task.weight():.0f}), "
                        "earliest window with room"
                    ),
                )
            )

        plan.entries.sort(key=lambda entry: _to_minutes(entry.start_time) or 0)
        return plan

    # -- internals ---------------------------------------------------------

    def _windows(self) -> list[list]:
        """Usable free windows as ``[label, start_min, end_min]``, sorted.

        Unparseable or empty slots are dropped, and overlapping slots are
        trimmed so the same minute is never offered twice.
        """
        windows: list[list] = []
        for slot in self.owner.available_timeslots:
            start = _to_minutes(slot.start_time)
            end = _to_minutes(slot.end_time)
            if start is None or end is None or end <= start:
                continue
            windows.append([slot.label or f"{slot.start_time}-{slot.end_time}", start, end])
        windows.sort(key=lambda window: window[1])

        trimmed: list[list] = []
        for label, start, end in windows:
            if trimmed and start < trimmed[-1][2]:
                start = trimmed[-1][2]
                if start >= end:
                    continue
            trimmed.append([label, start, end])
        return trimmed

    @staticmethod
    def _fit_at(free: list[list], start: int, duration: int) -> int | None:
        """Index of the free interval that fully contains ``[start, start+duration)``."""
        end = start + duration
        for index, (_, lo, hi) in enumerate(free):
            if lo <= start and end <= hi:
                return index
        return None

    @staticmethod
    def _first_fit(free: list[list], duration: int) -> int | None:
        """Index of the earliest free interval with room for ``duration``."""
        for index, (_, lo, hi) in enumerate(free):
            if hi - lo >= duration:
                return index
        return None

    @staticmethod
    def _consume(free: list[list], index: int, start: int, duration: int) -> None:
        """Book ``[start, start+duration)`` out of ``free[index]``."""
        label, lo, hi = free[index]
        end = start + duration
        leftovers = []
        if start > lo:
            leftovers.append([label, lo, start])
        if end < hi:
            leftovers.append([label, end, hi])
        free[index : index + 1] = leftovers

    @staticmethod
    def _reject(task: CareTask, reason: str) -> PlanEntry:
        return PlanEntry(pet=task.pet, task=task, reason=reason)

    @staticmethod
    def _why_pin_failed(windows: list[list], task: CareTask) -> str:
        """Explain a pinned task that would not go in."""
        start = _to_minutes(task.start_time)
        end = start + task.duration_minutes
        inside = any(lo <= start and end <= hi for _, lo, hi in windows)
        if inside:
            return f"requested {task.start_time} collides with an earlier task"
        return f"requested {task.start_time} falls outside every free window"


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
    def build(owner: Owner, weekday: str | None = None) -> "DailyPlan":
        """Convenience wrapper around :meth:`Scheduler.build_plan`."""
        return Scheduler(owner).build_plan(weekday)

    def scheduled_minutes(self) -> int:
        """Minutes of care actually booked."""
        return sum(entry.task.duration_minutes for entry in self.entries)

    def unused_minutes(self) -> int:
        """Free minutes the plan did not spend."""
        return self.owner.total_available_minutes() - self.scheduled_minutes()

    def explain(self) -> str:
        """Human-readable reasoning for why the plan looks the way it does."""
        budget = self.owner.total_available_minutes()
        pets = len(self.owner.pets)
        lines = [
            f"Daily plan for {self.owner.name} — {pets} pet(s), "
            f"{len(self.entries) + len(self.skipped)} task(s) considered, "
            f"{budget} min of free time.",
            "",
        ]

        if self.entries:
            lines.append(f"Scheduled ({len(self.entries)}):")
            for entry in self.entries:
                lines.append(
                    f"  {entry.start_time}-{entry.end_time()}  {entry.describe()}"
                    f" in {entry.slot_label} — {entry.reason}"
                )
        else:
            lines.append("Scheduled (0): nothing fit in the owner's free time.")

        if self.skipped:
            lines.append("")
            lines.append(f"Skipped ({len(self.skipped)}):")
            for entry in self.skipped:
                lines.append(f"  {entry.describe()} — {entry.reason}")

        lines.append("")
        lines.append(
            f"{self.scheduled_minutes()} of {budget} free minutes used; "
            f"{self.unused_minutes()} left over."
        )
        return "\n".join(lines)

    def to_table(self) -> list[dict]:
        """Flatten the scheduled entries into rows for st.table / st.dataframe."""
        return [
            {
                "Time": f"{entry.start_time}-{entry.end_time()}",
                "Pet": entry.pet.name if entry.pet is not None else "",
                "Task": entry.task.title,
                "Minutes": entry.task.duration_minutes,
                "Priority": entry.task.priority,
                "Frequency": entry.task.frequency,
                "Window": entry.slot_label,
                "Why": entry.reason,
            }
            for entry in self.entries
        ]

    def skipped_table(self) -> list[dict]:
        """Rows for the tasks that did not make it into the day."""
        return [
            {
                "Pet": entry.pet.name if entry.pet is not None else "",
                "Task": entry.task.title,
                "Minutes": entry.task.duration_minutes,
                "Priority": entry.task.priority,
                "Reason": entry.reason,
            }
            for entry in self.skipped
        ]
