.PHONY: bootstrap lint test integration demo benchmark verify
bootstrap:
	cd control && uv sync --dev
	cd web && npm install
lint:
	cd collector && gofmt -w . && go vet ./...
	cd control && uv run ruff check .
test:
	cd collector && go test -race ./...
	cd control && uv run pytest -q
integration: test
demo:
	docker compose up --build
benchmark:
	cd collector && go test -bench=. -benchmem ./...
verify: lint test
	cd web && npm run build
