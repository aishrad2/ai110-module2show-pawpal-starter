"""Two basic behaviour checks for the PawPal+ domain model.

The import below only works because ``conftest.py`` in this folder puts the
project root on Python's module search path — see the explanation in that file.
"""

from pawpal_system import CareTask, Pet


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
