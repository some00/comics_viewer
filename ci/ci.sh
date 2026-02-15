#!/bin/bash
set -ex
uv venv .venv_docker
source .venv_docker/bin/activate
uv pip install '.[test]'
pytest --cov=comics_viewer
pyrefly check
