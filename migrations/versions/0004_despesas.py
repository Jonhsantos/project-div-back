"""Criar despesas com comprovante obrigatório.

Revision ID: 0004
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "despesas",
        sa.Column("id_despesa", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("id_viagem", sa.BigInteger(), sa.ForeignKey("viagens.id_viagem"), nullable=False),
        sa.Column("id_usuario", sa.BigInteger(), sa.ForeignKey("usuarios.id_usuario"), nullable=False),
        sa.Column("descricao", sa.String(255), nullable=False),
        sa.Column("valor", sa.Numeric(12, 2), nullable=False),
        sa.Column("data_despesa", sa.Date(), nullable=False),
        sa.Column("categoria", sa.String(30), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("comprovante_conteudo", sa.LargeBinary(), nullable=False),
        sa.Column("comprovante_tipo", sa.String(30), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("valor > 0", name="ck_despesas_valor"),
        sa.CheckConstraint("status IN ('AGUARDANDO_CONFERENCIA', 'CONFERIDA', 'PENDENTE_CORRECAO')", name="ck_despesas_status"),
        sa.CheckConstraint("categoria IN ('ALIMENTACAO', 'HOSPEDAGEM', 'TRANSPORTE', 'ALUGUEL', 'OUTROS')", name="ck_despesas_categoria"),
    )
    op.create_index("ix_despesas_id_viagem", "despesas", ["id_viagem"])


def downgrade():
    op.drop_index("ix_despesas_id_viagem", table_name="despesas")
    op.drop_table("despesas")
