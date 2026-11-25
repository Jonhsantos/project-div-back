# DIV — Back-end

API REST para gerenciamento de despesas e comprovantes de viagens profissionais. Desenvolvida como Projeto Integrador do curso de Tecnologia em Sistemas para Internet do Senac.

## Sobre o projeto

O DIV centraliza despesas de equipes que trabalham em viagens, reduzindo a perda de comprovantes e facilitando a conferência e a prestação de contas.

## Funcionalidades

- Cadastro, login e consulta do usuário autenticado.
- Criação de viagens pelo líder e ingresso de técnicos por código.
- Registro, consulta, edição e exclusão de despesas conforme permissões.
- Upload e download de comprovantes PDF, PNG e JPEG (até 5 MB por arquivo).
- Conferência de despesas e solicitação de correções.
- Resumo de despesas por viagem e por técnico, conforme perfil.
- Encerramento de viagens e exportação de relatório PDF com comprovantes.

## Tecnologias

Python, FastAPI, PostgreSQL, SQLAlchemy 2, Alembic, psycopg, Pydantic, Uvicorn, PyJWT, Argon2, ReportLab, pypdf, Pillow e pytest.

## Estrutura

```text
app/
├── main.py       # Endpoints e regras de negócio
├── config.py     # Configurações
├── database.py   # Conexão e sessões
├── models.py     # Modelos ORM
├── schemas.py    # Validação e contratos
├── security.py   # Autenticação e segurança
└── export.py     # Relatórios PDF
migrations/      # Migrações Alembic
tests/           # Testes automatizados
requirements.txt
.env.example
alembic.ini
```

## Execução local (Windows PowerShell)

Pré-requisitos: Python compatível com as dependências, Git e PostgreSQL em execução. Crie um banco e um usuário com acesso a ele.

```powershell
git clone https://github.com/Jonhsantos/project-div-back.git
cd project-div-back
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Edite `.env` usando suas credenciais e a chave gerada:

```dotenv
DATABASE_URL=postgresql+psycopg://div:senha_local@localhost:5432/div
SECRET_KEY=substitua-pela-chave-aleatoria-gerada
CORS_ORIGINS=http://localhost:5173
```

```powershell
alembic upgrade head
uvicorn app.main:app --reload
```

- API: http://localhost:8000
- Swagger: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- Health check: http://localhost:8000/health

## Endpoints

| Método | Rota | Finalidade |
|---|---|---|
| GET | `/health` | Saúde da API |
| POST | `/auth/register` | Cadastro |
| POST | `/auth/login` | Login |
| GET | `/auth/me` | Usuário autenticado |
| POST | `/trips` | Criar viagem |
| GET | `/trips` | Listar viagens |
| POST | `/trips/join` | Ingressar por código |
| GET | `/trips/{trip_id}` | Detalhes |
| POST | `/trips/{trip_id}/close` | Encerrar viagem |
| GET | `/trips/{trip_id}/export` | Exportar PDF |
| POST | `/trips/{trip_id}/expenses` | Registrar despesa |
| GET | `/trips/{trip_id}/expenses` | Listar despesas |
| GET | `/trips/{trip_id}/expense-summary` | Resumo |
| PUT | `/expenses/{expense_id}` | Editar |
| DELETE | `/expenses/{expense_id}` | Excluir |
| POST | `/expenses/{expense_id}/review` | Conferir |
| GET | `/expenses/{expense_id}/receipt` | Baixar comprovante |

Rotas protegidas utilizam `Authorization: Bearer <token>`. O token expira em 30 minutos. Cadastro e edição de despesas utilizam multipart/form-data; na edição o comprovante é opcional.

## Regras de negócio

- Perfis: `LIDER` e `TECNICO` (trabalhador). O líder cria viagens; técnicos ingressam por código enquanto abertas.
- O líder responsável consulta todas as despesas da viagem; o técnico consulta apenas as próprias.
- Estados de despesa: `AGUARDANDO_CONFERENCIA`, `CONFERIDA`, `PENDENTE_CORRECAO`.
- Somente o proprietário edita despesas não conferidas; a edição retorna à conferência.
- Técnicos excluem somente despesas próprias não conferidas. O líder responsável exclui somente despesas conferidas.
- Encerramento exige todas as despesas conferidas e comprovantes processáveis para exportação. Viagens sem despesas também podem ser encerradas.
- Viagens encerradas permanecem disponíveis para consulta, mas não aceitam alterações ou ingresso. A exportação é exclusiva do líder responsável após encerramento.
- Exportação limitada a 200 despesas, 50 MB de comprovantes e 500 páginas; arquivos inválidos ou protegidos por senha podem impedir a exportação.

## Testes

Use um ambiente e banco isolados de produção. Confira a configuração dos testes antes de executar:

```bash
python -m pytest
```

## Deploy (Render)

Configure as variáveis de ambiente no serviço, incluindo a URL do PostgreSQL e a origem HTTPS do frontend em `CORS_ORIGINS` (sem barra final; múltiplas origens separadas por vírgula).

- Build: `python -m pip install -r requirements.txt`
- Migração: `alembic upgrade head` em etapa controlada antes da inicialização.
- Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

## Segurança e limitações

Não versione `.env`, senhas ou dados reais. A validação de comprovantes verifica tipo declarado e assinatura inicial, não substitui antivírus nem validação integral. Antes de uso em produção, revise limites de requisição, armazenamento, backups, retenção, revogação de tokens, recuperação de senha e limitação de tentativas. A aplicação é um projeto acadêmico, não uma certificação de segurança.

## Repositório relacionado

[DIV Front-end](https://github.com/Jonhsantos/project-div-front)

## Autor

Jonathan da Silva Santos — Tecnologia em Sistemas para Internet, Senac.
