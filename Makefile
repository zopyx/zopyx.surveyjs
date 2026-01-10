.PHONY: build run run-detached stop logs podman-build podman-run podman-run-detached podman-stop podman-logs

IMAGE_NAME := privacyforms/demo
CONTAINER_NAME := privacyforms-demo
HOST_PORT := 9000
CONTAINER_PORT := 8082

build:
	docker build -t $(IMAGE_NAME) .

run:
	docker run --rm --name $(CONTAINER_NAME) -p $(HOST_PORT):$(CONTAINER_PORT) $(IMAGE_NAME)

run-detached:
	docker run -d --rm --name $(CONTAINER_NAME) -p $(HOST_PORT):$(CONTAINER_PORT) $(IMAGE_NAME)

stop:
	docker stop $(CONTAINER_NAME)

logs:
	docker logs -f $(CONTAINER_NAME)

podman-build:
	podman buildx build --platform linux/amd64 -t $(IMAGE_NAME) --load .

podman-run:
	podman run --rm --name $(CONTAINER_NAME) -p $(HOST_PORT):$(CONTAINER_PORT) $(IMAGE_NAME)

podman-run-detached:
	podman run -d --rm --name $(CONTAINER_NAME) -p $(HOST_PORT):$(CONTAINER_PORT) $(IMAGE_NAME)

podman-stop:
	podman stop $(CONTAINER_NAME)

podman-logs:
	podman logs -f $(CONTAINER_NAME)
