.PHONY: all clean setup_environment check lint typecheck test \
        pyenv_exists poetry_exists is_git

# La CI passe RUFF_FORMAT=github pour annoter les lignes fautives dans la PR ;
# en local on garde la sortie lisible de ruff.
RUFF_FORMAT ?= full

all: setup_environment

clean:
	poetry run pre-commit uninstall
	rm -rf .venv

setup_environment: check
		pyenv install 3.14 --skip-existing \
		&& pyenv local 3.14 \
		&& poetry env use 3.14 \
		&& poetry install \
		&& poetry run pre-commit install

check: pyenv_exists poetry_exists is_git

pyenv_exists: ; @which pyenv > /dev/null

poetry_exists: ; @which poetry > /dev/null

is_git: ; @git rev-parse --git-dir > /dev/null

########################################################################
# Les vérifications. Une seule définition, appelée en local comme par
# .github/workflows/ci.yml : ce qui passe ici passe en CI.
########################################################################

lint:
	poetry run ruff format --check --diff .
	poetry run ruff check --output-format=$(RUFF_FORMAT) .

typecheck:
	poetry run mypy src/

test:
	poetry run coverage run
	poetry run coverage xml
