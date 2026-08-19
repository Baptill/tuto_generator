.DEFAULT_GOAL := help

VENV := .venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

.PHONY: help venv install test generate generate-html generate-all pdf serve ui open init clean

ARTICLE ?= 2026-07-exemple-tuto

help: ## Affiche cette aide
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

$(VENV)/bin/python:
	python3 -m venv $(VENV)

venv: $(VENV)/bin/python ## Crée l'environnement virtuel

install: venv ## Installe les dépendances Python dans .venv
	$(PIP) install -q --upgrade pip
	$(PIP) install -q -r requirements.txt

test: install ## Lance la suite de tests
	$(PYTHON) -m pytest tests/ -q

generate: install ## Génère HTML + PDF de l'article (ARTICLE=<id> pour cibler un autre)
	$(PYTHON) -m app.cli generate $(ARTICLE)

generate-html: install ## Génère uniquement le HTML (sans PDF) — plus rapide pour itérer sur le template
	$(PYTHON) -m app.cli generate $(ARTICLE) --skip-pdf

generate-all: install ## Régénère TOUS les articles (à lancer après un changement de charte)
	@ok=0; ko=0; echecs=""; \
	for dir in vault-articles/articles/*/; do \
		id=$$(basename "$$dir"); \
		[ -f "$$dir/content.yaml" ] || continue; \
		if $(PYTHON) -m app.cli generate "$$id"; then \
			ok=$$((ok+1)); \
		else \
			ko=$$((ko+1)); echecs="$$echecs $$id"; \
		fi; \
	done; \
	echo "------------------------------------------------------------"; \
	echo "$$ok article(s) régénéré(s), $$ko échec(s)$$echecs"; \
	[ $$ko -eq 0 ]

pdf: install ## Reconvertit le HTML existant en PDF (utile après retouche navigateur)
	$(PYTHON) -m app.cli pdf $(ARTICLE)

serve: install ## Lance le composeur + le service d'enregistrement des retouches
	$(PYTHON) -m app.cli serve

ui: install ## Lance le composeur et l'ouvre dans le navigateur
	@($(PYTHON) -m app.cli serve &) ; sleep 2 ; open http://127.0.0.1:8765/

open: ## Ouvre le HTML généré dans le navigateur par défaut
	open vault-articles/articles/$(ARTICLE)/output/article.html

init: install test ## Initialise le projet : venv + deps + tests
	@echo "Projet initialisé. Essaie : make generate"

clean: ## Supprime le venv et les caches Python
	rm -rf $(VENV) .pytest_cache app/__pycache__ scripts/__pycache__ tests/__pycache__ *.egg-info
