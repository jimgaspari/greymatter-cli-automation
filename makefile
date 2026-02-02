API_IMAGE=cli-api:dev
RUNNER_IMAGE=cli-api-runner:dev

build-api:
	docker build -f Dockerfile -t $(API_IMAGE) .

load-api:
	kind load docker-image cli-api:dev

build:
	make build-api

load:
	make load-api

build-load:
	make build-api
	make load-api
