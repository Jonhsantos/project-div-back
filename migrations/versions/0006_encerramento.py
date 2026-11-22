"""Registrar o instante real de encerramento das viagens."""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("viagens", sa.Column("encerrada_em", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column("viagens", "encerrada_em")
