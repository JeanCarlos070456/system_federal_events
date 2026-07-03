-- ============================================================
-- FEDERAL EVENTOS - MVP 1
-- Schema inicial Supabase/PostgreSQL
-- Streamlit + Supabase Auth + PostgreSQL
-- ============================================================

-- Extensão para UUID
create extension if not exists pgcrypto;

-- ============================================================
-- 1. FUNÇÕES GERAIS
-- ============================================================

create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

-- ============================================================
-- 2. PERFIS, USUÁRIOS E PERMISSÕES
-- ============================================================

create table if not exists public.perfis (
    id uuid primary key default gen_random_uuid(),
    nome text not null unique,
    descricao text,
    ativo boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

drop trigger if exists trg_perfis_updated_at on public.perfis;
create trigger trg_perfis_updated_at
before update on public.perfis
for each row execute function public.set_updated_at();


create table if not exists public.usuarios_app (
    id uuid primary key references auth.users(id) on delete cascade,
    nome text not null,
    email text not null unique,
    perfil text not null references public.perfis(nome),
    telefone text,
    cargo text,
    ativo boolean not null default true,
    ultimo_login timestamptz,
    observacoes text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

drop trigger if exists trg_usuarios_app_updated_at on public.usuarios_app;
create trigger trg_usuarios_app_updated_at
before update on public.usuarios_app
for each row execute function public.set_updated_at();


create table if not exists public.paginas_sistema (
    id uuid primary key default gen_random_uuid(),
    nome text not null unique,
    slug text not null unique,
    ordem integer not null default 0,
    ativo boolean not null default true,
    created_at timestamptz not null default now()
);


create table if not exists public.perfil_permissoes (
    id uuid primary key default gen_random_uuid(),
    perfil text not null references public.perfis(nome) on delete cascade,
    pagina text not null references public.paginas_sistema(nome) on delete cascade,
    pode_acessar boolean not null default true,
    pode_criar boolean not null default false,
    pode_editar boolean not null default false,
    pode_excluir boolean not null default false,
    pode_exportar boolean not null default false,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint uq_perfil_pagina unique (perfil, pagina)
);

drop trigger if exists trg_perfil_permissoes_updated_at on public.perfil_permissoes;
create trigger trg_perfil_permissoes_updated_at
before update on public.perfil_permissoes
for each row execute function public.set_updated_at();


-- ============================================================
-- 3. FUNÇÕES DE PERMISSÃO
-- ============================================================

create or replace function public.current_user_perfil()
returns text
language sql
security definer
set search_path = public
as $$
    select ua.perfil
    from public.usuarios_app ua
    where ua.id = auth.uid()
      and ua.ativo = true
    limit 1;
$$;


create or replace function public.is_admin_empresa()
returns boolean
language sql
security definer
set search_path = public
as $$
    select exists (
        select 1
        from public.usuarios_app ua
        where ua.id = auth.uid()
          and ua.ativo = true
          and ua.perfil = 'admin_empresa'
    );
$$;


create or replace function public.can_access_page(page_name text)
returns boolean
language sql
security definer
set search_path = public
as $$
    select exists (
        select 1
        from public.usuarios_app ua
        join public.perfil_permissoes pp
          on pp.perfil = ua.perfil
        where ua.id = auth.uid()
          and ua.ativo = true
          and pp.pagina = page_name
          and pp.pode_acessar = true
    );
$$;


-- ============================================================
-- 4. CLIENTES
-- ============================================================

create table if not exists public.clientes (
    id uuid primary key default gen_random_uuid(),

    nome text not null,
    tipo_pessoa text not null default 'juridica'
        check (tipo_pessoa in ('fisica', 'juridica')),

    documento text unique,
    inscricao_estadual text,
    responsavel_nome text,
    responsavel_cargo text,

    telefone text,
    whatsapp text,
    email text,

    cep text,
    endereco text,
    numero text,
    complemento text,
    bairro text,
    cidade text,
    uf text,

    status text not null default 'Ativo'
        check (status in ('Ativo', 'Inativo', 'Bloqueado', 'Prospecto')),

    origem text,
    observacoes text,

    criado_por uuid references public.usuarios_app(id),
    atualizado_por uuid references public.usuarios_app(id),

    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists idx_clientes_nome on public.clientes using gin (to_tsvector('portuguese', coalesce(nome, '')));
create index if not exists idx_clientes_documento on public.clientes(documento);
create index if not exists idx_clientes_status on public.clientes(status);

drop trigger if exists trg_clientes_updated_at on public.clientes;
create trigger trg_clientes_updated_at
before update on public.clientes
for each row execute function public.set_updated_at();


-- ============================================================
-- 5. PRODUTOS / EQUIPAMENTOS
-- ============================================================

create table if not exists public.produtos (
    id uuid primary key default gen_random_uuid(),

    codigo text not null unique,
    nome text not null,
    categoria text,
    subcategoria text,
    marca text,
    modelo text,

    descricao text,
    especificacoes text,

    valor_diaria numeric(12,2) not null default 0,
    valor_semanal numeric(12,2) not null default 0,
    valor_mensal numeric(12,2) not null default 0,

    quantidade_total integer not null default 0 check (quantidade_total >= 0),
    quantidade_disponivel integer not null default 0 check (quantidade_disponivel >= 0),

    status text not null default 'Disponível'
        check (status in ('Disponível', 'Reservado', 'Locado', 'Manutenção', 'Inativo', 'Danificado')),

    localizacao text,
    observacoes text,

    criado_por uuid references public.usuarios_app(id),
    atualizado_por uuid references public.usuarios_app(id),

    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists idx_produtos_codigo on public.produtos(codigo);
create index if not exists idx_produtos_nome on public.produtos using gin (to_tsvector('portuguese', coalesce(nome, '')));
create index if not exists idx_produtos_categoria on public.produtos(categoria);
create index if not exists idx_produtos_status on public.produtos(status);

drop trigger if exists trg_produtos_updated_at on public.produtos;
create trigger trg_produtos_updated_at
before update on public.produtos
for each row execute function public.set_updated_at();


create table if not exists public.produto_patrimonios (
    id uuid primary key default gen_random_uuid(),

    produto_id uuid not null references public.produtos(id) on delete cascade,
    cod_patrimonio text not null unique,

    numero_serie text,
    status text not null default 'Disponível'
        check (status in ('Disponível', 'Reservado', 'Locado', 'Manutenção', 'Inativo', 'Danificado', 'Extraviado')),

    localizacao text,
    observacoes text,

    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists idx_produto_patrimonios_produto_id on public.produto_patrimonios(produto_id);
create index if not exists idx_produto_patrimonios_cod on public.produto_patrimonios(cod_patrimonio);
create index if not exists idx_produto_patrimonios_status on public.produto_patrimonios(status);

drop trigger if exists trg_produto_patrimonios_updated_at on public.produto_patrimonios;
create trigger trg_produto_patrimonios_updated_at
before update on public.produto_patrimonios
for each row execute function public.set_updated_at();


-- ============================================================
-- 6. ORÇAMENTOS
-- ============================================================

create table if not exists public.orcamentos (
    id uuid primary key default gen_random_uuid(),

    codigo text not null unique,

    cliente_id uuid references public.clientes(id) on delete set null,
    cliente_nome text,
    cliente_documento text,
    responsavel_cliente text,

    evento_nome text not null,
    local_evento text,

    data_envio date,
    validade_dias integer not null default 7 check (validade_dias >= 0),
    data_montagem date,
    data_inicio date,
    data_fim date,

    status text not null default 'Rascunho'
        check (status in ('Rascunho', 'Enviado', 'Aprovado', 'Reprovado', 'Cancelado', 'Finalizado')),

    financeiro text not null default 'Pendente'
        check (financeiro in ('Pendente', 'Parcial', 'Pago', 'Atrasado', 'Cancelado')),

    valor_total numeric(14,2) not null default 0,
    valor_desconto numeric(14,2) not null default 0,
    valor_caucao numeric(14,2) not null default 0,
    valor_final numeric(14,2) not null default 0,

    observacoes text,
    condicoes_pagamento text,

    criado_por uuid references public.usuarios_app(id),
    atualizado_por uuid references public.usuarios_app(id),

    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists idx_orcamentos_codigo on public.orcamentos(codigo);
create index if not exists idx_orcamentos_cliente_id on public.orcamentos(cliente_id);
create index if not exists idx_orcamentos_status on public.orcamentos(status);
create index if not exists idx_orcamentos_financeiro on public.orcamentos(financeiro);
create index if not exists idx_orcamentos_datas on public.orcamentos(data_inicio, data_fim, data_montagem);

drop trigger if exists trg_orcamentos_updated_at on public.orcamentos;
create trigger trg_orcamentos_updated_at
before update on public.orcamentos
for each row execute function public.set_updated_at();


create table if not exists public.orcamento_ambientes (
    id uuid primary key default gen_random_uuid(),

    orcamento_id uuid not null references public.orcamentos(id) on delete cascade,

    tipo text not null default 'sala'
        check (tipo in ('sala', 'auditorio', 'credenciamento', 'outro')),

    nome text not null,
    ordem integer not null default 0,
    observacoes text,

    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists idx_orcamento_ambientes_orcamento_id on public.orcamento_ambientes(orcamento_id);

drop trigger if exists trg_orcamento_ambientes_updated_at on public.orcamento_ambientes;
create trigger trg_orcamento_ambientes_updated_at
before update on public.orcamento_ambientes
for each row execute function public.set_updated_at();


create table if not exists public.orcamento_itens (
    id uuid primary key default gen_random_uuid(),

    orcamento_id uuid not null references public.orcamentos(id) on delete cascade,
    ambiente_id uuid references public.orcamento_ambientes(id) on delete cascade,
    produto_id uuid references public.produtos(id) on delete set null,

    equipamento text not null,
    descricao text,

    quantidade integer not null default 1 check (quantidade > 0),
    dias_uso integer not null default 1 check (dias_uso > 0),

    valor_diaria numeric(12,2) not null default 0,
    desconto numeric(12,2) not null default 0,
    valor_total numeric(14,2) not null default 0,

    ordem integer not null default 0,

    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists idx_orcamento_itens_orcamento_id on public.orcamento_itens(orcamento_id);
create index if not exists idx_orcamento_itens_ambiente_id on public.orcamento_itens(ambiente_id);
create index if not exists idx_orcamento_itens_produto_id on public.orcamento_itens(produto_id);

drop trigger if exists trg_orcamento_itens_updated_at on public.orcamento_itens;
create trigger trg_orcamento_itens_updated_at
before update on public.orcamento_itens
for each row execute function public.set_updated_at();


-- ============================================================
-- 7. ESTOQUE / VÍNCULOS DE COD/PATRIMÔNIO
-- ============================================================

create table if not exists public.estoque_vinculos (
    id uuid primary key default gen_random_uuid(),

    orcamento_id uuid not null references public.orcamentos(id) on delete cascade,
    ambiente_id uuid references public.orcamento_ambientes(id) on delete set null,
    item_id uuid not null references public.orcamento_itens(id) on delete cascade,
    produto_id uuid references public.produtos(id) on delete set null,
    patrimonio_id uuid references public.produto_patrimonios(id) on delete set null,

    cod_patrimonio text not null,
    descricao text,

    quantidade integer not null default 1 check (quantidade > 0),

    status text not null default 'Vinculado'
        check (status in ('Vinculado', 'Separado', 'Retirado', 'Devolvido', 'Danificado', 'Cancelado')),

    vinculado_por uuid references public.usuarios_app(id),
    vinculado_em timestamptz not null default now(),

    observacoes text,

    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),

    constraint uq_estoque_vinculo_item_cod unique (item_id, cod_patrimonio)
);

create unique index if not exists uq_estoque_cod_ativo
on public.estoque_vinculos(cod_patrimonio)
where status in ('Vinculado', 'Separado', 'Retirado');

create index if not exists idx_estoque_vinculos_orcamento_id on public.estoque_vinculos(orcamento_id);
create index if not exists idx_estoque_vinculos_item_id on public.estoque_vinculos(item_id);
create index if not exists idx_estoque_vinculos_cod on public.estoque_vinculos(cod_patrimonio);
create index if not exists idx_estoque_vinculos_status on public.estoque_vinculos(status);

drop trigger if exists trg_estoque_vinculos_updated_at on public.estoque_vinculos;
create trigger trg_estoque_vinculos_updated_at
before update on public.estoque_vinculos
for each row execute function public.set_updated_at();


-- ============================================================
-- 8. AGENDA
-- ============================================================

create table if not exists public.agenda_eventos (
    id uuid primary key default gen_random_uuid(),

    orcamento_id uuid references public.orcamentos(id) on delete cascade,

    titulo text not null,
    tipo_evento text not null default 'Evento'
        check (tipo_evento in ('Evento', 'Montagem', 'Retirada', 'Devolução', 'Reunião', 'Outro')),

    data_inicio date not null,
    data_fim date,
    horario_inicio time,
    horario_fim time,

    local_evento text,
    status text not null default 'Agendado'
        check (status in ('Agendado', 'Em andamento', 'Concluído', 'Cancelado', 'Atrasado')),

    responsavel_id uuid references public.usuarios_app(id),
    observacoes text,

    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists idx_agenda_eventos_orcamento_id on public.agenda_eventos(orcamento_id);
create index if not exists idx_agenda_eventos_datas on public.agenda_eventos(data_inicio, data_fim);
create index if not exists idx_agenda_eventos_status on public.agenda_eventos(status);

drop trigger if exists trg_agenda_eventos_updated_at on public.agenda_eventos;
create trigger trg_agenda_eventos_updated_at
before update on public.agenda_eventos
for each row execute function public.set_updated_at();


-- ============================================================
-- 9. FINANCEIRO
-- ============================================================

create table if not exists public.financeiro_movimentos (
    id uuid primary key default gen_random_uuid(),

    orcamento_id uuid references public.orcamentos(id) on delete cascade,
    cliente_id uuid references public.clientes(id) on delete set null,

    tipo text not null default 'Receita'
        check (tipo in ('Receita', 'Despesa', 'Estorno', 'Ajuste')),

    categoria text,
    descricao text not null,

    valor numeric(14,2) not null default 0,

    forma_pagamento text,
    status text not null default 'Pendente'
        check (status in ('Pendente', 'Pago', 'Parcial', 'Atrasado', 'Cancelado')),

    data_vencimento date,
    data_pagamento date,

    comprovante_url text,
    observacoes text,

    criado_por uuid references public.usuarios_app(id),
    atualizado_por uuid references public.usuarios_app(id),

    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists idx_financeiro_orcamento_id on public.financeiro_movimentos(orcamento_id);
create index if not exists idx_financeiro_cliente_id on public.financeiro_movimentos(cliente_id);
create index if not exists idx_financeiro_status on public.financeiro_movimentos(status);
create index if not exists idx_financeiro_datas on public.financeiro_movimentos(data_vencimento, data_pagamento);

drop trigger if exists trg_financeiro_movimentos_updated_at on public.financeiro_movimentos;
create trigger trg_financeiro_movimentos_updated_at
before update on public.financeiro_movimentos
for each row execute function public.set_updated_at();


-- ============================================================
-- 10. RETIRADA E DEVOLUÇÃO
-- ============================================================

create table if not exists public.retirada_devolucao (
    id uuid primary key default gen_random_uuid(),

    orcamento_id uuid not null references public.orcamentos(id) on delete cascade,
    estoque_vinculo_id uuid references public.estoque_vinculos(id) on delete set null,
    item_id uuid references public.orcamento_itens(id) on delete set null,
    produto_id uuid references public.produtos(id) on delete set null,

    cod_patrimonio text,

    tipo_movimento text not null
        check (tipo_movimento in ('Retirada', 'Devolução')),

    data_movimento timestamptz not null default now(),

    estado text not null default 'Bom'
        check (estado in ('Novo', 'Bom', 'Regular', 'Danificado', 'Extraviado')),

    acessorios_conferidos boolean not null default false,
    checklist jsonb not null default '{}'::jsonb,

    dias_atraso integer not null default 0 check (dias_atraso >= 0),
    multa_dia numeric(12,2) not null default 0,
    valor_multa numeric(14,2) not null default 0,

    responsavel_id uuid references public.usuarios_app(id),
    observacoes text,

    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists idx_retirada_devolucao_orcamento_id on public.retirada_devolucao(orcamento_id);
create index if not exists idx_retirada_devolucao_tipo on public.retirada_devolucao(tipo_movimento);
create index if not exists idx_retirada_devolucao_cod on public.retirada_devolucao(cod_patrimonio);

drop trigger if exists trg_retirada_devolucao_updated_at on public.retirada_devolucao;
create trigger trg_retirada_devolucao_updated_at
before update on public.retirada_devolucao
for each row execute function public.set_updated_at();


-- ============================================================
-- 11. ARQUIVOS / ANEXOS
-- ============================================================

create table if not exists public.arquivos (
    id uuid primary key default gen_random_uuid(),

    entidade text not null
        check (entidade in (
            'cliente',
            'produto',
            'orcamento',
            'financeiro',
            'retirada_devolucao',
            'agenda',
            'sistema'
        )),

    entidade_id uuid,

    tipo_arquivo text
        check (tipo_arquivo in (
            'imagem',
            'video',
            'pdf',
            'contrato',
            'comprovante',
            'documento',
            'relatorio',
            'outro'
        )),

    nome_original text not null,
    nome_armazenado text,
    extensao text,
    mime_type text,
    tamanho_bytes bigint,

    storage_provider text not null default 'supabase'
        check (storage_provider in ('supabase', 'google_drive', 'local', 'externo')),

    bucket text,
    path text,
    public_url text,

    enviado_por uuid references public.usuarios_app(id),

    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists idx_arquivos_entidade on public.arquivos(entidade, entidade_id);
create index if not exists idx_arquivos_tipo on public.arquivos(tipo_arquivo);

drop trigger if exists trg_arquivos_updated_at on public.arquivos;
create trigger trg_arquivos_updated_at
before update on public.arquivos
for each row execute function public.set_updated_at();


-- ============================================================
-- 12. LOGS DO SISTEMA
-- ============================================================

create table if not exists public.logs_sistema (
    id uuid primary key default gen_random_uuid(),

    usuario_id uuid references public.usuarios_app(id) on delete set null,

    nivel text not null default 'INFO'
        check (nivel in ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')),

    modulo text,
    acao text not null,
    entidade text,
    entidade_id uuid,

    mensagem text,
    dados jsonb not null default '{}'::jsonb,

    ip text,
    user_agent text,

    created_at timestamptz not null default now()
);

create index if not exists idx_logs_usuario_id on public.logs_sistema(usuario_id);
create index if not exists idx_logs_nivel on public.logs_sistema(nivel);
create index if not exists idx_logs_modulo on public.logs_sistema(modulo);
create index if not exists idx_logs_created_at on public.logs_sistema(created_at);


-- ============================================================
-- 13. ROW LEVEL SECURITY - RLS
-- ============================================================

alter table public.perfis enable row level security;
alter table public.usuarios_app enable row level security;
alter table public.paginas_sistema enable row level security;
alter table public.perfil_permissoes enable row level security;

alter table public.clientes enable row level security;
alter table public.produtos enable row level security;
alter table public.produto_patrimonios enable row level security;
alter table public.orcamentos enable row level security;
alter table public.orcamento_ambientes enable row level security;
alter table public.orcamento_itens enable row level security;
alter table public.estoque_vinculos enable row level security;
alter table public.agenda_eventos enable row level security;
alter table public.financeiro_movimentos enable row level security;
alter table public.retirada_devolucao enable row level security;
alter table public.arquivos enable row level security;
alter table public.logs_sistema enable row level security;


-- ============================================================
-- 14. POLICIES - TABELAS DE CONFIGURAÇÃO
-- ============================================================

drop policy if exists "perfis_select_authenticated" on public.perfis;
create policy "perfis_select_authenticated"
on public.perfis for select
to authenticated
using (true);

drop policy if exists "perfis_admin_all" on public.perfis;
create policy "perfis_admin_all"
on public.perfis for all
to authenticated
using (public.is_admin_empresa())
with check (public.is_admin_empresa());


drop policy if exists "usuarios_select_own_or_admin" on public.usuarios_app;
create policy "usuarios_select_own_or_admin"
on public.usuarios_app for select
to authenticated
using (id = auth.uid() or public.is_admin_empresa());

drop policy if exists "usuarios_admin_insert" on public.usuarios_app;
create policy "usuarios_admin_insert"
on public.usuarios_app for insert
to authenticated
with check (public.is_admin_empresa() or id = auth.uid());

drop policy if exists "usuarios_update_own_or_admin" on public.usuarios_app;
create policy "usuarios_update_own_or_admin"
on public.usuarios_app for update
to authenticated
using (id = auth.uid() or public.is_admin_empresa())
with check (id = auth.uid() or public.is_admin_empresa());


drop policy if exists "paginas_select_authenticated" on public.paginas_sistema;
create policy "paginas_select_authenticated"
on public.paginas_sistema for select
to authenticated
using (true);

drop policy if exists "paginas_admin_all" on public.paginas_sistema;
create policy "paginas_admin_all"
on public.paginas_sistema for all
to authenticated
using (public.is_admin_empresa())
with check (public.is_admin_empresa());


drop policy if exists "permissoes_select_authenticated" on public.perfil_permissoes;
create policy "permissoes_select_authenticated"
on public.perfil_permissoes for select
to authenticated
using (true);

drop policy if exists "permissoes_admin_all" on public.perfil_permissoes;
create policy "permissoes_admin_all"
on public.perfil_permissoes for all
to authenticated
using (public.is_admin_empresa())
with check (public.is_admin_empresa());


-- ============================================================
-- 15. POLICIES - DADOS DO SISTEMA
-- Regra inicial MVP:
-- - usuários autenticados e ativos podem operar dados principais
-- - regras finas de página ficam na aplicação + perfil_permissoes
-- ============================================================

drop policy if exists "clientes_authenticated_all" on public.clientes;
create policy "clientes_authenticated_all"
on public.clientes for all
to authenticated
using (public.current_user_perfil() is not null)
with check (public.current_user_perfil() is not null);


drop policy if exists "produtos_authenticated_all" on public.produtos;
create policy "produtos_authenticated_all"
on public.produtos for all
to authenticated
using (public.current_user_perfil() is not null)
with check (public.current_user_perfil() is not null);


drop policy if exists "produto_patrimonios_authenticated_all" on public.produto_patrimonios;
create policy "produto_patrimonios_authenticated_all"
on public.produto_patrimonios for all
to authenticated
using (public.current_user_perfil() is not null)
with check (public.current_user_perfil() is not null);


drop policy if exists "orcamentos_authenticated_all" on public.orcamentos;
create policy "orcamentos_authenticated_all"
on public.orcamentos for all
to authenticated
using (public.current_user_perfil() is not null)
with check (public.current_user_perfil() is not null);


drop policy if exists "orcamento_ambientes_authenticated_all" on public.orcamento_ambientes;
create policy "orcamento_ambientes_authenticated_all"
on public.orcamento_ambientes for all
to authenticated
using (public.current_user_perfil() is not null)
with check (public.current_user_perfil() is not null);


drop policy if exists "orcamento_itens_authenticated_all" on public.orcamento_itens;
create policy "orcamento_itens_authenticated_all"
on public.orcamento_itens for all
to authenticated
using (public.current_user_perfil() is not null)
with check (public.current_user_perfil() is not null);


drop policy if exists "estoque_vinculos_authenticated_all" on public.estoque_vinculos;
create policy "estoque_vinculos_authenticated_all"
on public.estoque_vinculos for all
to authenticated
using (public.current_user_perfil() is not null)
with check (public.current_user_perfil() is not null);


drop policy if exists "agenda_eventos_authenticated_all" on public.agenda_eventos;
create policy "agenda_eventos_authenticated_all"
on public.agenda_eventos for all
to authenticated
using (public.current_user_perfil() is not null)
with check (public.current_user_perfil() is not null);


drop policy if exists "financeiro_movimentos_authenticated_all" on public.financeiro_movimentos;
create policy "financeiro_movimentos_authenticated_all"
on public.financeiro_movimentos for all
to authenticated
using (public.current_user_perfil() is not null)
with check (public.current_user_perfil() is not null);


drop policy if exists "retirada_devolucao_authenticated_all" on public.retirada_devolucao;
create policy "retirada_devolucao_authenticated_all"
on public.retirada_devolucao for all
to authenticated
using (public.current_user_perfil() is not null)
with check (public.current_user_perfil() is not null);


drop policy if exists "arquivos_authenticated_all" on public.arquivos;
create policy "arquivos_authenticated_all"
on public.arquivos for all
to authenticated
using (public.current_user_perfil() is not null)
with check (public.current_user_perfil() is not null);


drop policy if exists "logs_insert_authenticated" on public.logs_sistema;
create policy "logs_insert_authenticated"
on public.logs_sistema for insert
to authenticated
with check (public.current_user_perfil() is not null);

drop policy if exists "logs_select_admin" on public.logs_sistema;
create policy "logs_select_admin"
on public.logs_sistema for select
to authenticated
using (public.is_admin_empresa());


-- ============================================================
-- 16. SEEDS - PERFIS
-- ============================================================

insert into public.perfis (nome, descricao, ativo)
values
    ('admin_empresa', 'Usuário chefe/cliente com acesso total ao sistema.', true),
    ('colaborador', 'Usuário operacional com acesso parcial ao sistema.', true)
on conflict (nome) do update
set descricao = excluded.descricao,
    ativo = excluded.ativo,
    updated_at = now();


-- ============================================================
-- 17. SEEDS - PÁGINAS DO SISTEMA
-- ============================================================

insert into public.paginas_sistema (nome, slug, ordem, ativo)
values
    ('Dashboard', 'dashboard', 1, true),
    ('Produtos', 'produtos', 2, true),
    ('Clientes', 'clientes', 3, true),
    ('Orçamento', 'orcamento', 4, true),
    ('Estoque', 'estoque', 5, true),
    ('Agenda', 'agenda', 6, true),
    ('Retirada e Devolução', 'retirada_devolucao', 7, true),
    ('Financeiro', 'financeiro', 8, true),
    ('Relatórios', 'relatorios', 9, true)
on conflict (nome) do update
set slug = excluded.slug,
    ordem = excluded.ordem,
    ativo = excluded.ativo;


-- ============================================================
-- 18. SEEDS - PERMISSÕES ADMIN EMPRESA
-- ============================================================

insert into public.perfil_permissoes (
    perfil,
    pagina,
    pode_acessar,
    pode_criar,
    pode_editar,
    pode_excluir,
    pode_exportar
)
select
    'admin_empresa',
    ps.nome,
    true,
    true,
    true,
    true,
    true
from public.paginas_sistema ps
on conflict (perfil, pagina) do update
set pode_acessar = excluded.pode_acessar,
    pode_criar = excluded.pode_criar,
    pode_editar = excluded.pode_editar,
    pode_excluir = excluded.pode_excluir,
    pode_exportar = excluded.pode_exportar,
    updated_at = now();


-- ============================================================
-- 19. SEEDS - PERMISSÕES COLABORADOR
-- Acesso inicial a 5 páginas:
-- Dashboard, Produtos, Clientes, Orçamento, Estoque
-- ============================================================

insert into public.perfil_permissoes (
    perfil,
    pagina,
    pode_acessar,
    pode_criar,
    pode_editar,
    pode_excluir,
    pode_exportar
)
values
    ('colaborador', 'Dashboard', true, false, false, false, false),
    ('colaborador', 'Produtos', true, true, true, false, false),
    ('colaborador', 'Clientes', true, true, true, false, false),
    ('colaborador', 'Orçamento', true, true, true, false, true),
    ('colaborador', 'Estoque', true, true, true, false, false),

    ('colaborador', 'Agenda', false, false, false, false, false),
    ('colaborador', 'Retirada e Devolução', false, false, false, false, false),
    ('colaborador', 'Financeiro', false, false, false, false, false),
    ('colaborador', 'Relatórios', false, false, false, false, false)
on conflict (perfil, pagina) do update
set pode_acessar = excluded.pode_acessar,
    pode_criar = excluded.pode_criar,
    pode_editar = excluded.pode_editar,
    pode_excluir = excluded.pode_excluir,
    pode_exportar = excluded.pode_exportar,
    updated_at = now();


-- ============================================================
-- 20. VIEWS ÚTEIS PARA O SISTEMA
-- ============================================================

create or replace view public.vw_usuarios_com_perfil as
select
    ua.id,
    ua.nome,
    ua.email,
    ua.perfil,
    p.descricao as perfil_descricao,
    ua.telefone,
    ua.cargo,
    ua.ativo,
    ua.ultimo_login,
    ua.created_at,
    ua.updated_at
from public.usuarios_app ua
left join public.perfis p
    on p.nome = ua.perfil;


create or replace view public.vw_permissoes_usuario_atual as
select
    pp.perfil,
    pp.pagina,
    ps.slug,
    ps.ordem,
    pp.pode_acessar,
    pp.pode_criar,
    pp.pode_editar,
    pp.pode_excluir,
    pp.pode_exportar
from public.perfil_permissoes pp
join public.paginas_sistema ps
    on ps.nome = pp.pagina
where pp.perfil = public.current_user_perfil()
  and ps.ativo = true
order by ps.ordem;


create or replace view public.vw_orcamentos_resumo as
select
    o.id,
    o.codigo,
    o.evento_nome,
    o.local_evento,
    o.cliente_id,
    coalesce(c.nome, o.cliente_nome) as cliente_nome,
    o.data_montagem,
    o.data_inicio,
    o.data_fim,
    o.status,
    o.financeiro,
    o.valor_total,
    o.valor_final,
    count(distinct oa.id) as total_ambientes,
    count(distinct oi.id) as total_itens,
    o.created_at,
    o.updated_at
from public.orcamentos o
left join public.clientes c
    on c.id = o.cliente_id
left join public.orcamento_ambientes oa
    on oa.orcamento_id = o.id
left join public.orcamento_itens oi
    on oi.orcamento_id = o.id
group by
    o.id,
    o.codigo,
    o.evento_nome,
    o.local_evento,
    o.cliente_id,
    c.nome,
    o.cliente_nome,
    o.data_montagem,
    o.data_inicio,
    o.data_fim,
    o.status,
    o.financeiro,
    o.valor_total,
    o.valor_final,
    o.created_at,
    o.updated_at;


create or replace view public.vw_estoque_eventos_elegiveis as
select
    o.id as orcamento_id,
    o.codigo,
    o.evento_nome,
    coalesce(c.nome, o.cliente_nome) as cliente_nome,
    o.local_evento,
    o.data_montagem,
    o.data_inicio,
    o.data_fim,
    o.status,
    o.financeiro,
    o.valor_final
from public.orcamentos o
left join public.clientes c
    on c.id = o.cliente_id
where o.financeiro in ('Parcial', 'Pago', 'Atrasado')
  and o.status not in ('Cancelado', 'Reprovado');


create or replace view public.vw_financeiro_resumo_orcamento as
select
    o.id as orcamento_id,
    o.codigo,
    o.evento_nome,
    o.valor_final,
    coalesce(sum(fm.valor) filter (where fm.status = 'Pago'), 0) as valor_pago,
    greatest(
        o.valor_final - coalesce(sum(fm.valor) filter (where fm.status = 'Pago'), 0),
        0
    ) as valor_pendente,
    o.financeiro
from public.orcamentos o
left join public.financeiro_movimentos fm
    on fm.orcamento_id = o.id
group by
    o.id,
    o.codigo,
    o.evento_nome,
    o.valor_final,
    o.financeiro;


-- ============================================================
-- 21. COMENTÁRIOS
-- ============================================================

comment on table public.usuarios_app is 'Usuários do sistema vinculados ao Supabase Auth.';
comment on table public.perfil_permissoes is 'Controle de acesso por perfil às páginas do Streamlit.';
comment on table public.clientes is 'Cadastro de clientes da Federal Eventos.';
comment on table public.produtos is 'Cadastro geral de produtos/equipamentos locáveis.';
comment on table public.produto_patrimonios is 'Unidades físicas dos produtos, controladas por COD/patrimônio.';
comment on table public.orcamentos is 'Cabeçalho dos orçamentos/eventos.';
comment on table public.orcamento_ambientes is 'Ambientes/salas/auditórios/credenciamentos de cada orçamento.';
comment on table public.orcamento_itens is 'Itens/equipamentos dentro de cada ambiente do orçamento.';
comment on table public.estoque_vinculos is 'Vínculo entre orçamento/item e COD/patrimônio separado para o evento.';
comment on table public.agenda_eventos is 'Agenda operacional derivada ou vinculada aos orçamentos.';
comment on table public.financeiro_movimentos is 'Movimentos financeiros vinculados a orçamentos/clientes.';
comment on table public.retirada_devolucao is 'Registros de retirada e devolução dos equipamentos.';
comment on table public.arquivos is 'Metadados de arquivos salvos no Supabase Storage, Google Drive ou outro local.';
comment on table public.logs_sistema is 'Logs técnicos e operacionais do sistema.';

-- ============================================================
-- FIM DO SCHEMA
-- ============================================================