# Federal Eventos — Django Edition

Migração inicial do sistema Federal Eventos de Streamlit para Django, mantendo Supabase Auth, Supabase PostgreSQL e a identidade visual do `assets/style.css`.

## O que já está pronto neste pacote

- Projeto Django estruturado por módulos.
- Login/logout usando Supabase Auth.
- Sessão web segura pelo Django.
- Middleware `request.app_user`.
- Controle de permissões por `usuarios_app`, `paginas_sistema` e `perfil_permissoes`.
- Sidebar dinâmica por permissão.
- Models `managed = False` apontando para as tabelas atuais do Supabase.
- Dashboard inicial com métricas reais do banco.
- CRUD funcional de Clientes.
- CRUD funcional de Produtos e Patrimônios.
- Orçamentos com ambientes e itens básicos.
- Estoque com vínculo de patrimônio.
- Retirada/Devolução atualizando status operacional.
- Financeiro básico.
- Agenda básica + endpoint JSON para calendário.
- Relatórios gerenciais iniciais.
- CSS original copiado para `static/css/style.css` e camada Django em `static/css/federal_django.css`.

## Como rodar localmente

```bash
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/Mac

pip install -r requirements.txt
copy .env.example .env  # Windows
# cp .env.example .env  # Linux/Mac
```

Preencha o `.env` com:

- `DATABASE_URL` do Supabase PostgreSQL
- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`

Depois rode:

```bash
python manage.py migrate
python manage.py runserver
```

Acesse:

```text
http://127.0.0.1:8000
```

## Observação importante sobre banco

Os models do domínio foram criados com `managed = False`, porque eles apontam para as tabelas já existentes no Supabase. O `migrate` cria apenas tabelas internas do Django, como sessão.

## Segurança

Este pacote não contém `.streamlit/secrets.toml`, `.env` ou chaves reais. Use apenas `.env` localmente ou variáveis de ambiente no deploy.
