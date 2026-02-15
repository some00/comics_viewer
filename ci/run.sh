#!/bin/bash
set -ex
uv venv /tmp/.venv_docker
source /tmp/.venv_docker/bin/activate
uv pip install '.[test]'
pytest --cov=comics_viewer --cov-branch --cov-report=xml --cov-report=term
pyrefly check
