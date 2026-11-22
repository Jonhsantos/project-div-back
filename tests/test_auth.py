import os
from decimal import Decimal
from datetime import datetime, timezone
from io import BytesIO
from urllib.parse import quote

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["SECRET_KEY"] = "chave-exclusiva-de-testes-com-mais-de-32-caracteres"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from PIL import Image
from pypdf import PdfReader
from reportlab.pdfgen import canvas

from app.database import Base, get_db
from app.main import app
from app.models import Trip, User


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)

    def override_db():
        with sessions() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as test_client:
        yield test_client, sessions
    app.dependency_overrides.clear()
    engine.dispose()


def test_register_and_login(client):
    http, sessions = client
    data = {"nome": "Ana", "email": "ANA@example.com", "senha": "senha123", "perfil": "LIDER"}
    response = http.post("/auth/register", json=data)
    assert response.status_code == 201
    assert response.json()["email"] == "ana@example.com"
    assert "senha_hash" not in response.json()
    with sessions() as db:
        assert db.scalar(select(User)).senha_hash != data["senha"]
    assert http.post("/auth/register", json=data).status_code == 409
    assert http.post("/auth/login", json={"email": data["email"], "senha": "errada"}).status_code == 401
    login = http.post("/auth/login", json={"email": data["email"], "senha": data["senha"]})
    assert login.status_code == 200
    token = login.json()["access_token"]
    assert http.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).json()["perfil"] == "LIDER"
    assert http.get("/auth/me").status_code == 401
    assert http.get("/auth/me", headers={"Authorization": "Bearer invalido"}).status_code == 401


def test_invalid_registration(client):
    http, _ = client
    assert http.post("/auth/register", json={"nome": " ", "email": "invalido", "senha": "curta", "perfil": "ADMIN"}).status_code == 422


def test_trip_creation_and_owner_isolation(client):
    http, _ = client

    def token(email, perfil):
        assert http.post("/auth/register", json={"nome": "Pessoa", "email": email, "senha": "senha123", "perfil": perfil}).status_code == 201
        response = http.post("/auth/login", json={"email": email, "senha": "senha123"})
        return {"Authorization": "Bearer " + response.json()["access_token"]}

    leader = token("lider@example.com", "LIDER")
    other = token("outro@example.com", "LIDER")
    technician = token("tecnico@example.com", "TECNICO")
    trip = {"titulo": " Instalação ", "destino": "Campinas", "data_inicio": "2026-11-20", "data_fim": "2026-11-21"}
    assert http.post("/trips", json=trip).status_code == 401
    assert http.post("/trips", json=trip, headers=technician).status_code == 403
    assert http.get("/trips", headers=technician).json() == []
    assert http.post("/trips", json={**trip, "data_fim": "2026-11-19"}, headers=leader).status_code == 422
    assert http.post("/trips", json={**trip, "titulo": "  "}, headers=leader).status_code == 422
    created = http.post("/trips", json=trip, headers=leader)
    assert created.status_code == 201
    assert created.json()["titulo"] == "Instalação"
    assert created.json()["status"] == "EM_ANDAMENTO"
    assert created.json()["codigo_acesso"].startswith("DIV-")
    assert len(http.get("/trips", headers=leader).json()) == 1
    assert http.get("/trips", headers=other).json() == []


def test_technician_join_and_visibility(client):
    http, sessions = client

    def token(email, perfil):
        http.post("/auth/register", json={"nome": "Pessoa", "email": email, "senha": "senha123", "perfil": perfil})
        login = http.post("/auth/login", json={"email": email, "senha": "senha123"})
        return {"Authorization": "Bearer " + login.json()["access_token"]}

    leader = token("lider2@example.com", "LIDER")
    technician = token("tecnico2@example.com", "TECNICO")
    other = token("tecnico3@example.com", "TECNICO")
    other_leader = token("lider3@example.com", "LIDER")
    trip = {"titulo": "Instalação", "destino": "Campinas", "data_inicio": "2026-11-20"}
    created = http.post("/trips", json=trip, headers=leader).json()
    code = created["codigo_acesso"]
    assert http.post("/trips/join", json={"codigo_acesso": code}).status_code == 401
    assert http.post("/trips/join", headers=leader, json={"codigo_acesso": code}).status_code == 403
    assert http.post("/trips/join", headers=technician, json={"codigo_acesso": "DIV-INVALIDO"}).status_code == 404
    joined = http.post("/trips/join", headers=technician, json={"codigo_acesso": f"  {code.lower()}  "})
    assert joined.status_code == 201
    assert "codigo_acesso" not in joined.json()
    assert http.post("/trips/join", headers=technician, json={"codigo_acesso": code}).status_code == 409
    listed = http.get("/trips", headers=technician).json()
    assert [item["id_viagem"] for item in listed] == [created["id_viagem"]]
    assert "codigo_acesso" not in listed[0]
    assert http.get("/trips", headers=other).json() == []
    assert http.get("/trips", headers=leader).json()[0]["codigo_acesso"] == code
    trip_id = created["id_viagem"]
    assert http.get(f"/trips/{trip_id}").status_code == 401
    assert http.get(f"/trips/{trip_id}", headers=other).status_code == 404
    assert http.get(f"/trips/{trip_id}", headers=other_leader).status_code == 404
    assert http.get("/trips/999999", headers=leader).status_code == 404
    details = http.get(f"/trips/{trip_id}", headers=leader).json()
    assert details["viagem"]["codigo_acesso"] == code
    assert len(details["participantes"]) == 2
    assert {p["perfil"] for p in details["participantes"]} == {"LIDER", "TECNICO"}
    assert all("email" not in p for p in details["participantes"])
    technician_details = http.get(f"/trips/{trip_id}", headers=technician).json()
    assert technician_details["viagem"]["id_viagem"] == trip_id
    assert "codigo_acesso" not in technician_details["viagem"]
    assert "participantes" not in technician_details
    with sessions() as db:
        db.get(Trip, created["id_viagem"]).status = "ENCERRADA"
        db.commit()
    assert http.post("/trips/join", headers=other, json={"codigo_acesso": code}).status_code == 404
    assert len(http.get("/trips", headers=technician).json()) == 1


def test_expenses_require_receipt_and_permissions(client):
    http, sessions = client

    def token(email, role):
        http.post("/auth/register", json={"nome": email, "email": email, "senha": "senha123", "perfil": role})
        result = http.post("/auth/login", json={"email": email, "senha": "senha123"})
        return {"Authorization": "Bearer " + result.json()["access_token"]}

    leader = token("expense-leader@example.com", "LIDER")
    tech = token("expense-tech@example.com", "TECNICO")
    other = token("expense-other@example.com", "TECNICO")
    outsider = token("expense-outsider@example.com", "LIDER")
    trip = http.post("/trips", headers=leader, json={"titulo": "Viagem", "destino": "Santos", "data_inicio": "2026-11-20"}).json()
    trip_id = trip["id_viagem"]
    for member in (tech, other):
        assert http.post("/trips/join", headers=member, json={"codigo_acesso": trip["codigo_acesso"]}).status_code == 201
    url = f"/trips/{trip_id}/expenses"
    data = {"descricao": "Almoço", "valor": "45.90", "data_despesa": "2026-11-20", "categoria": "ALIMENTACAO"}
    pdf = {"comprovante": ("comprovante.pdf", b"%PDF-1.4\ntest", "application/pdf")}
    assert http.post(url, headers=tech, data=data).status_code == 422
    assert http.post(url, headers=tech, data=data, files={"comprovante": ("fake.pdf", b"not pdf", "application/pdf")}).status_code == 422
    assert http.post(url, headers=tech, data={**data, "valor": "0"}, files=pdf).status_code == 422
    assert http.post(url, headers=outsider, data=data, files=pdf).status_code == 404
    assert http.post(url, headers=tech, data=data, files={"comprovante": ("big.pdf", b"%PDF-" + b"x" * (5 * 1024 * 1024), "application/pdf")}).status_code == 413
    result = http.post(url, headers=tech, data=data, files=pdf)
    assert result.status_code == 201
    assert result.json()["valor"] == "45.90"
    expense_id = result.json()["id_despesa"]
    assert result.json()["status"] == "AGUARDANDO_CONFERENCIA"
    assert len(http.get(url, headers=leader).json()) == 1
    assert http.get(url, headers=other).json() == []
    assert http.get(url, headers=outsider).status_code == 404
    receipt = f"/expenses/{expense_id}/receipt"
    assert http.get(receipt, headers=leader).content == b"%PDF-1.4\ntest"
    assert http.get(receipt, headers=tech).status_code == 200
    assert http.get(receipt, headers=other).status_code == 404
    assert http.get(receipt, headers=outsider).status_code == 404
    review_url = f"/expenses/{expense_id}/review"
    assert http.post(review_url, json={"decisao": "CONFERIDA"}).status_code == 401
    assert http.post(review_url, headers=tech, json={"decisao": "CONFERIDA"}).status_code == 404
    assert http.post(review_url, headers=outsider, json={"decisao": "CONFERIDA"}).status_code == 404
    assert http.post(review_url, headers=leader, json={"decisao": "PENDENTE_CORRECAO", "motivo_correcao": "   "}).status_code == 422
    reviewed = http.post(review_url, headers=leader, json={"decisao": "PENDENTE_CORRECAO", "motivo_correcao": "  Falta detalhar  "})
    assert reviewed.status_code == 200
    assert reviewed.json()["motivo_correcao"] == "Falta detalhar"
    assert reviewed.json()["conferido_por"] and reviewed.json()["conferido_em"]
    assert http.get(url, headers=tech).json()[0]["motivo_correcao"] == "Falta detalhar"
    assert http.post(review_url, headers=leader, json={"decisao": "CONFERIDA"}).status_code == 409
    edit_url = f"/expenses/{expense_id}"
    assert http.put(edit_url, data=data).status_code == 401
    assert http.put(edit_url, headers=other, data=data).status_code == 404
    assert http.put(edit_url, headers=leader, data=data).status_code == 404
    assert http.put(edit_url, headers=tech, data={**data, "valor": "-1"}).status_code == 422
    assert http.put(edit_url, headers=tech, data=data, files={"comprovante": ("fake.pdf", b"fake", "application/pdf")}).status_code == 422
    corrected = http.put(edit_url, headers=tech, data={**data, "descricao": "Almoço corrigido"})
    assert corrected.status_code == 200
    assert corrected.json()["status"] == "AGUARDANDO_CONFERENCIA"
    assert corrected.json()["motivo_correcao"] is None
    assert corrected.json()["conferido_por"] is None and corrected.json()["conferido_em"] is None
    assert http.get(receipt, headers=tech).content == b"%PDF-1.4\ntest"
    png = b"\x89PNG\r\n\x1a\nnew"
    assert http.put(edit_url, headers=tech, data=data, files={"comprovante": ("x.png", png, "image/png")}).status_code == 200
    assert http.get(receipt, headers=tech).content == png
    second = http.post(url, headers=tech, data=data, files=pdf).json()
    approved = http.post(f"/expenses/{second['id_despesa']}/review", headers=leader, json={"decisao": "CONFERIDA"})
    assert approved.status_code == 200 and approved.json()["status"] == "CONFERIDA"
    assert http.put(f"/expenses/{second['id_despesa']}", headers=tech, data=data).status_code == 409
    assert http.delete(f"/expenses/{second['id_despesa']}", headers=tech).status_code == 403
    assert http.delete(f"/expenses/{second['id_despesa']}", headers=outsider).status_code == 404
    assert http.delete(f"/expenses/{second['id_despesa']}", headers=leader).status_code == 204
    assert http.get(f"/expenses/{second['id_despesa']}/receipt", headers=leader).status_code == 404
    third = http.post(url, headers=tech, data=data, files=pdf).json()
    assert http.delete(f"/expenses/{third['id_despesa']}").status_code == 401
    assert http.delete(f"/expenses/{third['id_despesa']}", headers=other).status_code == 404
    assert http.delete(f"/expenses/{third['id_despesa']}", headers=leader).status_code == 403
    disposable = http.post(url, headers=tech, data=data, files=pdf).json()
    assert http.delete(f"/expenses/{disposable['id_despesa']}", headers=tech).status_code == 204
    assert http.delete(f"/expenses/{disposable['id_despesa']}", headers=tech).status_code == 404
    with sessions() as db:
        db.get(Trip, trip_id).status = "ENCERRADA"
        db.commit()
    assert http.post(url, headers=tech, data=data, files=pdf).status_code == 409
    assert http.post(f"/expenses/{third['id_despesa']}/review", headers=leader, json={"decisao": "CONFERIDA"}).status_code == 409
    assert http.put(f"/expenses/{third['id_despesa']}", headers=tech, data=data).status_code == 409
    assert http.delete(f"/expenses/{third['id_despesa']}", headers=tech).status_code == 409


def test_leader_can_register_and_correct_own_expense(client):
    http, _ = client

    def token(email, role):
        http.post("/auth/register", json={"nome": email, "email": email, "senha": "senha123", "perfil": role})
        return {"Authorization": "Bearer " + http.post("/auth/login", json={"email": email, "senha": "senha123"}).json()["access_token"]}

    leader = token("own-leader@example.com", "LIDER")
    outsider = token("own-outsider@example.com", "LIDER")
    tech = token("own-tech@example.com", "TECNICO")
    trip = http.post("/trips", headers=leader, json={"titulo": "Viagem", "destino": "Santos", "data_inicio": "2026-11-20"}).json()
    url = f"/trips/{trip['id_viagem']}/expenses"
    data = {"descricao": "Despesa do líder", "valor": "12.50", "data_despesa": "2026-11-20", "categoria": "OUTROS"}
    receipt = BytesIO()
    page = canvas.Canvas(receipt)
    page.drawString(50, 700, "Comprovante")
    page.save()
    pdf = {"comprovante": ("comprovante.pdf", receipt.getvalue(), "application/pdf")}
    assert http.post(url, headers=leader, data=data).status_code == 422
    assert http.post(url, headers=outsider, data=data, files=pdf).status_code == 404
    assert http.post(url, headers=tech, data=data, files=pdf).status_code == 404
    created = http.post(url, headers=leader, data=data, files=pdf)
    assert created.status_code == 201
    expense = created.json()
    assert expense["status"] == "AGUARDANDO_CONFERENCIA"
    assert http.get(url, headers=leader).json()[0]["id_usuario"] == expense["id_usuario"]
    assert http.put(f"/expenses/{expense['id_despesa']}", headers=outsider, data=data).status_code == 404
    assert http.put(f"/expenses/{expense['id_despesa']}", headers=leader, data={**data, "descricao": "Corrigida"}).status_code == 200
    assert http.post(f"/trips/{trip['id_viagem']}/close", headers=leader).status_code == 409
    assert http.post(f"/expenses/{expense['id_despesa']}/review", headers=leader, json={"decisao": "CONFERIDA"}).status_code == 200
    assert http.post(f"/trips/{trip['id_viagem']}/close", headers=leader).status_code == 200
    assert http.post(url, headers=leader, data=data, files=pdf).status_code == 409
    assert http.get(f"/trips/{trip['id_viagem']}/export", headers=leader).status_code == 200


def test_expense_dates_respect_trip_start_not_expected_end(client):
    http, _ = client

    def token(email, role):
        http.post("/auth/register", json={"nome": email, "email": email, "senha": "senha123", "perfil": role})
        return {"Authorization": "Bearer " + http.post("/auth/login", json={"email": email, "senha": "senha123"}).json()["access_token"]}

    leader = token("dates-leader@example.com", "LIDER")
    tech = token("dates-tech@example.com", "TECNICO")
    trip = http.post("/trips", headers=leader, json={"titulo": "Datas", "destino": "Santos", "data_inicio": "2026-11-22", "data_fim": "2026-11-23"}).json()
    assert http.post("/trips/join", headers=tech, json={"codigo_acesso": trip["codigo_acesso"]}).status_code == 201
    url = f"/trips/{trip['id_viagem']}/expenses"
    pdf = {"comprovante": ("comprovante.pdf", b"%PDF-test", "application/pdf")}
    data = {"descricao": "Item", "valor": "10.00", "data_despesa": "2026-11-21", "categoria": "OUTROS"}
    for user in (leader, tech):
        rejected = http.post(url, headers=user, data=data, files=pdf)
        assert rejected.status_code == 422
        assert "anterior ao início" in rejected.json()["detail"]
        created = http.post(url, headers=user, data={**data, "data_despesa": "2026-11-22"}, files=pdf)
        assert created.status_code == 201
        expense_url = f"/expenses/{created.json()['id_despesa']}"
        assert http.put(expense_url, headers=user, data=data).status_code == 422
        assert http.put(expense_url, headers=user, data={**data, "data_despesa": "2026-11-24"}).status_code == 200
        assert http.post(url, headers=user, data={**data, "data_despesa": "2026-11-24"}, files=pdf).status_code == 201


def test_report_uses_persisted_closing_time_brasilia_and_handles_legacy(client, monkeypatch):
    import importlib
    main = importlib.import_module("app.main")
    http, sessions = client
    http.post("/auth/register", json={"nome": "Líder", "email": "date-report@example.com", "senha": "senha123", "perfil": "LIDER"})
    token = http.post("/auth/login", json={"email": "date-report@example.com", "senha": "senha123"}).json()["access_token"]
    headers = {"Authorization": "Bearer " + token}
    trip = http.post("/trips", headers=headers, json={"titulo": "Datas", "destino": "Santos", "data_inicio": "2026-11-20", "data_fim": "2026-12-01"}).json()

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 11, 22, 1, 30, tzinfo=timezone.utc)

    monkeypatch.setattr(main, "datetime", FixedDateTime)
    closed = http.post(f"/trips/{trip['id_viagem']}/close", headers=headers)
    assert closed.status_code == 200
    assert closed.json()["encerrada_em"].startswith("2026-11-22T01:30:00")
    assert http.post(f"/trips/{trip['id_viagem']}/close", headers=headers).status_code == 409
    for _ in range(2):
        pdf = http.get(f"/trips/{trip['id_viagem']}/export", headers=headers)
        text = "\n".join(page.extract_text() for page in PdfReader(BytesIO(pdf.content)).pages)
        assert "Data prevista de término: 01/12/2026" in text
        assert "Data de encerramento: 21/11/2026" in text
    with sessions() as db:
        db.get(Trip, trip["id_viagem"]).encerrada_em = None
        db.commit()
    pdf = http.get(f"/trips/{trip['id_viagem']}/export", headers=headers)
    text = "\n".join(page.extract_text() for page in PdfReader(BytesIO(pdf.content)).pages)
    assert "Data de encerramento: Não registrada" in text


def test_expense_summary_is_scoped_and_updates(client):
    http, _ = client

    def token(email, role):
        http.post("/auth/register", json={"nome": email, "email": email, "senha": "senha123", "perfil": role})
        return {"Authorization": "Bearer " + http.post("/auth/login", json={"email": email, "senha": "senha123"}).json()["access_token"]}

    leader = token("summary-leader@example.com", "LIDER")
    tech = token("summary-tech@example.com", "TECNICO")
    other = token("summary-other@example.com", "TECNICO")
    outsider = token("summary-outsider@example.com", "LIDER")
    trip = http.post("/trips", headers=leader, json={"titulo": "Teste", "destino": "Santos", "data_inicio": "2026-11-20"}).json()
    for member in (tech, other):
        assert http.post("/trips/join", headers=member, json={"codigo_acesso": trip["codigo_acesso"]}).status_code == 201
    summary_url = f"/trips/{trip['id_viagem']}/expense-summary"
    assert http.get(summary_url).status_code == 401
    assert http.get(summary_url, headers=outsider).status_code == 404
    assert Decimal(http.get(summary_url, headers=leader).json()["total"]) == Decimal("0.00")
    data = {"descricao": "Item", "valor": "0.10", "data_despesa": "2026-11-20", "categoria": "OUTROS"}
    pdf = {"comprovante": ("a.pdf", b"%PDF-test", "application/pdf")}
    expense_url = f"/trips/{trip['id_viagem']}/expenses"
    one = http.post(expense_url, headers=tech, data=data, files=pdf).json()
    two = http.post(expense_url, headers=other, data={**data, "valor": "0.20"}, files=pdf).json()
    leader_summary = http.get(summary_url, headers=leader).json()
    assert Decimal(leader_summary["total"]) == Decimal("0.30") and leader_summary["quantidade"] == 2
    assert len(leader_summary["por_tecnico"]) == 2
    own_summary = http.get(summary_url, headers=tech).json()
    assert Decimal(own_summary["total"]) == Decimal("0.10") and "por_tecnico" not in own_summary
    assert http.put(f"/expenses/{one['id_despesa']}", headers=tech, data={**data, "valor": "2.25"}).status_code == 200
    assert Decimal(http.get(summary_url, headers=leader).json()["total"]) == Decimal("2.45")
    assert http.delete(f"/expenses/{two['id_despesa']}", headers=other).status_code == 204
    assert Decimal(http.get(summary_url, headers=leader).json()["total"]) == Decimal("2.25")


def test_trip_close_requires_review_and_preserves_read_only_access(client):
    http, _ = client

    def token(email, role):
        http.post("/auth/register", json={"nome": email, "email": email, "senha": "senha123", "perfil": role})
        return {"Authorization": "Bearer " + http.post("/auth/login", json={"email": email, "senha": "senha123"}).json()["access_token"]}

    leader = token("close-leader@example.com", "LIDER")
    outsider = token("close-outsider@example.com", "LIDER")
    tech = token("close-tech@example.com", "TECNICO")
    newcomer = token("close-new@example.com", "TECNICO")
    trip = http.post("/trips", headers=leader, json={"titulo": "Teste", "destino": "Santos", "data_inicio": "2026-11-20"}).json()
    trip_id = trip["id_viagem"]
    url = f"/trips/{trip_id}/close"
    assert http.post(url).status_code == 401
    assert http.post(url, headers=outsider).status_code == 404
    assert http.post(url, headers=tech).status_code == 404
    assert http.post("/trips/join", headers=tech, json={"codigo_acesso": trip["codigo_acesso"]}).status_code == 201
    data = {"descricao": "Item", "valor": "10.00", "data_despesa": "2026-11-20", "categoria": "OUTROS"}
    receipt = BytesIO()
    page = canvas.Canvas(receipt)
    page.drawString(50, 750, "Comprovante")
    page.save()
    pdf = {"comprovante": ("a.pdf", receipt.getvalue(), "application/pdf")}
    expense = http.post(f"/trips/{trip_id}/expenses", headers=tech, data=data, files=pdf).json()
    expense_id = expense["id_despesa"]
    assert http.post(url, headers=leader).status_code == 409
    assert http.post(f"/expenses/{expense_id}/review", headers=leader, json={"decisao": "PENDENTE_CORRECAO", "motivo_correcao": "Corrigir"}).status_code == 200
    assert http.post(url, headers=leader).status_code == 409
    assert http.put(f"/expenses/{expense_id}", headers=tech, data=data).status_code == 200
    assert http.post(f"/expenses/{expense_id}/review", headers=leader, json={"decisao": "CONFERIDA"}).status_code == 200
    assert http.post(url, headers=leader).json()["status"] == "ENCERRADA"
    assert http.post(url, headers=leader).status_code == 409
    assert http.get(f"/trips/{trip_id}", headers=tech).json()["viagem"]["status"] == "ENCERRADA"
    assert http.get(f"/trips/{trip_id}/expenses", headers=tech).status_code == 200
    assert http.get(f"/expenses/{expense_id}/receipt", headers=leader).status_code == 200
    assert http.post("/trips/join", headers=newcomer, json={"codigo_acesso": trip["codigo_acesso"]}).status_code == 404
    assert http.post(f"/trips/{trip_id}/expenses", headers=tech, data=data, files=pdf).status_code == 409
    assert http.put(f"/expenses/{expense_id}", headers=tech, data=data).status_code == 409
    assert http.post(f"/expenses/{expense_id}/review", headers=leader, json={"decisao": "CONFERIDA"}).status_code == 409
    assert http.delete(f"/expenses/{expense_id}", headers=leader).status_code == 409
    empty = http.post("/trips", headers=leader, json={"titulo": "Vazia", "destino": "Santos", "data_inicio": "2026-11-20"}).json()
    assert http.post(f"/trips/{empty['id_viagem']}/close", headers=leader).status_code == 200


def test_export_report_with_receipts_and_authorization(client):
    http, _ = client

    def token(email, role):
        http.post("/auth/register", json={"nome": email, "email": email, "senha": "senha123", "perfil": role})
        return {"Authorization": "Bearer " + http.post("/auth/login", json={"email": email, "senha": "senha123"}).json()["access_token"]}

    leader = token("export-leader@example.com", "LIDER")
    outsider = token("export-outsider@example.com", "LIDER")
    tech = token("export-tech@example.com", "TECNICO")
    tech2 = token("export-tech2@example.com", "TECNICO")
    trip = http.post("/trips", headers=leader, json={"titulo": "Viagem de teste", "destino": "Santos", "data_inicio": "2026-11-20", "data_fim": "2026-11-22", "descricao": "Instalacao de equipamentos"}).json()
    trip_id = trip["id_viagem"]
    export_url = f"/trips/{trip_id}/export"
    assert http.get(export_url).status_code == 401
    assert http.get(export_url, headers=outsider).status_code == 404
    assert http.get(export_url, headers=tech).status_code == 404
    assert http.get(export_url, headers=leader).status_code == 409
    assert http.post("/trips/join", headers=tech, json={"codigo_acesso": trip["codigo_acesso"]}).status_code == 201
    assert http.post("/trips/join", headers=tech2, json={"codigo_acesso": trip["codigo_acesso"]}).status_code == 201
    receipt = BytesIO()
    pdf = canvas.Canvas(receipt)
    pdf.drawString(50, 750, "COMPROVANTE PAGINA UM")
    pdf.showPage()
    pdf.drawString(50, 750, "COMPROVANTE PAGINA DOIS")
    pdf.save()
    image = BytesIO()
    Image.new("RGB", (10, 10), "red").save(image, format="PNG")
    jpeg = BytesIO()
    Image.new("RGB", (10, 10), "blue").save(jpeg, format="JPEG")
    data = {"descricao": "Almoco teste", "valor": "12.30", "data_despesa": "2026-11-20", "categoria": "ALIMENTACAO"}
    expenses_url = f"/trips/{trip_id}/expenses"
    for filename, contents, mime in [("x.pdf", receipt.getvalue(), "application/pdf"), ("x.png", image.getvalue(), "image/png")]:
        result = http.post(expenses_url, headers=tech, data=data, files={"comprovante": (filename, contents, mime)})
        assert result.status_code == 201
        assert http.post(f"/expenses/{result.json()['id_despesa']}/review", headers=leader, json={"decisao": "CONFERIDA"}).status_code == 200
    second_tech = http.post(expenses_url, headers=tech2, data={**data, "descricao": "Despesa outro tecnico"}, files={"comprovante": ("x.jpg", jpeg.getvalue(), "image/jpeg")})
    assert second_tech.status_code == 201
    assert http.post(f"/expenses/{second_tech.json()['id_despesa']}/review", headers=leader, json={"decisao": "CONFERIDA"}).status_code == 200
    assert http.post(f"/trips/{trip_id}/close", headers=leader).status_code == 200
    result = http.get(export_url, headers=leader)
    assert result.status_code == 200 and result.headers["content-type"] == "application/pdf"
    assert "filename*=UTF-8''" + quote("Viagem de teste Santos relatório.pdf", safe="") in result.headers["content-disposition"]
    assert result.headers["cache-control"] == "no-store"
    pages = PdfReader(BytesIO(result.content)).pages
    assert len(pages) == 6
    assert "Almoco teste" in pages[0].extract_text()
    assert "export-tech@example.com" in pages[0].extract_text()
    assert "export-tech2@example.com" in pages[0].extract_text()
    report_text = pages[0].extract_text()
    assert "Viagem de teste" in report_text and "Santos" in report_text
    assert "20/11/2026" in report_text and "22/11/2026" in report_text
    assert "Instalacao de equipamentos" in report_text
    assert "export-leader@example.com" in report_text and "ENCERRADA" in report_text
    assert trip["codigo_acesso"] in report_text
    texts = [page.extract_text() for page in pages]
    assert any("COMPROVANTE PAGINA UM" in text for text in texts)
    assert any("COMPROVANTE PAGINA DOIS" in text for text in texts)
    assert http.get(export_url, headers=tech).status_code == 404
    assert http.get(export_url, headers=outsider).status_code == 404


def test_export_fails_for_invalid_receipt(client):
    http, sessions = client
    def token(email, role):
        http.post("/auth/register", json={"nome": email, "email": email, "senha": "senha123", "perfil": role})
        return {"Authorization": "Bearer " + http.post("/auth/login", json={"email": email, "senha": "senha123"}).json()["access_token"]}
    leader = token("broken-leader@example.com", "LIDER")
    tech = token("broken-tech@example.com", "TECNICO")
    trip = http.post("/trips", headers=leader, json={"titulo": "Teste", "destino": "Santos", "data_inicio": "2026-11-20"}).json()
    trip_id = trip["id_viagem"]
    http.post("/trips/join", headers=tech, json={"codigo_acesso": trip["codigo_acesso"]})
    data = {"descricao": "Item", "valor": "1.00", "data_despesa": "2026-11-20", "categoria": "OUTROS"}
    item = http.post(f"/trips/{trip_id}/expenses", headers=tech, data=data, files={"comprovante": ("x.pdf", b"%PDF-broken", "application/pdf")}).json()
    http.post(f"/expenses/{item['id_despesa']}/review", headers=leader, json={"decisao": "CONFERIDA"})
    blocked = http.post(f"/trips/{trip_id}/close", headers=leader)
    assert blocked.status_code == 409 and f"#{item['id_despesa']}" in blocked.json()["detail"]
    with sessions() as db:
        db.get(Trip, trip_id).status = "ENCERRADA"
        db.commit()
    result = http.get(f"/trips/{trip_id}/export", headers=leader)
    assert result.status_code == 422 and f"#{item['id_despesa']}" in result.json()["detail"]
