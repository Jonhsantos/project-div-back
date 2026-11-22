import secrets
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Annotated, Literal
from urllib.parse import quote

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.export import ExportError, generate_expense_pdf, report_filename
from app.models import Expense, Participant, Trip, User
from app.schemas import ExpenseRead, ExpenseReview, ExpenseSummary, ExpenseUserTotal, Login, Token, TripCreate, TripDetails, TripJoin, TripParticipant, TripPublic, TripRead, UserCreate, UserRead
from app.security import create_token, current_user, dummy_hash, password_hash

app = FastAPI(title="DIV API")
app.add_middleware(CORSMiddleware, allow_origins=[origin.strip() for origin in get_settings().cors_origins.split(",")], allow_credentials=False, allow_methods=["GET", "POST", "PUT", "DELETE"], allow_headers=["Authorization", "Content-Type"])


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/auth/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(data: UserCreate, db: Session = Depends(get_db)):
    user = User(nome=data.nome, email=str(data.email).strip().lower(), senha_hash=password_hash.hash(data.senha), perfil=data.perfil)
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Não foi possível cadastrar este email")
    db.refresh(user)
    return user


@app.post("/auth/login", response_model=Token)
def login(data: Login, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == str(data.email).strip().lower()))
    valid = password_hash.verify(data.senha, user.senha_hash if user else dummy_hash)
    if not user or not valid:
        raise HTTPException(status_code=401, detail="Email ou senha inválidos", headers={"WWW-Authenticate": "Bearer"})
    return Token(access_token=create_token(user.id_usuario))


@app.get("/auth/me", response_model=UserRead)
def me(user: User = Depends(current_user)):
    return user


@app.post("/trips", response_model=TripRead, status_code=status.HTTP_201_CREATED)
def create_trip(data: TripCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if user.perfil != "LIDER":
        raise HTTPException(status_code=403, detail="Apenas líderes podem criar viagens")
    # 64 random bits; the database unique constraint is the final collision check.
    trip = Trip(**data.model_dump(), id_lider=user.id_usuario, codigo_acesso=f"DIV-{secrets.token_hex(8).upper()}")
    db.add(trip)
    db.commit()
    db.refresh(trip)
    return trip


@app.get("/trips", response_model=list[TripRead | TripPublic])
def list_trips(user: User = Depends(current_user), db: Session = Depends(get_db)):
    if user.perfil == "LIDER":
        return db.scalars(select(Trip).where(Trip.id_lider == user.id_usuario).order_by(Trip.id_viagem.desc())).all()
    trips = db.scalars(select(Trip).join(Participant, Participant.id_viagem == Trip.id_viagem).where(Participant.id_usuario == user.id_usuario).order_by(Trip.id_viagem.desc())).all()
    return [TripPublic.model_validate(trip) for trip in trips]


@app.post("/trips/join", response_model=TripPublic, status_code=status.HTTP_201_CREATED)
def join_trip(data: TripJoin, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if user.perfil != "TECNICO":
        raise HTTPException(status_code=403, detail="Apenas técnicos podem entrar em viagens")
    # Lock the trip row until commit so a future closing operation cannot race with joining.
    trip = db.scalar(select(Trip).where(Trip.codigo_acesso == data.codigo_acesso).with_for_update())
    if not trip or trip.status != "EM_ANDAMENTO":
        raise HTTPException(status_code=404, detail="Código inválido ou viagem encerrada")
    db.add(Participant(id_viagem=trip.id_viagem, id_usuario=user.id_usuario))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(select(Participant).where(Participant.id_viagem == trip.id_viagem, Participant.id_usuario == user.id_usuario))
        if existing:
            raise HTTPException(status_code=409, detail="Você já participa desta viagem")
        raise
    return trip


@app.get("/trips/{trip_id}", response_model=TripDetails, response_model_exclude_none=True)
def trip_details(trip_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    trip = db.get(Trip, trip_id)
    if not trip:
        raise HTTPException(status_code=404, detail="Viagem não encontrada")
    if user.perfil == "LIDER" and trip.id_lider == user.id_usuario:
        participants = db.scalars(select(User).join(Participant, Participant.id_usuario == User.id_usuario).where(Participant.id_viagem == trip.id_viagem).order_by(User.nome, User.id_usuario)).all()
        return TripDetails(viagem=TripRead.model_validate(trip), participantes=[TripParticipant.model_validate(user), *[TripParticipant.model_validate(p) for p in participants]])
    if user.perfil == "TECNICO":
        membership = db.scalar(select(Participant.id_participante).where(Participant.id_viagem == trip.id_viagem, Participant.id_usuario == user.id_usuario))
        if membership:
            return TripDetails(viagem=TripPublic.model_validate(trip))
    raise HTTPException(status_code=404, detail="Viagem não encontrada")


def expense_access(trip_id: int, user: User, db: Session, lock: bool = False):
    query = select(Trip).where(Trip.id_viagem == trip_id)
    trip = db.scalar(query.with_for_update() if lock else query)
    if trip and user.perfil == "LIDER" and trip.id_lider == user.id_usuario:
        return trip
    if trip and user.perfil == "TECNICO" and db.scalar(select(Participant.id_participante).where(Participant.id_viagem == trip_id, Participant.id_usuario == user.id_usuario)):
        return trip
    raise HTTPException(status_code=404, detail="Viagem não encontrada")


@app.post("/trips/{trip_id}/close", response_model=TripRead)
def close_trip(trip_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if user.perfil != "LIDER":
        raise HTTPException(status_code=404, detail="Viagem não encontrada")
    trip = expense_access(trip_id, user, db, lock=True)
    if trip.status != "EM_ANDAMENTO":
        raise HTTPException(status_code=409, detail="A viagem já está encerrada")
    pending = db.scalar(select(func.count(Expense.id_despesa)).where(Expense.id_viagem == trip_id, Expense.status != "CONFERIDA"))
    if pending:
        raise HTTPException(status_code=409, detail="Não é possível encerrar: existem despesas aguardando conferência ou correção")
    rows = db.execute(select(Expense, User.nome).join(User, Expense.id_usuario == User.id_usuario).where(Expense.id_viagem == trip_id).order_by(User.nome, User.id_usuario, Expense.data_despesa, Expense.id_despesa)).all()
    try:
        participants = db.scalars(select(User).join(Participant, Participant.id_usuario == User.id_usuario).where(Participant.id_viagem == trip_id).order_by(User.nome, User.id_usuario)).all()
        generate_expense_pdf(trip, user, participants, rows)
    except ExportError as exc:
        raise HTTPException(status_code=409, detail=f"Não é possível encerrar: {exc}") from exc
    trip.status = "ENCERRADA"
    trip.encerrada_em = datetime.now(timezone.utc)
    db.commit()
    db.refresh(trip)
    return trip


@app.get("/trips/{trip_id}/export")
def export_trip(trip_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if user.perfil != "LIDER":
        raise HTTPException(status_code=404, detail="Viagem não encontrada")
    trip = expense_access(trip_id, user, db)
    if trip.status != "ENCERRADA":
        raise HTTPException(status_code=409, detail="A exportação está disponível apenas após o encerramento")
    rows = db.execute(select(Expense, User.nome).join(User, Expense.id_usuario == User.id_usuario).where(Expense.id_viagem == trip_id).order_by(User.nome, User.id_usuario, Expense.data_despesa, Expense.id_despesa)).all()
    try:
        participants = db.scalars(select(User).join(Participant, Participant.id_usuario == User.id_usuario).where(Participant.id_viagem == trip_id).order_by(User.nome, User.id_usuario)).all()
        document = generate_expense_pdf(trip, user, participants, rows)
    except ExportError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    filename = quote(report_filename(trip.titulo, trip.destino), safe="")
    return Response(content=document, media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename=relatorio.pdf; filename*=UTF-8''{filename}", "X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"})


def validate_receipt(comprovante: UploadFile):
    contents = comprovante.file.read(5 * 1024 * 1024 + 1)
    if len(contents) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="O comprovante deve ter no máximo 5 MB")
    signatures = {"application/pdf": b"%PDF-", "image/png": b"\x89PNG\r\n\x1a\n", "image/jpeg": b"\xff\xd8\xff"}
    if comprovante.content_type not in signatures or not contents.startswith(signatures[comprovante.content_type]):
        raise HTTPException(status_code=422, detail="Envie um comprovante PDF, PNG ou JPEG válido")
    return contents


@app.post("/trips/{trip_id}/expenses", response_model=ExpenseRead, status_code=201)
def create_expense(
    trip_id: int,
    descricao: Annotated[str, Form(min_length=1, max_length=255)],
    valor: Annotated[Decimal, Form(gt=0, max_digits=12, decimal_places=2)],
    data_despesa: Annotated[date, Form()],
    categoria: Annotated[Literal["ALIMENTACAO", "HOSPEDAGEM", "TRANSPORTE", "ALUGUEL", "OUTROS"], Form()],
    comprovante: Annotated[UploadFile, File()],
    user: User = Depends(current_user), db: Session = Depends(get_db),
):
    trip = expense_access(trip_id, user, db, lock=True)
    if trip.status != "EM_ANDAMENTO":
        raise HTTPException(status_code=409, detail="Não é possível registrar despesas em viagem encerrada")
    if data_despesa < trip.data_inicio:
        raise HTTPException(status_code=422, detail="A data da despesa não pode ser anterior ao início da viagem")
    descricao = descricao.strip()
    if not descricao:
        raise HTTPException(status_code=422, detail="Informe a descrição")
    contents = validate_receipt(comprovante)
    expense = Expense(id_viagem=trip_id, id_usuario=user.id_usuario, descricao=descricao, valor=valor, data_despesa=data_despesa, categoria=categoria, comprovante_conteudo=contents, comprovante_tipo=comprovante.content_type)
    db.add(expense)
    db.commit()
    db.refresh(expense)
    return expense


@app.put("/expenses/{expense_id}", response_model=ExpenseRead)
def update_expense(
    expense_id: int,
    descricao: Annotated[str, Form(min_length=1, max_length=255)],
    valor: Annotated[Decimal, Form(gt=0, max_digits=12, decimal_places=2)],
    data_despesa: Annotated[date, Form()],
    categoria: Annotated[Literal["ALIMENTACAO", "HOSPEDAGEM", "TRANSPORTE", "ALUGUEL", "OUTROS"], Form()],
    comprovante: Annotated[UploadFile | None, File()] = None,
    user: User = Depends(current_user), db: Session = Depends(get_db),
):
    expense = db.get(Expense, expense_id)
    if not expense or expense.id_usuario != user.id_usuario:
        raise HTTPException(status_code=404, detail="Despesa não encontrada")
    trip = expense_access(expense.id_viagem, user, db, lock=True)
    if trip.status != "EM_ANDAMENTO":
        raise HTTPException(status_code=409, detail="Edição indisponível para viagem encerrada")
    if data_despesa < trip.data_inicio:
        raise HTTPException(status_code=422, detail="A data da despesa não pode ser anterior ao início da viagem")
    expense = db.scalar(select(Expense).where(Expense.id_despesa == expense_id).with_for_update().execution_options(populate_existing=True))
    if not expense or expense.id_usuario != user.id_usuario:
        raise HTTPException(status_code=404, detail="Despesa não encontrada")
    if expense.status == "CONFERIDA":
        raise HTTPException(status_code=409, detail="Despesas conferidas não podem ser editadas")
    descricao = descricao.strip()
    if not descricao:
        raise HTTPException(status_code=422, detail="Informe a descrição")
    if comprovante is not None:
        expense.comprovante_conteudo = validate_receipt(comprovante)
        expense.comprovante_tipo = comprovante.content_type
    expense.descricao, expense.valor, expense.data_despesa, expense.categoria = descricao, valor, data_despesa, categoria
    expense.status = "AGUARDANDO_CONFERENCIA"
    expense.motivo_correcao = None
    expense.conferido_por = None
    expense.conferido_em = None
    db.commit()
    db.refresh(expense)
    return expense


@app.get("/trips/{trip_id}/expenses", response_model=list[ExpenseRead])
def list_expenses(trip_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    expense_access(trip_id, user, db)
    query = select(Expense).where(Expense.id_viagem == trip_id)
    if user.perfil == "TECNICO":
        query = query.where(Expense.id_usuario == user.id_usuario)
    return db.scalars(query.order_by(Expense.id_despesa.desc())).all()


@app.get("/trips/{trip_id}/expense-summary", response_model=ExpenseSummary, response_model_exclude_none=True)
def expense_summary(trip_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    expense_access(trip_id, user, db)
    query = select(func.sum(Expense.valor), func.count(Expense.id_despesa)).where(Expense.id_viagem == trip_id)
    if user.perfil == "TECNICO":
        query = query.where(Expense.id_usuario == user.id_usuario)
    total, count = db.execute(query).one()
    if user.perfil == "TECNICO":
        return ExpenseSummary(total=total or Decimal("0.00"), quantidade=count)
    rows = db.execute(select(User.id_usuario, User.nome, func.sum(Expense.valor), func.count(Expense.id_despesa)).join(Expense, Expense.id_usuario == User.id_usuario).where(Expense.id_viagem == trip_id).group_by(User.id_usuario, User.nome).order_by(User.nome, User.id_usuario)).all()
    return ExpenseSummary(total=total or Decimal("0.00"), quantidade=count, por_tecnico=[ExpenseUserTotal(id_usuario=row[0], nome=row[1], total=row[2], quantidade=row[3]) for row in rows])


@app.get("/expenses/{expense_id}/receipt")
def download_receipt(expense_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    expense = db.get(Expense, expense_id)
    if not expense:
        raise HTTPException(status_code=404, detail="Comprovante não encontrado")
    expense_access(expense.id_viagem, user, db)
    if user.perfil == "TECNICO" and expense.id_usuario != user.id_usuario:
        raise HTTPException(status_code=404, detail="Comprovante não encontrado")
    extension = {"application/pdf": "pdf", "image/png": "png", "image/jpeg": "jpg"}[expense.comprovante_tipo]
    return Response(content=expense.comprovante_conteudo, media_type=expense.comprovante_tipo, headers={"Content-Disposition": f'attachment; filename="comprovante-{expense.id_despesa}.{extension}"', "X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"})


@app.post("/expenses/{expense_id}/review", response_model=ExpenseRead)
def review_expense(expense_id: int, data: ExpenseReview, user: User = Depends(current_user), db: Session = Depends(get_db)):
    expense = db.get(Expense, expense_id)
    if not expense or user.perfil != "LIDER":
        raise HTTPException(status_code=404, detail="Despesa não encontrada")
    trip = expense_access(expense.id_viagem, user, db, lock=True)
    if trip.status != "EM_ANDAMENTO":
        raise HTTPException(status_code=409, detail="Conferência indisponível para viagem encerrada")
    expense = db.scalar(select(Expense).where(Expense.id_despesa == expense_id).with_for_update().execution_options(populate_existing=True))
    if not expense:
        raise HTTPException(status_code=404, detail="Despesa não encontrada")
    if expense.status != "AGUARDANDO_CONFERENCIA":
        raise HTTPException(status_code=409, detail="A despesa não está aguardando conferência")
    expense.status = data.decisao
    expense.motivo_correcao = data.motivo_correcao if data.decisao == "PENDENTE_CORRECAO" else None
    expense.conferido_por = user.id_usuario
    expense.conferido_em = datetime.now(timezone.utc)
    db.commit()
    db.refresh(expense)
    return expense


@app.delete("/expenses/{expense_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_expense(expense_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    expense = db.get(Expense, expense_id)
    if not expense:
        raise HTTPException(status_code=404, detail="Despesa não encontrada")
    trip = expense_access(expense.id_viagem, user, db, lock=True)
    if trip.status != "EM_ANDAMENTO":
        raise HTTPException(status_code=409, detail="Exclusão indisponível para viagem encerrada")
    expense = db.scalar(select(Expense).where(Expense.id_despesa == expense_id).with_for_update().execution_options(populate_existing=True))
    if not expense:
        raise HTTPException(status_code=404, detail="Despesa não encontrada")
    if user.perfil == "TECNICO":
        if expense.id_usuario != user.id_usuario:
            raise HTTPException(status_code=404, detail="Despesa não encontrada")
        if expense.status == "CONFERIDA":
            raise HTTPException(status_code=403, detail="Apenas o líder pode excluir despesa conferida")
    elif expense.status != "CONFERIDA":
        raise HTTPException(status_code=403, detail="O líder só pode excluir despesas conferidas")
    db.delete(expense)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
