from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator


class UserCreate(BaseModel):
    nome: str = Field(min_length=1, max_length=150)
    email: EmailStr
    senha: str = Field(min_length=8, max_length=128)
    perfil: Literal["LIDER", "TECNICO"]

    @field_validator("nome")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Informe seu nome")
        return value


class Login(BaseModel):
    email: EmailStr
    senha: str = Field(min_length=1, max_length=128)


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id_usuario: int
    nome: str
    email: EmailStr
    perfil: Literal["LIDER", "TECNICO"]
    criado_em: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TripCreate(BaseModel):
    titulo: str = Field(min_length=1, max_length=150)
    destino: str = Field(min_length=1, max_length=255)
    data_inicio: date
    data_fim: date | None = None
    descricao: str | None = Field(default=None, max_length=5000)

    @field_validator("titulo", "destino")
    @classmethod
    def clean_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Campo obrigatório")
        return value

    @model_validator(mode="after")
    def check_dates(self):
        if self.data_fim and self.data_fim < self.data_inicio:
            raise ValueError("A data de término não pode ser anterior ao início")
        return self


class TripPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id_viagem: int
    id_lider: int
    titulo: str
    destino: str
    data_inicio: date
    data_fim: date | None
    descricao: str | None
    status: Literal["EM_ANDAMENTO", "ENCERRADA"]
    criado_em: datetime


class TripRead(TripPublic):
    codigo_acesso: str


class TripParticipant(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id_usuario: int
    nome: str
    perfil: Literal["LIDER", "TECNICO"]


class TripDetails(BaseModel):
    viagem: TripRead | TripPublic
    participantes: list[TripParticipant] | None = None


class TripJoin(BaseModel):
    codigo_acesso: str = Field(min_length=1, max_length=20)

    @field_validator("codigo_acesso", mode="before")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        if not isinstance(value, str):
            return value
        value = value.strip().upper()
        if not value:
            raise ValueError("Informe o código da viagem")
        return value


class ExpenseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id_despesa: int
    id_viagem: int
    id_usuario: int
    descricao: str
    valor: Decimal
    data_despesa: date
    categoria: str
    status: str
    motivo_correcao: str | None
    conferido_por: int | None
    conferido_em: datetime | None
    criado_em: datetime


class ExpenseUserTotal(BaseModel):
    id_usuario: int
    nome: str
    total: Decimal
    quantidade: int


class ExpenseSummary(BaseModel):
    total: Decimal
    quantidade: int
    por_tecnico: list[ExpenseUserTotal] | None = None


class ExpenseReview(BaseModel):
    decisao: Literal["CONFERIDA", "PENDENTE_CORRECAO"]
    motivo_correcao: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_reason(self):
        if self.decisao == "PENDENTE_CORRECAO":
            if not self.motivo_correcao or not self.motivo_correcao.strip():
                raise ValueError("Informe o motivo da correção")
            self.motivo_correcao = self.motivo_correcao.strip()
        elif self.motivo_correcao:
            raise ValueError("Motivo permitido apenas para solicitação de correção")
        return self
