.PHONY: help test lint doctor package clean

PY ?= python3

help:
	@echo "make test     跑单元测试（离线，不产生费用）"
	@echo "make lint     ruff 静态检查"
	@echo "make doctor   校验方舟 Key（需已配置）"
	@echo "make package  打发布压缩包到 dist/"
	@echo "make clean    清理缓存与产物"

test:
	$(PY) -m unittest discover -s tests -v

lint:
	ruff check .

doctor:
	$(PY) scripts/ark_3d.py doctor

package:
	@mkdir -p dist
	@rm -f dist/photo-to-3d.zip
	@zip -r dist/photo-to-3d.zip . \
	  -x "dist/*" -x ".git/*" -x ".ark_key" -x "*/__pycache__/*" -x "*.pyc" \
	  -x ".ruff_cache/*" -x ".pytest_cache/*" -x "out/*" -x "*.glb" > /dev/null
	@echo "已生成 dist/photo-to-3d.zip"

clean:
	rm -rf dist out scripts/__pycache__ tests/__pycache__ .pytest_cache
