# Babe's Bookstore on Kubernetes

Production-grade deployment with **zero-downtime rolling updates for every
user**. The storefront stays on Netlify/CDN; this cluster runs the FastAPI
backend (`/api/*`) plus the Celery worker, Postgres and Redis.

```
Netlify/CDN (static storefront)
        │  /api/* → https://api.babes-bookstore.example
        ▼
┌─────────────────────────────────────────────┐
│ kubernetes cluster (babes-bookstore ns)     │
│   babes-api     Deployment  2→8 replicas    │
│   babes-worker  Deployment  1 replica+beat  │
│   babes-postgres StatefulSet 1 (or managed) │
│   babes-redis   Deployment 1 (or managed)   │
└─────────────────────────────────────────────┘
```

## Why this is "updates for all users"

- The API Deployment rolls with `maxSurge: 1`, `maxUnavailable: 0`, and the
  new pod only receives traffic once `/health` passes, so deploys never drop
  a live request.
- Migrations run in a pod **initContainer** *before* new code serves traffic,
  while old pods keep serving — schema-first, traffic-second.
- A `PodDisruptionBudget` guarantees a node drain never leaves the API at 0.
- Pushing to `main` triggers the GitHub Actions pipeline
  (`.github/workflows/deploy-kubernetes.yml`) to build a new image tag and
  roll it through the cluster automatically.

## 1. One-time prerequisites

1. `kubectl` + a cluster (minikube/k3s/kind for testing, EKS/GKE/AKS for prod).
2. An ingress controller + cert-manager (for the TLS block in `08-ingress.yaml`).
3. Copy `02-secrets.yaml` → replace every `CHANGE_ME` value.
   - Generate the JWT key: `openssl rand -hex 32`.
   - Point `database-url` / `sync-database-url` at the bundled Postgres or a
     managed offering.
   - `redis-url` must match the `redis-password` you set.

## 2. Deploy

```bash
# from the repo root
kubectl apply -k infra/kubernetes

# watch it settle: old pods keep serving while new ones roll
kubectl -n babes-bookstore rollout status deployment/babes-api
kubectl -n babes-bookstore get pods

# create the first admin (optional; ADMIN_EMAILS in the ConfigMap also works)
kubectl -n babes-bookstore exec deploy/babes-api -- python -c "
import asyncio
from sqlalchemy import select
from app.database import AsyncSessionLocal
from app.models.user import User
from passlib.context import CryptContext
"...  # see README.md — run once
```

## 3. Update to a new version

```bash
# Option A — GitHub Actions (recommended): push to main.
# Option B — manual:
kubectl -n babes-bookstore set image deploy/babes-api   api=ghcr.io/djbernie-cyber/babes-bookstore:NEW
kubectl -n babes-bookstore set image deploy/babes-worker worker=ghcr.io/djbernie-cyber/babes-bookstore:NEW
kubectl -n babes-bookstore rollout status deploy/babes-api
```

## 4. Backups & data

- Postgres data lives in the `data-*` PersistentVolumeClaim (20Gi). Back it
  up with `pg_dump` from the pod or your managed DB's tooling.
- Bundle files use R2 whenever configured. Without R2 the worker writes to
  the ephemeral `emptyDir` mount — change `06-worker.yaml` `volumes` to a
  ReadWriteMany PVC for durable storage.

## Files

| File | Purpose |
|---|---|
| `00-namespace.yaml` | isolation + labels |
| `01-configmap.yaml` | shared non-secret config |
| `02-secrets.yaml` | **template** — replace all `CHANGE_ME` values |
| `04-postgres.yaml` | self-contained Postgres StatefulSet + Service |
| `04-redis.yaml` | self-contained Redis + Service |
| `05-api.yaml` | API Deployment (rolling/health-gated), migration init, PDB |
| `06-worker.yaml` | Celery worker + beat |
| `07-hpa.yaml` | CPU autoscaling 2→8 replicas |
| `08-ingress.yaml` | TLS ingress for the API host |
| `kustomization.yaml` | one-command apply |
| `../../.github/workflows/deploy-kubernetes.yml` | CI/CD rolling deploy |