# DIV — API

Base inicial da API: cadastro, login e consulta do usuário autenticado. Viagens e despesas ainda não foram implementadas.

## Ambiente local (PowerShell)

1. Na pasta `project-div-back`, execute `python -m venv .venv` e `.\.venv\Scripts\Activate.ps1`.
2. Instale as dependências: `python -m pip install -r requirements.txt`.
3. Crie um banco PostgreSQL e copie `.env.example` para `.env`. Configure `DATABASE_URL` e uma chave aleatória exclusiva de pelo menos 32 caracteres em `SECRET_KEY`. Para gerá-la: `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
4. Execute `alembic upgrade head` e inicie com `uvicorn app.main:app --reload`.
5. A documentação interativa fica em `http://127.0.0.1:8000/docs`. Execute os testes com `python -m pytest`.

O token de acesso expira em 30 minutos. Esta base ainda não inclui recuperação de senha, revogação de tokens, limitação de tentativas ou configuração de produção; não a exponha publicamente sem completar a revisão de segurança. Não publique o `.env`.

## Despesas e comprovantes

O comprovante é obrigatório no cadastro de despesas. São aceitos PDF, PNG e JPEG de até 5 MB. O arquivo é armazenado no banco na mesma transação da despesa; seu download é restrito ao técnico responsável e ao líder da viagem. A validação verifica o tipo declarado e a assinatura inicial do arquivo, não sendo uma análise antivírus nem uma validação completa do conteúdo. Antes de usar em produção, avalie limites de requisição, análise de arquivos, armazenamento, backups e retenção.

## Encerramento de viagens

O líder responsável pode encerrar uma viagem apenas quando todas as despesas estiverem conferidas e os comprovantes puderem ser processados para exportação. Uma viagem sem despesas também pode ser encerrada. Após o encerramento, não é permitido ingressar, registrar, editar, conferir ou excluir despesas; a consulta permanece disponível.

O líder responsável pode exportar um PDF com os dados da viagem, seus participantes e o relatório das despesas de todos os técnicos, seguido dos comprovantes. A exportação aceita no máximo 200 despesas, 50 MB de comprovantes e 500 páginas. Um comprovante inválido ou protegido por senha impede a exportação e é identificado pelo número da despesa. O sistema atualmente valida apenas a assinatura dos anexos no envio: antes do uso em produção, devem ser acrescentadas validação integral, análise de arquivos e limites de recursos adequados.
