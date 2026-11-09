# Infrastructure notes

This project uses PostgreSQL and Redis. For local development, use
`docker-compose.yml` at the repo root, which runs Postgres, Redis, the API,
and Celery workers.

For production, deploy the same services using an open-source/free approach
such as:

- **Docker Compose** on a VPS you control
- **[Coolify](https://coolify.io/)** (open-source, self-hosted PaaS) to
  deploy the compose stack

**Security:** keep Redis and Postgres on a private network. Do not expose the
broker/database publicly. Use strong passwords and set secrets via your
platform's secret management or environment configuration.
