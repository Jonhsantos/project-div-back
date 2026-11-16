"""Adicionar dados de conferência das despesas.

Revision ID: 0005
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("despesas", sa.Column("motivo_correcao", sa.Text(), nullable=True))
    op.add_column("despesas", sa.Column("conferido_por", sa.BigInteger(), nullable=True))
    op.add_column("despesas", sa.Column("conferido_em", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key("fk_despesas_conferido_por", "despesas", "usuarios", ["conferido_por"], ["id_usuario"])


def downgrade():
    op.drop_constraint("fk_despesas_conferido_por", "despesas", type_="foreignkey")
    op.drop_column("despesas", "conferido_em")
    op.drop_column("despesas", "conferido_por")
    op.drop_column("despesas", "motivo_correcao")
