.PHONY: build run run-detached stop logs podman-build podman-run podman-run-detached podman-stop podman-logs test

IMAGE_NAME := privacyforms/demo
CONTAINER_NAME := pfs-demo
HOST_PORT := 10000
CONTAINER_PORT := 8082

build:
	docker build -t $(IMAGE_NAME) .

run:
	docker run --rm --name $(CONTAINER_NAME) -p $(HOST_PORT):$(CONTAINER_PORT) $(IMAGE_NAME)

run-detached:
	-docker run -d --rm --name $(CONTAINER_NAME) -p $(HOST_PORT):$(CONTAINER_PORT) $(IMAGE_NAME)

stop:
	-docker stop $(CONTAINER_NAME)
	-docker kill $(CONTAINER_NAME)

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

test:
	PYTHONWARNINGS=ignore uv pip install pytest-coverage pytest
	PYTHONWARNINGS=ignore bin/test -s zopyx.surveyjs
	PYTHONWARNINGS=ignore bin/zopepy -m coverage run -m pytest \
		src/zopyx/surveyjs/converters/tests/test_converters.py \
		src/zopyx/surveyjs/schema/tests/test_converter.py \
		src/zopyx/surveyjs/schema/tests/test_converters_formats.py \
		src/zopyx/surveyjs/tests/test_validation.py
	PYTHONWARNINGS=ignore bin/zopepy -m coverage report -m --include='src/zopyx/surveyjs/converters/*.py,src/zopyx/surveyjs/validation.py'
