# AGENTS.md — DIV Back-end

## Contexto e arquitetura

API REST do DIV para despesas de viagens profissionais. Preserve Python, FastAPI, PostgreSQL, SQLAlchemy 2, Alembic, Pydantic, psycopg, JWT, Argon2 e pytest. A integração ocorre com https://github.com/Jonhsantos/project-div-front.

- `app/main.py`: endpoints e regras atuais.
- `app/models.py` e `app/schemas.py`: persistência e contratos.
- `app/database.py` e `app/config.py`: sessões e configuração.
- `app/security.py`: autenticação; `app/export.py`: relatórios PDF.
- `migrations/`: evolução do banco; `tests/`: testes.

## Fluxo obrigatório

1. Leia README, AGENTS e arquivos relevantes. Inspecione o estado do Git e preserve alterações do usuário.
2. Trabalhe em etapas pequenas e coerentes; não implemente requisitos não solicitados.
3. Preserve contratos da API. Avalie impactos no frontend antes de modificá-los.
4. Implemente com tipagem, código limpo, responsabilidades claras e testes de regressão.
5. Execute verificações pertinentes e informe alterações, resultados e pendências reais.

## Regras obrigatórias de negócio

- Perfis `LIDER` e `TECNICO`: somente líderes criam viagens; técnicos ingressam por código em viagens abertas.
- Verifique vínculo, perfil e propriedade no servidor em todas as operações protegidas.
- Líder responsável consulta despesas da viagem; técnico consulta apenas as próprias.
- Comprovante obrigatório no cadastro: PDF, PNG ou JPEG de até 5 MB.
- Use Decimal para valores monetários; valide valores positivos e datas.
- Preserve os estados `AGUARDANDO_CONFERENCIA`, `CONFERIDA` e `PENDENTE_CORRECAO`.
- Somente o proprietário edita despesas não conferidas; edição retorna à conferência.
- Técnico exclui apenas despesas próprias não conferidas; líder responsável exclui somente despesas conferidas.
- Encerramento exige despesas conferidas e relatório processável; viagem vazia pode ser encerrada.
- Viagens encerradas são somente leitura; exportação exclusiva do líder responsável após encerramento.

## Segurança e persistência

- Preserve validações Pydantic, hash Argon2, JWT e autorização por recurso.
- Não enfraqueça autenticação, CORS ou validação de arquivos para contornar erros.
- Use consultas parametrizadas, transações, rollback e tratamento de erros sem vazar detalhes internos.
- Preserve locks e ordem de aquisição em operações concorrentes.
- Alterações de esquema exigem migração Alembic revisada; não destrua dados para corrigir migrações.
- Configure CORS com origens autorizadas. Não exponha segredos, tokens, comprovantes ou dados pessoais em logs e commits.
- Preserve limites de exportação: 200 despesas, 50 MB de comprovantes e 500 páginas. Não trate assinatura inicial como antivírus.
- Não faça deploy, push, migração em produção ou operações destrutivas sem autorização.

## Testes e critérios de conclusão

- `python -m pip install -r requirements.txt`
- `alembic upgrade head` (banco local autorizado)
- `uvicorn app.main:app --reload`
- `python -m pytest` (ambiente isolado)

Cubra sucesso, entradas inválidas, isolamento entre usuários, permissões, estados e concorrência quando pertinente. Confira `/docs` e `/health` quando necessário. Atualize a documentação e não declare testes aprovados sem executá-los.

## Git e comunicação

Use commits semânticos quando solicitado: feat, fix, refactor, docs, test, chore. Relate arquivos alterados, decisões técnicas, comandos executados e limitações. Não invente funcionalidades ou resultados.
