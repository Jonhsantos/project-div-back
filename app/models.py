from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, CheckConstraint, Date, DateTime, ForeignKey, Integer, LargeBinary, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class User(Base):
    __tablename__ = "usuarios"
    __table_args__ = (CheckConstraint("perfil IN ('LIDER', 'TECNICO')", name="ck_usuarios_perfil"),)

    id_usuario: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    nome: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    senha_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    perfil: Mapped[str] = mapped_column(String(20), nullable=False)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Trip(Base):
    __tablename__ = "viagens"
    __table_args__ = (
        CheckConstraint("status IN ('EM_ANDAMENTO', 'ENCERRADA')", name="ck_viagens_status"),
        CheckConstraint("data_fim IS NULL OR data_fim >= data_inicio", name="ck_viagens_datas"),
    )

    id_viagem: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    id_lider: Mapped[int] = mapped_column(ForeignKey("usuarios.id_usuario"), nullable=False, index=True)
    titulo: Mapped[str] = mapped_column(String(150), nullable=False)
    destino: Mapped[str] = mapped_column(String(255), nullable=False)
    data_inicio: Mapped[date] = mapped_column(Date, nullable=False)
    data_fim: Mapped[date | None] = mapped_column(Date)
    descricao: Mapped[str | None] = mapped_column(Text)
    codigo_acesso: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="EM_ANDAMENTO")
    encerrada_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Participant(Base):
    __tablename__ = "participantes"
    __table_args__ = (UniqueConstraint("id_viagem", "id_usuario", name="uq_participantes_viagem_usuario"),)

    id_participante: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    id_viagem: Mapped[int] = mapped_column(ForeignKey("viagens.id_viagem"), nullable=False)
    id_usuario: Mapped[int] = mapped_column(ForeignKey("usuarios.id_usuario"), nullable=False, index=True)
    ingressou_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Expense(Base):
    __tablename__ = "despesas"
    __table_args__ = (
        CheckConstraint("valor > 0", name="ck_despesas_valor"),
        CheckConstraint("status IN ('AGUARDANDO_CONFERENCIA', 'CONFERIDA', 'PENDENTE_CORRECAO')", name="ck_despesas_status"),
        CheckConstraint("categoria IN ('ALIMENTACAO', 'HOSPEDAGEM', 'TRANSPORTE', 'ALUGUEL', 'OUTROS')", name="ck_despesas_categoria"),
    )
    id_despesa: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    id_viagem: Mapped[int] = mapped_column(ForeignKey("viagens.id_viagem"), nullable=False, index=True)
    id_usuario: Mapped[int] = mapped_column(ForeignKey("usuarios.id_usuario"), nullable=False)
    descricao: Mapped[str] = mapped_column(String(255), nullable=False)
    valor: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    data_despesa: Mapped[date] = mapped_column(Date, nullable=False)
    categoria: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="AGUARDANDO_CONFERENCIA")
    comprovante_conteudo: Mapped[bytes] = mapped_column(LargeBinary, nullable=False, deferred=True)
    comprovante_tipo: Mapped[str] = mapped_column(String(30), nullable=False)
    motivo_correcao: Mapped[str | None] = mapped_column(Text)
    conferido_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id_usuario"))
    conferido_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
