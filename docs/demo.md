# Reproducible demo

1. Start the stack with `docker compose up --build`.
2. Send an OTLP/HTTP JSON span whose `service.name` is `checkout`, `peer.service` is `users`, `http.route` is `/users/42`, and `contract.fields` is `id,email`.
3. Register OpenAPI v1 containing `id` and `email` on `GET /users/{id}`.
4. Register v2 without `email`.
5. Compare the returned spec IDs. The report is `high` risk and identifies `checkout`.

The control-plane test suite executes this entire scenario without external services.
