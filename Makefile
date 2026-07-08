.DEFAULT_GOAL := help

VENV := .venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

.PHONY: help venv install templates test generate clean

help: ## Affiche cette aide
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

$(VENV)/bin/python:
	python3 -m venv $(VENV)

venv: $(VENV)/bin/python ## Crée l'environnement virtuel

install: venv ## Installe les dépendances Python dans .venv
	$(PIP) install -q --upgrade pip
	$(PIP) install -q -r requirements.txt

templates: install ## (Re)génère les templates Word pilotes (tuto-release, blog-standard)
	$(PYTHON) -m scripts.build_templates

test: install ## Lance la suite de tests
	$(PYTHON) -m pytest tests/ -q

generate: install ## Génère l'article d'exemple (docx + pdf si LibreOffice dispo)
	$(PYTHON) -m app.cli 2026-07-exemple-tuto

init: install templates test ## Initialise le projet : venv + deps + templates pilotes + tests
	@echo "Projet initialisé. Essaie : make generate"

clean: ## Supprime le venv et les caches Python
	rm -rf $(VENV) .pytest_cache app/__pycache__ scripts/__pycache__ tests/__pycache__ *.egg-info
