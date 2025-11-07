.PHONY: test test-unit test-integration test-coverage test-watch install-test-deps clean-test help

# Colors for output
GREEN := \033[0;32m
YELLOW := \033[1;33m
RED := \033[0;31m
NC := \033[0m # No Color

help: ## Show this help message
	@echo "$(GREEN)Available commands:$(NC)"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(YELLOW)%-20s$(NC) %s\n", $$1, $$2}'

install-test-deps: ## Install testing dependencies
	@echo "$(GREEN)Installing test dependencies...$(NC)"
	pip install -r requirements.txt

test: ## Run all tests
	@echo "$(GREEN)Running all tests...$(NC)"
	pytest

test-unit: ## Run only unit tests
	@echo "$(GREEN)Running unit tests...$(NC)"
	pytest tests/unit/ -m unit

test-integration: ## Run only integration tests
	@echo "$(GREEN)Running integration tests...$(NC)"
	pytest tests/integration/ -m integration

test-api: ## Run only API tests
	@echo "$(GREEN)Running API tests...$(NC)"
	pytest -m api

test-database: ## Run only database tests
	@echo "$(GREEN)Running database tests...$(NC)"
	pytest -m database

test-coverage: ## Run tests with coverage report
	@echo "$(GREEN)Running tests with coverage...$(NC)"
	pytest --cov=app --cov-report=term-missing --cov-report=html

test-watch: ## Run tests in watch mode (requires pytest-watch)
	@echo "$(GREEN)Running tests in watch mode...$(NC)"
	@echo "$(YELLOW)Note: Install pytest-watch with 'pip install pytest-watch'$(NC)"
	ptw

test-fast: ## Run tests excluding slow tests
	@echo "$(GREEN)Running fast tests only...$(NC)"
	pytest -m "not slow"

test-slow: ## Run only slow tests
	@echo "$(GREEN)Running slow tests...$(NC)"
	pytest -m slow

test-verbose: ## Run tests with verbose output
	@echo "$(GREEN)Running tests with verbose output...$(NC)"
	pytest -v -s

clean-test: ## Clean test artifacts
	@echo "$(GREEN)Cleaning test artifacts...$(NC)"
	rm -rf .pytest_cache/
	rm -rf htmlcov/
	rm -rf .coverage
	rm -rf test-*.db
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete

lint: ## Run code linting
	@echo "$(GREEN)Running linting...$(NC)"
	flake8 app/ tests/
	black --check app/ tests/
	isort --check-only app/ tests/

format: ## Format code
	@echo "$(GREEN)Formatting code...$(NC)"
	black app/ tests/
	isort app/ tests/

# Development shortcuts
dev-setup: install-test-deps ## Set up development environment
	@echo "$(GREEN)Development environment ready!$(NC)"

ci-test: clean-test test-coverage ## Run CI-style testing
	@echo "$(GREEN)CI tests completed!$(NC)"
