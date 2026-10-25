# All targets delegate to scripts/tasks.py so behaviour is identical on Windows (make.cmd) and Unix.
UV ?= uv
RUN = $(UV) run python scripts/tasks.py

.PHONY: install lint test seed eval demo web-test

install: ; $(RUN) install
lint:    ; $(RUN) lint
test:    ; $(RUN) test
seed:    ; $(RUN) seed
eval:    ; $(RUN) eval
demo:    ; $(RUN) demo
web-test: ; $(RUN) web-test
