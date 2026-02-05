REPO=tio-oci.download.greymatter.io
API_IMAGE=greymatter-cli-api
VERSION=0.3.0

build-api:
	docker build -f Dockerfile -t $(API_IMAGE):dev .

load-api:
	kind load docker-image cli-api:dev

build:
	make build-api

load:
	make load-api

build-load:
	make build-api
	make load-api

build-deploy:
	docker login $(REPO)
	docker build -f Dockerfile -t $(REPO)/$(API_IMAGE):$(VERSION) .
	docker push $(REPO)/$(API_IMAGE):$(VERSION)