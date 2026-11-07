"""Shared pytest setup for every test in this folder.

WHAT IS conftest.py?
--------------------
``conftest.py`` is a filename pytest treats specially. You never import it and
you never reference it by name: before pytest runs any test in this directory,
it finds this file automatically and executes it. That makes it the standard
home for setup and fixtures that several test files should share.

WHY DOES THIS PROJECT NEED ONE?
-------------------------------
``pawpal_system.py`` lives at the repository root::

    ai110-module2show-pawpal-starter/
    ├── pawpal_system.py        <- the code under test
    ├── test_pawpal_system.py   <- same folder, so `import pawpal_system` works
    └── tests/
        ├── conftest.py         <- this file
        └── test_pawpal.py      <- one folder down, so the import would FAIL

When pytest collects a test file, it adds *that file's own folder* to
``sys.path`` (the list of places Python searches for modules). For
``tests/test_pawpal.py`` that folder is ``tests/`` — which does not contain
``pawpal_system.py``. Without help, the import raises::

    ModuleNotFoundError: No module named 'pawpal_system'

The fix below adds the project root to ``sys.path`` as well, so the import
resolves. The root-level ``test_pawpal_system.py`` never needed this because it
already sits beside the module it imports.
"""

import sys
from pathlib import Path

# __file__ is this file's path. .resolve() makes it absolute, the first
# .parent is tests/, and the second .parent is the project root.
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# sys.path holds the folders Python searches when you write `import X`.
# insert(0, ...) puts the project root first so it is searched before anything
# else. The `if` guard keeps the entry from being added twice.
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
