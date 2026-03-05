.PHONY: build run run-detached stop logs podman-build podman-run podman-run-detached podman-stop podman-logs test sdist screenshots screenshots-setup screenshots-survey screenshots-psf screenshots-cp screenshots-headed screenshots-raw screenshots-raw-survey screenshots-raw-psf screenshots-raw-cp screenshots-raw-headed plone-start-for-tests plone-stop-for-tests screenshots-album screenshots-view

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
		src/zopyx/surveyjs/schema/tests/test_converters_formats.py
	PYTHONWARNINGS=ignore bin/zopepy -m coverage report -m --include='src/zopyx/surveyjs/converters/*.py'

sdist:
	uv run python setup.py sdist

# Screenshot automation with Playwright
# These targets automatically handle Plone startup/shutdown

screenshots-setup:
	@echo "Installing Playwright dependencies..."
	cd playwright-tests && npm install
	cd playwright-tests && npx playwright install chromium

screenshots:
	cd playwright-tests && ./run-screenshots-with-plone.sh

screenshots-survey:
	cd playwright-tests && ./run-screenshots-with-plone.sh survey

screenshots-psf:
	cd playwright-tests && ./run-screenshots-with-plone.sh psf

screenshots-cp:
	cd playwright-tests && ./run-screenshots-with-plone.sh cp

screenshots-headed:
	cd playwright-tests && ./run-screenshots-with-plone.sh headed

# Raw screenshot targets (assumes Plone is already running)
screenshots-raw:
	cd playwright-tests && ./run-screenshots.sh

screenshots-raw-survey:
	cd playwright-tests && ./run-screenshots.sh survey

screenshots-raw-psf:
	cd playwright-tests && ./run-screenshots.sh psf

screenshots-raw-cp:
	cd playwright-tests && ./run-screenshots.sh cp

screenshots-raw-headed:
	cd playwright-tests && ./run-screenshots.sh headed

# Start/stop Plone for tests (manual control)
plone-start-for-tests:
	cd playwright-tests && ./start_plone_for_tests.sh

plone-stop-for-tests:
	cd playwright-tests && ./stop_plone_for_tests.sh

# Generate HTML album from screenshots
screenshots-album:
	cd playwright-tests && npx tsx generate-album.ts

# View screenshots album in browser
screenshots-view:
	cd playwright-tests/screenshots/output && npx serve -p 3000
