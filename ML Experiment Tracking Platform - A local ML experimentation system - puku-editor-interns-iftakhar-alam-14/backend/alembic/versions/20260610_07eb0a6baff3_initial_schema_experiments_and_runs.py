"""initial schema: experiments and runs

Revision ID: 07eb0a6baff3
Revises:
Create Date: 2026-06-10 00:18:02.075914

This migration creates the two tables that back the entire platform:

  * experiments — top-level container for a set of related runs
  * runs        — individual training/inference jobs that belong to an experiment

The DDL below mirrors the SQLAlchemy model definitions in
``backend/app/models/`` exactly. If you change a model, autogenerate
will produce a follow-up migration that diffs against this baseline.

To re-derive this file with autogenerate, run:
    alembic revision --autogenerate -m "initial schema"
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = '07eb0a6baff3'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the initial schema."""
    # ─── experiments ──────────────────────────────────────────────────
    op.create_table(
        'experiments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('tags', sa.Text(), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=True,
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_experiments_id'), 'experiments', ['id'], unique=False
    )
    op.create_index(
        op.f('ix_experiments_name'), 'experiments', ['name'], unique=True
    )

    # ─── runs ─────────────────────────────────────────────────────────
    op.create_table(
        'runs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('experiment_id', sa.Integer(), nullable=False),
        sa.Column('run_name', sa.String(length=255), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=True),
        sa.Column('metrics', sa.Text(), nullable=True),
        sa.Column('parameters', sa.Text(), nullable=True),
        sa.Column('tags', sa.Text(), nullable=True),
        sa.Column('artifact_uri', sa.String(length=500), nullable=True),
        sa.Column(
            'start_time',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=True,
        ),
        sa.Column('end_time', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ['experiment_id'], ['experiments.id'],
            name='fk_runs_experiment_id_experiments',
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_runs_id'), 'runs', ['id'], unique=False
    )


def downgrade() -> None:
    """Reverse the initial schema (drops the runs table first, then experiments)."""
    # Drop the dependent table first because of the foreign key.
    op.drop_index(op.f('ix_runs_id'), table_name='runs')
    op.drop_table('runs')

    op.drop_index(op.f('ix_experiments_name'), table_name='experiments')
    op.drop_index(op.f('ix_experiments_id'), table_name='experiments')
    op.drop_table('experiments')
