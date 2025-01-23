#!/bin/bash

set -o errexit
set -o pipefail

pwd
script_directory=$(dirname -- "$(realpath $0)")
project_dir="$(realpath $1)"
shift

script_args=()
remove_poetry=1
sed_files=""  # list of files to replace poetry.lock with uv.lock

while [[ $# -gt 0 ]]; do
    arg="$1"
    shift

    case $arg in
        --keep-poetry)
            remove_poetry=0
            script_args+=("$arg")
            ;;
        *)
            script_args+=("$arg")
            ;;
    esac
done

echo "Generating requirements from poetry to get exact versions from lock"
awk -F"#" '{print $1}' $project_dir/pyproject.toml | grep -q '\[tool\.poetry\.dev-dependencies\]' && with_flags="--with dev"
poetry export -C $project_dir -f requirements.txt --output $project_dir/requirements_poetry.txt --without-hashes --all-extras $with_flags
sed -i '' '/file:/d' "${project_dir}/requirements_poetry.txt"

echo "Generate two versions of pyproject.toml, one with exact versions and one with constraints from prior pyproject.toml"
pyzr run $script_directory -- python ${script_directory}/convert_poetry_to_uv.py --requirements requirements_poetry.txt --project-dir $project_dir "${script_args[@]}"

echo "Create uv.lock with exact versions"
cd $project_dir
mv -v pyproject_pinned.toml pyproject.toml
uv lock
uv export --output-file requirements_pinned.txt --no-hashes --quiet --all-extras

echo "Regenerate uv.lock with non-pinned pyproject.toml, but keep versions what they were before"
mv pyproject_pep508.toml pyproject.toml
uv lock --no-upgrade
uv export --output-file requirements_pep508.txt --no-hashes --quiet --all-extras

echo "Check diff between exported requirements texts exported by poetry (<) and final uv (>)"
diff -b -w <(awk '{print $1}' requirements_poetry.txt) <(awk '{print $1}' requirements_pep508.txt) >/dev/stderr || exitcode=$?

# allow exit code of 1 because diff returns 1 if files are different
[[ $exitcode -gt 1 ]] && exit $exitcode

echo "Add uv.lock to git"
git add uv.lock
git stage -u pyproject.toml

echo "Clean up intermediate files"
rm requirements_poetry.txt requirements_pinned.txt requirements_pep508.txt

if [[ $remove_poetry -eq 1 ]]; then
    git rm poetry.lock
    for sed_file in $sed_files; do
        if [[ -f $sed_file ]]; then
            sed -i "" 's/poetry\.lock/uv.lock/g' $project_dir/$sed_file
            if git status --porcelain -- $project_dir/$sed_file | grep -qv "^??"; then
                git add $project_dir/$sed_file
            fi
        fi
    done
fi

echo "Complete!"
