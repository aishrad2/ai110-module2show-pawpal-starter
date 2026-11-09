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
Design diagram: ``diagrams/uml_final.mmd`` (``uml_draft.mmd`` is the Phase 1
sketch, kept for comparison).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date, timedelta

#: Higher rank wins when two tasks compete for the same minutes.
PRIORITY_RANK = {"high": 3, "medium": 2, "low": 1}

#: Accepted values for ``CareTask.frequency``.
FREQUENCIES = ("daily", "weekly", "once")

#: How far ahead each recurring frequency repeats. ``timedelta`` is used rather
#: than hand-rolled arithmetic because it is calendar-aware: adding 1 day to
#: 2026-02-28 gives 2026-02-29 in a leap year and 2026-03-01 otherwise, and
#: adding 7 days rolls month and year boundaries for free. A ``"once"`` task has
#: no entry here — it simply never repeats.
REPEAT_AFTER = {
    "daily": timedelta(days=1),
    "weekly": timedelta(days=7),
}


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

    ``due_date`` is the calendar day this particular instance is for. Leaving it
    ``None`` means "no date constraint" — the task is due whenever it is asked
    about, which is how every task behaved before recurrence existed. Once a
    date is set, finishing a recurring task spawns the next instance through
    :meth:`create_next_occurrence`.
    """

    title: str
    duration_minutes: int
    priority: str
    start_time: str = ""
    frequency: str = "daily"
    day_of_week: str = ""
    completed: bool = False
    due_date: date | None = None
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

    def normalised_frequency(self) -> str:
        """``frequency`` lowercased and stripped, for comparisons."""
        return str(self.frequency).strip().lower()

    def is_recurring(self) -> bool:
        """True if finishing this task should produce a next occurrence."""
        return self.normalised_frequency() in REPEAT_AFTER

    def is_due(self, weekday: str | None = None, on_date: date | None = None) -> bool:
        """Whether this task belongs in the plan for ``weekday`` / ``on_date``.

        Two independent gates, both of which must pass:

        * **Date.** A task carrying a ``due_date`` is due on that day and on any
          day after it (an overdue task still needs doing). A task with no
          ``due_date``, or a question with no ``on_date``, skips this gate —
          that is what keeps the date-free tasks in ``main.py`` working.
        * **Weekday.** Daily and one-off tasks pass. A weekly task passes only
          on its ``day_of_week`` — unless it names no day, or no day was asked
          about.
        """
        if self.due_date is not None and on_date is not None:
            if self.due_date > on_date:
                return False
        if self.normalised_frequency() != "weekly":
            return True
        if not self.day_of_week.strip() or weekday is None:
            return True
        return self.day_of_week.strip().lower() == str(weekday).strip().lower()

    def next_due_date(self, from_date: date | None = None) -> date | None:
        """When this task comes round again, or ``None`` if it never does.

        The step comes from ``REPEAT_AFTER``: one day for ``"daily"``, seven for
        ``"weekly"``. Seven days is deliberate for weekly tasks — it lands on
        the same weekday, so a ``day_of_week`` of "Sunday" stays a Sunday
        without any extra bookkeeping.

        ``from_date`` is the day the task was finished; it defaults to this
        instance's own ``due_date``, and failing that to today. Counting from
        the completion day rather than from "now" is what keeps a chain of
        completions from drifting: finishing Monday's walk late on Tuesday
        still schedules the next one for Tuesday, not Wednesday.
        """
        step = REPEAT_AFTER.get(self.normalised_frequency())
        if step is None:
            return None
        anchor = from_date or self.due_date or date.today()
        return anchor + step

    def create_next_occurrence(self, from_date: date | None = None) -> "CareTask | None":
        """A fresh, unfinished copy of this task dated for its next occurrence.

        Returns ``None`` for a ``"once"`` task — there is no next time. The copy
        keeps the title, duration, priority, requested time, frequency and
        weekday, so the recurring task really is the same task again; only
        ``completed`` and ``due_date`` move on.

        The copy is *not* attached to a pet here. :meth:`Scheduler.complete_task`
        does that, so a task can be rolled forward in isolation (in a test, say)
        without silently growing the pet's list.
        """
        next_date = self.next_due_date(from_date)
        if next_date is None:
            return None
        return replace(self, completed=False, due_date=next_date, pet=None)

    def mark_complete(self) -> None:
        """Record that this task has been done.

        Deliberately just a state flip. Spawning the next occurrence needs to
        attach that occurrence to the pet, which a task cannot do for itself
        without reaching back through its own back-reference — so the rollover
        lives in :meth:`Scheduler.complete_task`, one level up where the pet is
        already in hand.
        """
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


class FreeTime:
    """The owner's unbooked minutes, as a shrinking list of intervals.

    Exists to give the scheduler's densest operation a name. Each interval is
    ``[label, start_minute, end_minute)``; booking time out of one splits it
    into the leftovers on either side — zero, one, or two of them — which is
    why :meth:`book` ends in a slice assignment rather than a simple delete.
    Pulled out of ``build_plan`` so that method reads as "find a slot, book it"
    instead of as list surgery.
    """

    def __init__(self, windows: list[list]) -> None:
        #: Copied, not aliased: booking must not eat the caller's windows.
        self._free = [list(window) for window in windows]

    def __len__(self) -> int:
        return len(self._free)

    def label_at(self, index: int) -> str:
        """The name of the window interval ``index`` came from."""
        return self._free[index][0]

    def start_at(self, index: int) -> int:
        """The first free minute of interval ``index``."""
        return self._free[index][1]

    def fit_at(self, start: int, duration: int) -> int | None:
        """Index of the interval that fully contains ``[start, start+duration)``.

        Used for pinned tasks: the owner named a time, so it is that time or
        nothing. ``None`` means the requested slot is unavailable.
        """
        end = start + duration
        for index, (_, lo, hi) in enumerate(self._free):
            if lo <= start and end <= hi:
                return index
        return None

    def first_fit(self, duration: int) -> int | None:
        """Index of the earliest interval with room for ``duration``.

        Used for flexible tasks: anywhere will do, so take the earliest
        opening. ``None`` means nothing left is long enough.
        """
        for index, (_, lo, hi) in enumerate(self._free):
            if hi - lo >= duration:
                return index
        return None

    def book(self, index: int, start: int, duration: int) -> None:
        """Spend ``[start, start+duration)`` out of interval ``index``.

        The booked stretch is removed and whatever is left before and after it
        stays available, so booking 08:00-08:30 out of 07:00-09:00 leaves two
        shorter intervals rather than one unusable one.
        """
        label, lo, hi = self._free[index]
        end = start + duration
        leftovers = []
        if start > lo:
            leftovers.append([label, lo, start])
        if end < hi:
            leftovers.append([label, end, hi])
        # Replace the one interval with its leftovers in place: two of them when
        # the booking sits in the middle, one when it touches an edge, none when
        # it fills the interval exactly.
        self._free[index : index + 1] = leftovers


@dataclass
class TaskConflict:
    """Two tasks the owner asked for at overlapping times.

    A finding, not an error: it carries the two tasks and how many minutes they
    tread on each other, and :meth:`message` turns that into the warning the UI
    prints. Nothing here raises — see :meth:`Scheduler.detect_conflicts`.
    """

    first: CareTask
    second: CareTask
    overlap_minutes: int

    def same_pet(self) -> bool:
        """True if both tasks belong to one pet (``False`` also when unattached)."""
        return (
            self.first.pet is not None
            and self.second.pet is not None
            and self.first.pet is self.second.pet
        )

    def _window(self, task: CareTask) -> str:
        start = _to_minutes(task.start_time) or 0
        return f"{_to_clock(start)}-{_to_clock(start + task.duration_minutes)}"

    def message(self) -> str:
        """One warning line naming both tasks, their pets, and the overlap."""
        who = (
            f"{self.first.pet_name()}"
            if self.same_pet()
            else f"{self.first.pet_name() or 'unassigned'} and "
            f"{self.second.pet_name() or 'unassigned'}"
        )
        return (
            f"⚠ Conflict for {who}: "
            f"'{self.first.title}' ({self._window(self.first)}) overlaps "
            f"'{self.second.title}' ({self._window(self.second)}) "
            f"by {self.overlap_minutes} min."
        )

    def __str__(self) -> str:  # so print(conflict) reads as the warning
        return self.message()


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

    def pending_tasks(
        self, weekday: str | None = None, on_date: date | None = None
    ) -> list[CareTask]:
        """Unfinished tasks that are due on ``weekday`` / ``on_date``."""
        return [
            task
            for task in self.get_all_tasks()
            if not task.completed and task.is_due(weekday, on_date)
        ]

    def ranked_tasks(
        self, weekday: str | None = None, on_date: date | None = None
    ) -> list[CareTask]:
        """Due tasks in the order the scheduler would try to place them."""
        return sorted(
            self.pending_tasks(weekday, on_date),
            key=lambda task: (not task.is_pinned(), -task.weight(), task.title),
        )

    def tasks_for(self, pet: Pet) -> list[CareTask]:
        """One pet's slice of the owner's task list (for display, not planning)."""
        return [task for task in self.get_all_tasks() if task.pet is pet]

    def sort_by_time(self, tasks: list[CareTask] | None = None) -> list[CareTask]:
        """Tasks ordered by their requested ``start_time``, earliest first.

        Defaults to every task the owner has. Pass ``tasks`` to sort a slice
        instead, so the filters below compose with it::

            scheduler.sort_by_time(scheduler.filter_tasks(pet_name="Mochi"))

        The ``key`` lambda returns a tuple, which ``sorted`` compares left to
        right: unscheduled tasks (blank ``start_time``) sink to the bottom,
        the rest go by clock, and same-minute ties break by title.

        The key parses the string rather than sorting it as text. A zero-padded
        ``"HH:MM"`` *does* sort correctly on its own — ``"07:00" < "18:00"``
        character by character — but the time arrives from a free text box in
        ``app.py``, and a user typing ``"7:00"`` would land after ``"18:00"``
        because ``"7" > "1"``. ``_to_minutes`` turns both spellings into
        comparable integers.
        """
        pool = self.get_all_tasks() if tasks is None else list(tasks)
        return sorted(
            pool,
            key=lambda task: (
                _to_minutes(task.start_time) is None,  # False (0) sorts first
                _to_minutes(task.start_time) or 0,
                task.title,
            ),
        )

    def filter_tasks(
        self,
        tasks: list[CareTask] | None = None,
        *,
        pet_name: str | None = None,
        completed: bool | None = None,
    ) -> list[CareTask]:
        """Tasks narrowed by pet name and/or completion status.

        Both filters are optional and they stack — ``None`` means "don't
        care"::

            filter_tasks(pet_name="Mochi")                  # one pet, done or not
            filter_tasks(completed=False)                   # everything outstanding
            filter_tasks(pet_name="Mochi", completed=True)  # both at once

        Pet names are matched case-insensitively and ignore surrounding
        spaces, since they come from a text box. This is the name-based
        counterpart to :meth:`tasks_for`, which matches on object identity.
        """
        pool = self.get_all_tasks() if tasks is None else list(tasks)
        wanted = pet_name.strip().lower() if pet_name is not None else None
        return [
            task
            for task in pool
            if (wanted is None or task.pet_name().strip().lower() == wanted)
            and (completed is None or bool(task.completed) == bool(completed))
        ]

    # -- management --------------------------------------------------------

    def add_task(self, pet: Pet, task: CareTask) -> CareTask:
        """Give a pet a new task, registering the pet with the owner if needed."""
        self.owner.add_pet(pet)
        pet.add_task(task)
        return task

    def complete_task(
        self, task: CareTask, on_date: date | None = None
    ) -> CareTask | None:
        """Mark a task done and, if it recurs, queue up its next occurrence.

        Returns the newly created task, or ``None`` for a ``"once"`` task (and
        for a task that was already complete — finishing something twice must
        not breed two copies of it).

        The new instance is attached to the same pet, so it shows up in
        ``owner.get_all_tasks()`` straight away; its ``due_date`` keeps it out
        of *today's* plan until the day it is actually for.
        """
        if task.completed:
            return None

        task.mark_complete()

        follow_up = task.create_next_occurrence(on_date)
        if follow_up is None:
            return None
        if task.pet is not None:
            task.pet.add_task(follow_up)
        return follow_up

    # -- conflict detection ------------------------------------------------

    def detect_conflicts(
        self,
        weekday: str | None = None,
        on_date: date | None = None,
    ) -> list["TaskConflict"]:
        """Pairs of outstanding tasks whose requested times overlap.

        Only *pinned* tasks can conflict: a task with no requested time has no
        time to clash over, and the scheduler is free to drop it elsewhere.
        Two pinned tasks overlap when each starts before the other ends —
        ``start_a < end_b and start_b < end_a`` — which is the whole test, and
        it holds whether the two tasks belong to the same pet or to different
        ones. The owner is one person either way: they cannot brush the cat and
        walk the dog in the same ten minutes.

        This is deliberately a *report*, not an exception. Overlapping times are
        something the owner typed and may well have meant; the planner's job is
        to say so and carry on. :meth:`build_plan` still produces a plan — the
        loser of an overlap lands in ``skipped`` with its own reason.

        The scan is a straight pairwise walk over the pinned tasks. That is
        O(n²), which is the right trade here: a day holds a handful of tasks,
        and the simple version is the one that is obviously correct.
        """
        pinned = sorted(
            (
                task
                for task in self.get_all_tasks()
                if not task.completed
                and task.is_due(weekday, on_date)
                and task.is_pinned()
                and task.duration_minutes > 0
            ),
            key=lambda task: (_to_minutes(task.start_time) or 0, task.title),
        )

        conflicts: list[TaskConflict] = []
        for index, first in enumerate(pinned):
            first_start = _to_minutes(first.start_time) or 0
            first_end = first_start + first.duration_minutes
            for second in pinned[index + 1 :]:
                second_start = _to_minutes(second.start_time) or 0
                second_end = second_start + second.duration_minutes
                if first_start < second_end and second_start < first_end:
                    overlap = min(first_end, second_end) - max(first_start, second_start)
                    conflicts.append(TaskConflict(first, second, overlap))
        return conflicts

    def conflict_warnings(
        self,
        weekday: str | None = None,
        on_date: date | None = None,
    ) -> list[str]:
        """:meth:`detect_conflicts`, already phrased as warning lines."""
        return [conflict.message() for conflict in self.detect_conflicts(weekday, on_date)]

    def reset_day(self) -> None:
        """Reopen every task — the start of a new day."""
        for task in self.get_all_tasks():
            task.reopen()

    # -- planning ----------------------------------------------------------

    def build_plan(
        self, weekday: str | None = None, on_date: date | None = None
    ) -> "DailyPlan":
        """Select, order, and time-stamp every pet's tasks within the owner's windows.

        ``on_date`` is the calendar day being planned. Passing it is what keeps
        the next occurrence of a completed recurring task — which is already
        sitting on the pet — out of today's plan. Omit it and dates are ignored,
        exactly as before recurrence existed.

        Overlapping requested times are reported on ``DailyPlan.warnings``
        rather than raised: the plan is still built, and the task that lost the
        overlap lands in ``skipped`` with its own reason.
        """
        plan = DailyPlan(owner=self.owner)
        plan.warnings = self.conflict_warnings(weekday, on_date)
        windows = self._windows()
        free = FreeTime(windows)

        pinned, flexible = self._triage(plan, weekday, on_date)

        # Pass 1: honour requested times, earliest request first, so an explicit
        # wish always beats a score.
        for task in sorted(pinned, key=lambda t: _to_minutes(t.start_time) or 0):
            start = _to_minutes(task.start_time)
            index = free.fit_at(start, task.duration_minutes)
            if index is None:
                plan.skipped.append(self._reject(task, self._why_pin_failed(windows, task)))
                continue
            label = free.label_at(index)
            free.book(index, start, task.duration_minutes)
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
        # Kept as its own loop rather than folded into pass 1 behind a "find a
        # slot" callback: the two passes differ in how they choose a slot and in
        # why they fail, and spelling both out reads better than one abstraction
        # the reader has to unpick.
        for task in sorted(flexible, key=lambda t: (-t.weight(), t.title)):
            index = free.first_fit(task.duration_minutes)
            if index is None:
                plan.skipped.append(
                    self._reject(
                        task,
                        f"no window had {task.duration_minutes} free minutes left",
                    )
                )
                continue
            label = free.label_at(index)
            start = free.start_at(index)
            free.book(index, start, task.duration_minutes)
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

    def _triage(
        self,
        plan: "DailyPlan",
        weekday: str | None,
        on_date: date | None,
    ) -> tuple[list[CareTask], list[CareTask]]:
        """Split today's tasks into the pinned and the flexible.

        Anything that cannot be scheduled at all — already done, not due today,
        or a nonsense duration — is appended to ``plan.skipped`` with the reason
        and never reaches the placement passes. Returns the two lists that do:
        ``(pinned, flexible)``.
        """
        pinned: list[CareTask] = []
        flexible: list[CareTask] = []
        for task in self.get_all_tasks():
            if task.completed:
                plan.skipped.append(self._reject(task, "already done today"))
            elif not task.is_due(weekday, on_date):
                plan.skipped.append(
                    self._reject(task, self._why_not_due(task, weekday, on_date))
                )
            elif task.duration_minutes <= 0:
                plan.skipped.append(
                    self._reject(task, "duration must be at least 1 minute")
                )
            elif task.is_pinned():
                pinned.append(task)
            else:
                flexible.append(task)
        return pinned, flexible

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
    def _reject(task: CareTask, reason: str) -> PlanEntry:
        return PlanEntry(pet=task.pet, task=task, reason=reason)

    @staticmethod
    def _why_not_due(
        task: CareTask, weekday: str | None, on_date: date | None
    ) -> str:
        """Say which of ``is_due``'s two gates this task failed."""
        if (
            task.due_date is not None
            and on_date is not None
            and task.due_date > on_date
        ):
            return f"next {task.frequency} occurrence, due {task.due_date:%a %d %b}"
        return f"{task.frequency} task, not due on {weekday}"

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
    #: Non-fatal notices raised while building — currently the overlapping
    #: requested times found by :meth:`Scheduler.detect_conflicts`. A plan with
    #: warnings is still a usable plan.
    warnings: list[str] = field(default_factory=list)

    @staticmethod
    def build(
        owner: Owner, weekday: str | None = None, on_date: date | None = None
    ) -> "DailyPlan":
        """Convenience wrapper around :meth:`Scheduler.build_plan`."""
        return Scheduler(owner).build_plan(weekday, on_date)

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

        if self.warnings:
            lines.append(f"Warnings ({len(self.warnings)}):")
            lines.extend(f"  {warning}" for warning in self.warnings)
            lines.append("")

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
                "Due": f"{entry.task.due_date:%d %b}" if entry.task.due_date else "—",
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
