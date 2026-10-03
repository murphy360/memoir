# Everything runs in the project's Docker images, never on the host (murphy360/standards).
# TAG keeps parallel sessions from overwriting each other's images: `make test TAG=<you>`.
SHELL := /bin/sh
TAG ?= dev
API_TEST := memoir-api-test:$(TAG)
WEB_TEST := memoir-web-test:$(TAG)
MOUNT := -v "$(CURDIR):/src"
AS_ME := -u $$(id -u):$$(id -g) -e HOME=/tmp

.PHONY: images test test-api test-web lint lint-api lint-web format openapi up down

images:
	docker build --target test -t $(API_TEST) api
	docker build --target test -t $(WEB_TEST) web

test: test-api test-web

test-api: images
	docker run --rm $(MOUNT) -w /src/api $(API_TEST) pytest -q

test-web: images
	docker run --rm $(AS_ME) $(MOUNT) -w /src/web $(WEB_TEST) sh -c "npm run typecheck && npm test"

lint: lint-api lint-web

# The API, as python-lint runs it: formatting, ruff with the standard limits, and no noqa.
# (CI also checks file sizes with code_rules.py --all from murphy360/standards.)
lint-api: images
	docker run --rm $(MOUNT) -w /src/api $(API_TEST) \
		sh -c "! grep -rn --include='*.py' '# *noqa' . && ruff format --no-cache --check . \
		&& ruff check --no-cache --ignore-noqa \
		--extend-select E,W,F,C901,PLR0912,PLR0915 --config lint.mccabe.max-complexity=15 \
		--config lint.pylint.max-branches=15 --config lint.pylint.max-statements=60 ."

lint-web: images
	docker run --rm $(AS_ME) $(MOUNT) -w /src/web $(WEB_TEST) \
		sh -c "prettier --check . && eslint --rule '{\"complexity\": [\"error\", 15]}' \
		--rule '{\"max-statements\": [\"error\", 60]}' ."

format: images
	docker run --rm $(AS_ME) $(MOUNT) -w /src/api $(API_TEST) ruff format --no-cache .
	docker run --rm $(AS_ME) $(MOUNT) -w /src/web $(WEB_TEST) prettier --write .

# Regenerate the OpenAPI document the web client is typed from. Commit the result.
openapi: images
	docker run --rm $(MOUNT) -w /src/api $(API_TEST) memoir-cli openapi > web/src/api/openapi.json

up:
	docker compose up --build -d
	@echo "Memoir: http://localhost:8080/memoir/   API: http://localhost:8010/api/health"

down:
	docker compose down
