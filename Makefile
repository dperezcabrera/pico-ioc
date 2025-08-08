.PHONY: $(VERSIONS) build-% test-% test-all

VERSIONS = 3.8 3.9 3.10 3.11 3.12 3.13

build-%:
	docker build --pull --build-arg PYTHON_VERSION=$* \
		-t pico-ioc-test:$* -f Dockerfile.test .

test-%: build-%
	docker run --rm pico-ioc-test:$*

test-all: $(addprefix test-, $(VERSIONS))
	@echo "✅ All versions done"

