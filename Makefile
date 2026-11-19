.PHONY: help test lint doctor package clean

PY ?= python3

help:
	@echo "make test     跑单元测试（离线，不产生费用）"
	@echo "make lint     ruff 静态检查"
	@echo "make doctor   校验方舟 Key（需已配置）"
	@echo "make package  生成 Skill 压缩包与 SHA-256 校验文件"
	@echo "make clean    清理缓存与产物"

test:
	$(PY) -m unittest discover -s tests -v

lint:
	ruff check .

doctor:
	$(PY) scripts/ark_3d.py doctor

package:
	$(PY) .github/scripts/package_skill.py

clean:
	rm -rf dist out scripts/__pycache__ tests/__pycache__ .pytest_cache
