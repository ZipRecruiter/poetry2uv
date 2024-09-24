#!/bin/bash

set -o errexit
set -o pipefail

script_directory=$(dirname -- "$0")
cd $1

poetry export -f requirements.txt --output requirements_poetry.txt --without-hashes

python ${script_directory}/convert_poetry_to_uv.py --requirements requirements_poetry.txt

mv pyproject_pinned.toml pyproject.toml
uv lock
uv export --output-file requirements_pinned.txt --no-hashes

mv pyproject_pep508.toml pyproject.toml
uv lock --no-upgrade
uv export --output-file requirements_pep508.txt --no-hashes

diff requirements_pinned.txt requirements_pep508.txt
rm requirements_poetry.txt requirements_pinned.txt requirements_pep508.txt

echo "Complete!"
