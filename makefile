API_IMAGE=cli-api:dev
RUNNER_IMAGE=cli-api-runner:dev

build-api:
	docker build -f Dockerfile -t $(API_IMAGE) .

load-api:
	kind load docker-image cli-api:dev


build-runner:
	docker build -f Dockerfile.runner -t $(RUNNER_IMAGE) .

load-runner:
	kind load docker-image cli-api-runner:dev

build:
	make build-api
	make build-runner

load:
	make load-api
	make load-runner
build-load:
	make build-api
	make build-runner
	make load-api
	make load-runner

build-load-api:
	make build-api
	make load-api