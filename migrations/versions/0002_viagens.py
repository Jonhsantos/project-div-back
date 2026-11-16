"""Criar tabela de viagens.

Revision ID: 0002
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "viagens",
        sa.Column("id_viagem", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("id_lider", sa.BigInteger(), sa.ForeignKey("usuarios.id_usuario"), nullable=False),
        sa.Column("titulo", sa.String(150), nullable=False),
        sa.Column("destino", sa.String(255), nullable=False),
        sa.Column("data_inicio", sa.Date(), nullable=False),
        sa.Column("data_fim", sa.Date()),
        sa.Column("descricao", sa.Text()),
        sa.Column("codigo_acesso", sa.String(20), nullable=False, unique=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('EM_ANDAMENTO', 'ENCERRADA')", name="ck_viagens_status"),
        sa.CheckConstraint("data_fim IS NULL OR data_fim >= data_inicio", name="ck_viagens_datas"),
    )
    op.create_index("ix_viagens_id_lider", "viagens", ["id_lider"])


def downgrade():
    op.drop_index("ix_viagens_id_lider", table_name="viagens")
    op.drop_table("viagens")
