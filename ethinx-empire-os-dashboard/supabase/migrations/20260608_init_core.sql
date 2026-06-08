-- ETHINX Canonical v1 - Initial Schema
create extension if not exists "uuid-ossp";
create table public.tenants (id uuid primary key default uuid_generate_v4(), name text not null, slug text unique not null, created_at timestamptz default now());
create table public.users (id uuid primary key references auth.users(id) on delete cascade, email text unique not null, full_name text, created_at timestamptz default now());
create table public.memberships (id uuid primary key default uuid_generate_v4(), tenant_id uuid references public.tenants(id) on delete cascade, user_id uuid references public.users(id) on delete cascade, role text not null check (role in ('owner','admin','user','readonly')), created_at timestamptz default now(), unique(tenant_id, user_id));
create table public.plans (id text primary key, name text not null, price_cents integer not null, dodo_product_id text not null, features jsonb default '{}'::jsonb);
create table public.subscriptions (id uuid primary key default uuid_generate_v4(), tenant_id uuid references public.tenants(id) on delete cascade, dodo_subscription_id text unique not null, dodo_customer_id text not null, plan_id text references public.plans(id), status text not null, current_period_end timestamptz, created_at timestamptz default now());
create table public.leads (id uuid primary key default uuid_generate_v4(), tenant_id uuid references public.tenants(id) on delete cascade, source text not null, email text, phone text, name text, status text default 'new', score integer default 0, data jsonb default '{}'::jsonb, created_at timestamptz default now());
create table public.lead_events (id uuid primary key default uuid_generate_v4(), lead_id uuid references public.leads(id) on delete cascade, tenant_id uuid references public.tenants(id) on delete cascade, event_type text not null, payload jsonb, created_at timestamptz default now());
alter table public.tenants enable row level security;
alter table public.leads enable row level security;
alter table public.lead_events enable row level security;
create policy "tenant_isolation" on public.leads for all using (tenant_id in (select tenant_id from public.memberships where user_id = auth.uid()));
