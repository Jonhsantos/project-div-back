"""Criar tabela de participantes.

Revision ID: 0003
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "participantes",
        sa.Column("id_participante", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("id_viagem", sa.BigInteger(), sa.ForeignKey("viagens.id_viagem"), nullable=False),
        sa.Column("id_usuario", sa.BigInteger(), sa.ForeignKey("usuarios.id_usuario"), nullable=False),
        sa.Column("ingressou_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("id_viagem", "id_usuario", name="uq_participantes_viagem_usuario"),
    )
    op.create_index("ix_participantes_id_usuario", "participantes", ["id_usuario"])


def downgrade():
    op.drop_index("ix_participantes_id_usuario", table_name="participantes")
    op.drop_table("participantes")
