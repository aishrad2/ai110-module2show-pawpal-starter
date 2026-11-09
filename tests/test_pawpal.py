"""Two basic behaviour checks for the PawPal+ domain model.

The import below only works because ``conftest.py`` in this folder puts the
project root on Python's module search path — see the explanation in that file.
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
