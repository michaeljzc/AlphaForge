PY ?= .venv/bin/python
AF ?= .venv/bin/alphaforge

.PHONY: help install ingest build demo mine event test report clean
help:
	@echo "make ingest   # 全量数据摄取"
	@echo "make build    # 面板 + Qlib 导出 + 校验"
	@echo "make demo     # 端到端演示 + HTML"
	@echo "make mine     # 完整 GP"
	@echo "make event    # T0 事件研究"
	@echo "make test     # 单元测试"

install:
	python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/pip install -e . --no-deps

ingest:
	$(AF) ingest --start 2019-01-01 --end 2026-10-30

build:
	$(AF) build --export-qlib --verify

demo:
	$(AF) demo

mine:
	$(AF) factors mine --population 200 --generations 15

event:
	$(AF) event --audit

test:
	$(PY) -m unittest discover -s tests -v

clean:
	rm -f data/cache/panel_*.npz
	rm -rf reports/artifacts
