"""SQLAlchemy ORM models.

Importing this package triggers the side effect of registering all
model classes with ``Base.metadata`` (because each model class
definition runs at import time). Anywhere that needs to see all
tables — e.g. ``Base.metadata.create_all()`` or
``alembic --autogenerate`` — must import this package first.

We import the concrete models (not the files) so the symbol
``backend.app.models.Experiment`` and ``backend.app.models.Run``
exist for any code that wants them.
"""
from backend.app.models.experiment import Experiment
from backend.app.models.run import Run

__all__ = ["Experiment", "Run"]
