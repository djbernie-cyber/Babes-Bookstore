# infra/

`redis.fly.toml` configures the separate Redis app used as the Celery broker:

    flyctl deploy -a babes-bookstore-redis --config infra/redis.fly.toml

The password lives in that app's secrets (`REDIS_PASSWORD`). The main app's
`REDIS_URL` secret points at `babes-bookstore-redis.internal:6379`.

Note: keep exactly ONE machine in this app. Extra standby machines join the
`.internal` DNS rotation while stopped and cause random connection refusals.
