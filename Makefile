PY_SERVICES = api-gateway portfolio-service radar-service news-service research-service

.PHONY: install-frontend test-frontend test-services $(addprefix test-service-,$(PY_SERVICES)) docker-up docker-down docker-logs install-tools clean init-db

install-tools:
	@echo "安裝基礎 CLI 依賴 (aider / python-dotenv 等)"
	pip install -r requirements.txt

install-frontend:
	cd frontend && npm install

test-frontend:
	cd frontend && npm run test

$(addprefix test-service-,$(PY_SERVICES)):
	@service=$(subst test-service-,,$@); \
	cd services/$$service && pytest

test-services:
	@for service in $(PY_SERVICES); do \
		$(MAKE) test-service-$$service || exit 1; \
	done

clean:
	rm -rf frontend/node_modules frontend/dist .pytest_cache .vitest
	find services -name '__pycache__' -type d -prune -exec rm -rf {} +

docker-up:
	docker compose up -d --build

docker-down:
	docker compose down -v

docker-logs:
	docker compose logs -f

init-db:
	@echo "執行資料庫初始化與遷移..."
	./scripts/init_databases.sh
