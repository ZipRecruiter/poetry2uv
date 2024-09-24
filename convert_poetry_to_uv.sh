#!/bin/bash

set -o errexit
set -o pipefail

script_directory=$(dirname -- "$0")
cd $1

# get the current exact versions
poetry export -f requirements.txt --output requirements_poetry.txt --without-hashes

# generate two versions of pyproject.toml, one with exact versions and one with prior constraints from pyproject.toml
python ${script_directory}/convert_poetry_to_uv.py --requirements requirements_poetry.txt

# create uv.lock with exact versions
mv pyproject_pinned.toml pyproject.toml
uv lock
uv export --output-file requirements_pinned.txt --no-hashes

# regenerate uv.lock with non-pinned pyproject.toml, but keep versions what they were before
mv pyproject_pep508.toml pyproject.toml
uv lock --no-upgrade
uv export --output-file requirements_pep508.txt --no-hashes

# check diff, but allow exit code of 1 
diff requirements_pinned.txt <(awk '{print $1}' requirements_pep508.txt) || true

# clean up
rm requirements_poetry.txt requirements_pinned.txt requirements_pep508.txt

echo "Complete!"
