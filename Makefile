.PHONY: install test lint task1 task2 task3 task4 mock-mcp mock-llm tokens

install:
	python -m pip install -e '.[dev]'

test:
	pytest

lint:
	ruff check src tests mocks scripts

task1:
	python -m quilrai_assessment.task1_mcp_server.server

task2:
	uvicorn quilrai_assessment.task2_security_gateway.app:app --port 9101

task3:
	uvicorn quilrai_assessment.task3_stream_guardrail.app:app --port 9200

task4:
	uvicorn quilrai_assessment.task4_model_router.app:app --port 9300

mock-mcp:
	uvicorn mocks.mock_mcp_downstream:app --port 9102

mock-llm:
	uvicorn mocks.mock_llm_provider:app --port 9301

tokens:
	python scripts/generate_demo_tokens.py
