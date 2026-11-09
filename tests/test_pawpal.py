"""Behaviour tests for the PawPal+ domain model.

The import below only works because ``conftest.py`` in this folder puts the
project root on Python's module search path — see the explanation in that file.

WHAT THIS SUITE COVERS
----------------------
Five core behaviours, each with its happy path and its edge cases:

1. **Sorting** (``Scheduler.sort_by_time``) — chronological order, including
   the unpadded ``"7:00"`` that would sort wrongly as text.
2. **Filtering** (``Scheduler.filter_tasks``) — by pet, by completion, and both
   at once, with ``None`` meaning "don't care".
3. **Recurrence** (``Scheduler.complete_task``) — a finished daily or weekly
   task queues its next instance; ``once`` queues nothing.
4. **Conflict detection** (``Scheduler.detect_conflicts``) — overlapping
   requested times are reported, within one pet and across two, and
   back-to-back tasks are *not* flagged.
5. **Plan building** (``Scheduler.build_plan``) — placement, the shared time
   budget, and a reason recorded for everything left out.

Edge cases deliberately included: a pet with no tasks, an owner with no pets,
an owner with no free time, two tasks at the exact same minute, malformed and
unpadded clock strings, a task longer than any window, zero duration, and
month-end date arithmetic.

Every test uses the fixed ``TODAY`` below rather than ``date.today()`` so the
suite means the same thing whenever it runs.
"""

from datetime import date, timedelta

from pawpal_system import CareTask, Owner, Pet, Scheduler, TimeSlot

#: A fixed date so these tests do not change meaning depending on when they run.
TODAY = date(2026, 2, 27)


def test_mark_complete_changes_task_status():
    """A task starts unfinished; mark_complete() flips it to done."""
    task = CareTask("Morning walk", 30, "high")

    # Confirm the starting state, so a task that was somehow already complete
    # can't make this test pass for the wrong reason.
    assert task.completed is False

    task.mark_complete()

    assert task.completed is True


def test_add_task_increases_pet_task_count():
    """Adding a task to a pet grows that pet's task list by one."""
    pet = Pet("Mochi", "dog", age_years=3)

    assert len(pet.tasks) == 0

    pet.add_task(CareTask("Feeding", 10, "high"))

    assert len(pet.tasks) == 1


# --- Step 3: recurring tasks ---------------------------------------------


def _scheduler_with(*tasks: CareTask) -> tuple[Scheduler, Pet]:
    """A scheduler holding one pet with ``tasks`` attached, free all morning."""
    owner = Owner("Jordan", available_timeslots=[TimeSlot("Morning", "07:00", "12:00")])
    pet = Pet("Mochi", "dog", age_years=3)
    scheduler = Scheduler(owner)
    for task in tasks:
        scheduler.add_task(pet, task)
    return scheduler, pet


def test_completing_a_daily_task_queues_tomorrow():
    """A finished daily task reappears on the pet, dated today + 1 day."""
    walk = CareTask("Morning walk", 30, "high", start_time="07:00", due_date=TODAY)
    scheduler, pet = _scheduler_with(walk)

    follow_up = scheduler.complete_task(walk, on_date=TODAY)

    assert walk.completed is True
    assert follow_up is not None
    assert follow_up.due_date == TODAY + timedelta(days=1)
    assert follow_up.completed is False
    # Same task, same pet — only the date and the done-flag moved on.
    assert follow_up.title == walk.title
    assert follow_up.start_time == walk.start_time
    assert follow_up in pet.tasks


def test_daily_rollover_crosses_a_month_end():
    """timedelta does the calendar arithmetic: 2026-02-28 -> 2026-03-01."""
    task = CareTask("Feeding", 10, "high", frequency="daily")

    assert task.next_due_date(date(2026, 2, 28)) == date(2026, 3, 1)


def test_completing_a_weekly_task_keeps_its_weekday():
    """A weekly task jumps seven days, so its day_of_week still holds."""
    trim = CareTask(
        "Nail trim", 20, "low", frequency="weekly", day_of_week="Friday",
        due_date=date(2026, 2, 27),  # a Friday
    )
    scheduler, _ = _scheduler_with(trim)

    follow_up = scheduler.complete_task(trim, on_date=date(2026, 2, 27))

    assert follow_up.due_date == date(2026, 3, 6)
    assert follow_up.due_date.strftime("%A") == "Friday"


def test_a_once_task_does_not_come_back():
    """"once" means once — completing it queues nothing."""
    task = CareTask("Vet visit", 60, "high", frequency="once", due_date=TODAY)
    scheduler, pet = _scheduler_with(task)

    assert scheduler.complete_task(task, on_date=TODAY) is None
    assert len(pet.tasks) == 1


def test_completing_twice_does_not_queue_two_copies():
    """A second completion is a no-op, not a second instance."""
    task = CareTask("Feeding", 10, "high", due_date=TODAY)
    scheduler, pet = _scheduler_with(task)

    scheduler.complete_task(task, on_date=TODAY)
    assert scheduler.complete_task(task, on_date=TODAY) is None
    assert len(pet.tasks) == 2  # the original plus exactly one follow-up


def test_queued_occurrence_stays_out_of_todays_plan():
    """Tomorrow's instance is skipped today rather than double-booking."""
    task = CareTask("Feeding", 10, "high", due_date=TODAY)
    scheduler, _ = _scheduler_with(task)
    scheduler.complete_task(task, on_date=TODAY)

    plan = scheduler.build_plan(TODAY.strftime("%A"), TODAY)

    assert plan.entries == []
    assert any("occurrence" in entry.reason for entry in plan.skipped)


# --- Step 4: conflict detection -------------------------------------------


def test_overlapping_tasks_are_reported_not_raised():
    """Two tasks sharing minutes produce a warning; nothing raises."""
    meds = CareTask("Meds", 10, "high", start_time="07:45")
    brushing = CareTask("Brushing", 15, "medium", start_time="07:45")
    scheduler, _ = _scheduler_with(meds, brushing)

    conflicts = scheduler.detect_conflicts()

    assert len(conflicts) == 1
    assert conflicts[0].overlap_minutes == 10
    assert "overlaps" in conflicts[0].message()


def test_conflicts_are_found_across_different_pets():
    """One owner, two pets, one pair of hands — still a conflict."""
    owner = Owner("Jordan", available_timeslots=[TimeSlot("AM", "07:00", "12:00")])
    scheduler = Scheduler(owner)
    scheduler.add_task(Pet("Mochi", "dog", 3), CareTask("Walk", 30, "high", start_time="08:00"))
    scheduler.add_task(Pet("Biscuit", "cat", 7), CareTask("Feeding", 10, "high", start_time="08:15"))

    conflicts = scheduler.detect_conflicts()

    assert len(conflicts) == 1
    assert conflicts[0].same_pet() is False


def test_back_to_back_tasks_do_not_conflict():
    """A task ending exactly when the next starts is fine, not an overlap."""
    first = CareTask("Walk", 30, "high", start_time="07:00")   # 07:00-07:30
    second = CareTask("Feeding", 10, "high", start_time="07:30")  # 07:30-07:40
    scheduler, _ = _scheduler_with(first, second)

    assert scheduler.detect_conflicts() == []


def test_unpinned_and_completed_tasks_are_not_conflicts():
    """Only outstanding tasks with a requested time can clash."""
    flexible = CareTask("Litter box", 15, "medium")  # no requested time
    done = CareTask("Meds", 10, "high", start_time="07:00", completed=True)
    pinned = CareTask("Walk", 30, "high", start_time="07:00")
    scheduler, _ = _scheduler_with(flexible, done, pinned)

    assert scheduler.detect_conflicts() == []


def test_build_plan_warns_but_still_schedules():
    """A conflicting day still yields a plan — the loser lands in skipped."""
    meds = CareTask("Meds", 10, "high", start_time="07:45")
    brushing = CareTask("Brushing", 15, "medium", start_time="07:45")
    scheduler, _ = _scheduler_with(meds, brushing)

    plan = scheduler.build_plan()

    assert len(plan.warnings) == 1
    assert len(plan.entries) == 1
    assert any("collides" in entry.reason for entry in plan.skipped)


def test_two_tasks_at_the_exact_same_minute_conflict():
    """The textbook edge case: identical start times, identical durations."""
    first = CareTask("Walk", 20, "high", start_time="08:00")
    second = CareTask("Vet call", 20, "high", start_time="08:00")
    scheduler, _ = _scheduler_with(first, second)

    conflicts = scheduler.detect_conflicts()

    assert len(conflicts) == 1
    # Identical windows overlap completely, so the overlap is the full duration.
    assert conflicts[0].overlap_minutes == 20


def test_three_overlapping_tasks_report_every_pair():
    """n tasks all overlapping yield n*(n-1)/2 findings, not just one."""
    scheduler, _ = _scheduler_with(
        CareTask("A", 60, "high", start_time="08:00"),
        CareTask("B", 60, "high", start_time="08:10"),
        CareTask("C", 60, "high", start_time="08:20"),
    )

    assert len(scheduler.detect_conflicts()) == 3  # A-B, A-C, B-C


# --- Sorting --------------------------------------------------------------


def test_sort_by_time_returns_chronological_order():
    """Tasks come back earliest-first regardless of the order they were added."""
    scheduler, _ = _scheduler_with(
        CareTask("Evening meds", 10, "high", start_time="18:30"),
        CareTask("Lunch", 15, "medium", start_time="12:00"),
        CareTask("Morning walk", 30, "high", start_time="07:00"),
    )

    order = [task.title for task in scheduler.sort_by_time()]

    assert order == ["Morning walk", "Lunch", "Evening meds"]


def test_sort_by_time_handles_unpadded_hours():
    """"7:00" must sort before "18:00" — text comparison would get this wrong.

    Sorting these as plain strings puts "18:00" first, because the character
    "1" is less than "7". The sort key parses to minutes instead, so this is
    the test that would catch a regression back to string comparison.
    """
    scheduler, _ = _scheduler_with(
        CareTask("Evening walk", 30, "high", start_time="18:00"),
        CareTask("Breakfast", 10, "high", start_time="7:00"),
    )

    order = [task.title for task in scheduler.sort_by_time()]

    assert order == ["Breakfast", "Evening walk"]


def test_tasks_without_a_requested_time_sort_last():
    """Unscheduled tasks sink below every timed one, then order by title."""
    scheduler, _ = _scheduler_with(
        CareTask("Zoomies", 10, "low"),          # no requested time
        CareTask("Brushing", 10, "low"),         # no requested time
        CareTask("Meds", 10, "high", start_time="09:00"),
    )

    order = [task.title for task in scheduler.sort_by_time()]

    assert order[0] == "Meds"
    assert order[1:] == ["Brushing", "Zoomies"]  # alphabetical among the untimed


def test_sort_by_time_accepts_a_filtered_slice():
    """The sorter composes with the filter rather than always reading all tasks."""
    scheduler, _ = _scheduler_with(
        CareTask("Late", 10, "low", start_time="20:00"),
        CareTask("Early", 10, "low", start_time="06:00"),
    )

    subset = scheduler.filter_tasks(completed=False)
    order = [task.title for task in scheduler.sort_by_time(subset)]

    assert order == ["Early", "Late"]


def test_malformed_times_are_treated_as_unscheduled():
    """Garbage in the time box sinks to the bottom instead of crashing."""
    scheduler, _ = _scheduler_with(
        CareTask("Nonsense", 10, "low", start_time="abc"),
        CareTask("Impossible", 10, "low", start_time="25:00"),
        CareTask("Real", 10, "high", start_time="08:00"),
    )

    order = [task.title for task in scheduler.sort_by_time()]

    assert order[0] == "Real"
    assert set(order[1:]) == {"Nonsense", "Impossible"}
    # And a malformed time is not a pinned time, so it cannot cause a conflict.
    assert scheduler.detect_conflicts() == []


# --- Filtering ------------------------------------------------------------


def _two_pet_scheduler() -> Scheduler:
    """One owner, two pets, four tasks, one of them already done."""
    owner = Owner("Jordan", available_timeslots=[TimeSlot("AM", "07:00", "12:00")])
    scheduler = Scheduler(owner)
    mochi = Pet("Mochi", "dog", age_years=3)
    biscuit = Pet("Biscuit", "cat", age_years=7)
    scheduler.add_task(mochi, CareTask("Walk", 30, "high", start_time="07:00"))
    scheduler.add_task(mochi, CareTask("Meds", 10, "high", start_time="08:00"))
    scheduler.add_task(biscuit, CareTask("Litter box", 15, "medium"))
    done = CareTask("Feeding", 10, "high", frequency="once")
    scheduler.add_task(biscuit, done)
    scheduler.complete_task(done, on_date=TODAY)
    return scheduler


def test_filter_by_pet_name_is_case_insensitive():
    """Pet names come from a text box, so matching ignores case and spaces."""
    scheduler = _two_pet_scheduler()

    assert len(scheduler.filter_tasks(pet_name="mochi")) == 2
    assert len(scheduler.filter_tasks(pet_name="  MOCHI  ")) == 2


def test_filter_by_completion_status():
    """completed=True and completed=False partition the whole task list."""
    scheduler = _two_pet_scheduler()

    done = scheduler.filter_tasks(completed=True)
    todo = scheduler.filter_tasks(completed=False)

    assert [task.title for task in done] == ["Feeding"]
    assert len(todo) == 3
    assert len(done) + len(todo) == len(scheduler.get_all_tasks())


def test_filters_stack():
    """Both filters at once narrow to the intersection."""
    scheduler = _two_pet_scheduler()

    result = scheduler.filter_tasks(pet_name="Biscuit", completed=False)

    assert [task.title for task in result] == ["Litter box"]


def test_no_filters_returns_everything():
    """None means "don't care" — passing neither filter is not a filter."""
    scheduler = _two_pet_scheduler()

    assert len(scheduler.filter_tasks()) == len(scheduler.get_all_tasks())


def test_filter_on_an_unknown_pet_returns_empty():
    """A name nobody has yields nothing rather than raising."""
    scheduler = _two_pet_scheduler()

    assert scheduler.filter_tasks(pet_name="Rex") == []


# --- Empty and degenerate cases -------------------------------------------


def test_pet_with_no_tasks_contributes_nothing():
    """A pet the owner has not given any work to is harmless everywhere."""
    owner = Owner("Jordan", available_timeslots=[TimeSlot("AM", "07:00", "09:00")])
    owner.add_pet(Pet("Ghost", "fish", age_years=1))
    scheduler = Scheduler(owner)

    assert scheduler.get_all_tasks() == []
    assert scheduler.sort_by_time() == []
    assert scheduler.detect_conflicts() == []

    plan = scheduler.build_plan(TODAY.strftime("%A"), TODAY)

    assert plan.entries == []
    assert plan.skipped == []
    assert plan.unused_minutes() == 120  # the whole window is still free


def test_owner_with_no_pets_produces_an_empty_plan():
    """The emptiest case of all still returns a plan object, not an error."""
    owner = Owner("Jordan", available_timeslots=[TimeSlot("AM", "07:00", "09:00")])
    plan = Scheduler(owner).build_plan()

    assert plan.entries == []
    assert plan.scheduled_minutes() == 0
    assert "Scheduled (0)" in plan.explain()


def test_owner_with_no_free_time_schedules_nothing_but_explains_why():
    """No availability is a real situation, not a crash."""
    owner = Owner("Jordan", available_timeslots=[])
    scheduler = Scheduler(owner)
    scheduler.add_task(Pet("Mochi", "dog", 3), CareTask("Walk", 30, "high"))

    plan = scheduler.build_plan()

    assert plan.entries == []
    assert plan.unused_minutes() == 0
    assert any("no window" in entry.reason for entry in plan.skipped)


def test_task_longer_than_every_window_is_skipped_with_a_reason():
    """A 3-hour task cannot fit a 2-hour window; say so rather than truncate."""
    owner = Owner("Jordan", available_timeslots=[TimeSlot("AM", "07:00", "09:00")])
    scheduler = Scheduler(owner)
    scheduler.add_task(Pet("Mochi", "dog", 3), CareTask("Spa day", 180, "low"))

    plan = scheduler.build_plan()

    assert plan.entries == []
    assert "180 free minutes" in plan.skipped[0].reason


def test_zero_duration_task_is_rejected():
    """A task that takes no time is a data error, not a free lunch."""
    scheduler, _ = _scheduler_with(CareTask("Nothing", 0, "high"))

    plan = scheduler.build_plan()

    assert plan.entries == []
    assert "at least 1 minute" in plan.skipped[0].reason


def test_weekly_task_is_skipped_on_the_wrong_weekday():
    """A Sunday task does not appear on a Friday."""
    trim = CareTask("Nail trim", 20, "low", frequency="weekly", day_of_week="Sunday")
    scheduler, _ = _scheduler_with(trim)

    plan = scheduler.build_plan("Friday")

    assert plan.entries == []
    assert "not due on Friday" in plan.skipped[0].reason


# --- Multi-pet budgeting ---------------------------------------------------


def test_one_owner_two_pets_share_a_single_time_budget():
    """The whole point of planning at the owner level: minutes are spent once.

    Two pets with 30 minutes of work each, in a 45-minute window, must come to
    45 booked minutes and one skipped task — not 60, which is what planning each
    pet against the full window separately would produce.
    """
    owner = Owner("Jordan", available_timeslots=[TimeSlot("AM", "07:00", "07:45")])
    scheduler = Scheduler(owner)
    scheduler.add_task(Pet("Mochi", "dog", 3), CareTask("Walk", 30, "high"))
    scheduler.add_task(Pet("Biscuit", "cat", 7), CareTask("Grooming", 30, "high"))

    plan = scheduler.build_plan()

    assert plan.scheduled_minutes() == 30
    assert len(plan.entries) == 1
    assert len(plan.skipped) == 1
