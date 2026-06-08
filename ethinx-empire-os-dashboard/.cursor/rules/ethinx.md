# ETHINX Build Rules — Canonical v1

SOURCE OF TRUTH:
- Follow ETHINX Canonical Architecture v1 in docs/architecture/ETHINX_Canonical_Architecture_v1.pdf
- Do not re-architect. Do not invent new patterns.

STACK:
- Frontend: Next.js 14 (App Router, TypeScript)
- Backend: Supabase (Postgres, Auth, RLS, Storage, Edge Functions)
- Payments: Dodo (NOT Stripe)
- Workflow: Simple trigger → action (no DAG, no agent choreography)

PHASE 1 SCOPE ONLY:
- Multi-tenancy with RLS
- User roles: Platform Admin, Tenant Owner, Tenant Admin, Tenant User, Read-only
- Subscriptions via Dodo webhooks
- Lead Engine v1: capture, normalize, deduplicate, score, assign
- Template system skeleton

DO NOT BUILD:
- Agent orchestration, DAG workflows, multi-service Kubernetes, Terraform, Stripe
