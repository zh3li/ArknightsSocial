.PHONY: all resolve scan graph stats verify data web dev test clean

# Full pipeline: resolve -> scan -> graph -> stats -> verify
all: resolve scan graph stats verify

resolve:
	python3 build/resolve.py

scan:
	python3 build/scan.py

graph:
	python3 build/graph.py

stats:
	python3 build/stats.py

verify:
	python3 build/verify.py

# frontend
web:
	cd web && npm install && npm run build

dev:
	cd web && npm run dev

test:
	cd web && node test-logic.mjs

clean:
	rm -rf build/data web/dist
