import os
import re
from copy import deepcopy
from typing import Any, Collection, Optional

import tomlkit
from tomlkit import TOMLDocument
from tomlkit.api import Array
from tomlkit.exceptions import NonExistentKey
from tomlkit.toml_file import TOMLFile

PathLike = os.PathLike | str


class PyProject:
    """This class converts a Poetry-style pyproject.toml to PEP 508 format.
    In its current factoring, initializing it does the conversion and writes the output to a file -
    it does not return the intermediate representation.
    """

    version_pattern = re.compile(
        r"^([=^~]{0,2})([\d.*]+(?:-\w+(?:\.\d)?)?)"
    )  # versions involving =, ^, ~ need to be converted
    author_pattern = re.compile(r"^(.*?)\s+<([^>]+)>$")
    git_source_keys = {"git", "rev", "tag", "branch"}

    def __init__(
        self,
        input_file: PathLike,
        output_file: PathLike,
        project_dir: PathLike = ".",
        exported_reqs: str = "",
        keep_poetry: bool = False,
        prompt_for_version: bool = False,
        remove_entries: Optional[Collection[str]] = None,
    ):
        """Load a pyproject.toml input_file and convert it to PEP 508 format, writing to output_file.
        :param exported_reqs: if provided, will use the requirements.txt file to get exact versions for dependencies.
        """
        self.project_dir = project_dir
        self.prompt_for_version = prompt_for_version
        self.sources = {}
        self.remove_entries = remove_entries if remove_entries is not None else []
        self.convert_to_pep508(input_file, output_file, exported_reqs, keep_poetry)

    def convert_version_entry(self, version_entry: str | Array) -> str:
        """Converts poetry version constraint specifications to PEP 621."""
        # might want to handle multiple comma-separated constraints e.g. str(version_constraint).split(',')

        if version_entry == "*":
            return ""

        if isinstance(version_entry, Array):
            if len(version_entry) > 1 and self.prompt_for_version:
                print("Multiple constraints for source not supported, please select one:")
                version_entry = self.select_input_choice(version_entry)
            else:
                version_entry = version_entry[0]
            if "git" not in version_entry:
                raise NotImplementedError("Only git sources are supported currently")
            self.handle_git_entry(version_entry)
            return ""

        groups = version_entry.split(",")

        return ",".join(self.convert_version_constraint(group) for group in groups)

    @staticmethod
    def increment_version(version_split: list[str], increment_index: int) -> None:
        """Increments the version number at the specified index in place."""
        if increment_index == 2 and "-" in version_split[increment_index]:
            # if the patch version has a pre-release, increment the pre-release number
            pre_release_split = version_split[increment_index].split("-")
            pre_release_split[-1] = str(int(pre_release_split[-1]) + 1)
            version_split[increment_index] = "-".join(pre_release_split)
        else:
            version_split[increment_index] = str(int(version_split[increment_index]) + 1)
        for i in range(increment_index + 1, len(version_split)):
            version_split[i] = "0"

    @staticmethod
    def convert_version_constraint(version_constraint: str) -> str:
        # check if version constraint is a string matching the typical pattern needing conversion
        if (match := PyProject.version_pattern.match(version_constraint)) is not None:
            symbols = match.group(1)
            numbers = match.group(2)
            split_numbers = numbers.split(".")
            upper_constraint = ""
            i_nonzero = next((i for i, value in enumerate(split_numbers) if int(value) != 0), -1)  # first nonzero index

            if symbols in ["", "="]:  # base case for no symbolic expression, assume equality (includes e.g. 1.2.*)
                symbols = "=="
            elif symbols == "^":
                symbols = ">="
                PyProject.increment_version(split_numbers, i_nonzero)
                # split_numbers[i_nonzero] = str(int(split_numbers[i_nonzero]) + 1)
                upper_constraint = f",<{'.'.join(map(str, split_numbers[: i_nonzero + 1]))}"
            elif symbols == "~":
                symbols = ">="
                if len(split_numbers) >= 3 and i_nonzero < 2:
                    PyProject.increment_version(split_numbers, 1)
                    # split_numbers[1] = str(int(split_numbers[1]) + 1)
                    split_numbers[2] = "0"
                else:
                    PyProject.increment_version(split_numbers, len(split_numbers) - 1)
                    # split_numbers[-1] = str(int(split_numbers[-1]) + 1)
                upper_constraint = f",<{'.'.join(split_numbers)}"
            return f"{symbols}{numbers}{upper_constraint}"

        elif version_constraint.startswith("~") or version_constraint.startswith("^"):
            raise ValueError(f"Invalid version constraint: {version_constraint}")

        return str(version_constraint)

    @staticmethod
    def _split_version(version: str) -> tuple[int, int, int, str]:
        """
        Parse a version string like "1.2.3" or "1.2.3-alpha" into major, minor, patch, and extra.
        Returns (major, minor, patch, extra).
        """
        # This regex separates out an optional pre-release or build metadata after a dash or plus.
        match = re.match(r"^(\d+)(?:\.(\d+))?(?:\.(\d+))?([\-\+].+)?$", version.strip())
        if not match:
            # If we can't parse it at all, fallback to all zeros
            return 0, 0, 0, ""

        major_str, minor_str, patch_str, extra = match.groups()
        major = int(major_str) if major_str else 0
        minor = int(minor_str) if minor_str else 0
        patch = int(patch_str) if patch_str else 0
        extra = extra or ""

        return major, minor, patch, extra

    def handle_git_entry(self, git_entry: dict[str, Any]) -> str:
        """Converts a git dependency entry to a PEP 508 format.
        Returns the package name."""
        package_name = os.path.splitext(os.path.basename(git_entry["git"]))[0]
        if package_name in self.sources:
            raise NotImplementedError(
                f"Can not handle duped sources with name {package_name}!"
                f"\n{self.sources[package_name]} -> {git_entry['git']}"
            )
        source = tomlkit.inline_table()
        source.update({k: v for k, v in git_entry.items() if k in self.git_source_keys})
        self.sources[package_name] = source
        return package_name

    def get_package_name_from_path_dependency(self, dependency_rel_path: str):
        dependency_path = os.path.abspath(os.path.join(self.project_dir, dependency_rel_path, "pyproject.toml"))
        if os.path.exists(dependency_path):
            dependency_toml: TOMLDocument = TOMLFile(dependency_path).read()
            project_name = dependency_toml.get("project", {}).get("name")
            if project_name:
                return project_name

        return os.path.basename(dependency_rel_path.rstrip("/"))

    @staticmethod
    def select_input_choice(choices: list[str]) -> str:
        """Prompts the user to select from a list of choices."""
        for i, choice in enumerate(choices, 1):
            print(f"{i}. {choice}")
        choice = None
        while choice is None:
            try:
                choice = int(input("Enter the number of your choice: "))
                if choice < 1 or choice > len(choices):
                    choice = None
                    print("Invalid choice. Please enter a number from the list.")
            except ValueError:
                print("Invalid choice. Please enter a number.")
        return choices[choice - 1]

    def convert_deps_list(self, deps_list: dict) -> tuple[Array, Array]:
        """
        returns list of normal deps and list of inherited projects
        """
        deps = tomlkit.array()
        deps.multiline(True)
        members = tomlkit.array()
        members.multiline(True)
        for name, dep_v in deps_list.items():
            # skip this case, as it's handled separately
            if name == "python":
                continue

            if isinstance(dep_v, dict):
                dep_map = deepcopy(dep_v)

                if "git" in dep_map:
                    pkg_name = self.handle_git_entry(dep_map)
                    deps.append(pkg_name)
                    continue
                if "url" in dep_map:
                    dep_url = dep_map.pop("url")
                    source = tomlkit.inline_table()
                    source.update({"url": dep_url})
                    self.sources[name] = source
                    deps.append(name)

                # get a local package from a repo path
                if "path" in dep_map:
                    member = dep_map.pop("path")
                    # for some reason, `uv lock` doesn't work unless the source members are altered from .e.g 'config'
                    member_name = self.get_package_name_from_path_dependency(member)
                    members.append(member)
                    deps.append(member_name)
                    source = tomlkit.inline_table()
                    source.update({"path": member})
                    self.sources[member_name] = source
                    if "develop" in dep_map:
                        print(
                            f"warning, {members[-1]} was labeled as 'develop'={dep_map.pop('develop')}, "
                            f"but workspace members are always editable"
                        )
                vers = ""  # version string
                if "extras" in dep_map:
                    vers = str(dep_map.pop("extras")).replace("'", "")
                if "version" in dep_map:
                    converted_version = self.convert_version_entry(dep_map.pop("version"))
                    vers = f"{vers}{converted_version}"
                optional = dep_map.pop("optional", False)
                if vers and not optional:
                    deps.append(f"{name}{vers}")
                if dep_map:
                    raise NotImplementedError(
                        f"Remaining key{'s' if len(dep_map.keys()) > 1 else ''} in deps entry: {dep_map.keys()}"
                    )

            elif dep_v:  # convert a basic version string
                dep_v = self.convert_version_entry(dep_v)
                deps.append(f"{name}{dep_v}")

        return deps, members

    def extract_from_requirements_txt(self, requirements_file: str) -> Array:
        """Extracts an array list of dependencies from a requirements.txt file."""
        reqs = tomlkit.array()
        reqs.multiline(True)
        with open(f"{self.project_dir}/{requirements_file}") as f:
            for line in f.readlines():
                split_line = line.split()
                if len(split_line) > 0 and (len(split_line) == 1 or split_line[1] == ";"):
                    reqs.append(split_line[0])
        return reqs

    def get_author_name_email(self, author_full: str) -> tomlkit.api.InlineTable:
        """Converts a full author string to a PEP 621 author table."""
        author_table = tomlkit.inline_table()
        if (match := self.author_pattern.match(author_full)) is not None:
            name, email = match.groups()
            author_table.update({"name": name, "email": email})
        else:
            author_table.update({"name": author_full})
        return author_table

    def convert_to_pep508(
        self, input_file: PathLike, output_file: PathLike, exported_reqs: str = "", keep_poetry: bool = False
    ) -> None:
        """Converts a Poetry-style pyproject.toml to PEP 508 format.
        :param input_file: The input pyproject.toml file to read from.
        :param output_file: The output pyproject_pep508.toml file to write to.
        :param exported_reqs: The exported requirements.txt file to write to.
        :param keep_poetry: If True, keep the Poetry sections in the output file. This will allow cross-compatibility.
        """

        with open(f"{self.project_dir}/{input_file}", "r") as f:
            pyproject_data = tomlkit.parse(f.read())

        # Extract relevant data from the Poetry section
        tool_data = pyproject_data.get("tool", {})
        try:
            poetry_data = tool_data.pop("poetry") if not keep_poetry else tool_data.get("poetry", {})
        except NonExistentKey:
            print("tool keys:", tool_data.keys(), sep="\n")
            raise
        project_name = poetry_data.get("name")
        version = poetry_data.get("version")
        description = poetry_data.get("description")
        authors = poetry_data.get("authors")
        dependencies = poetry_data.get("dependencies", {})
        dev_dependencies = poetry_data.get("dev-dependencies", {})
        self.sources = {}

        # get main and dev deps
        python_version = self.convert_version_entry(dependencies["python"])
        deps, members = self.convert_deps_list(dependencies)
        dev_deps, dev_members = self.convert_deps_list(dev_dependencies)
        members.extend(dev_members)

        # Construct the workspace table which specifies inherited projects
        workspace_table = tomlkit.inline_table()
        workspace_table.update({"members": members})
        # currently not using the workspace block

        # get optional deps groups
        optional_deps = {}
        groups = poetry_data.get("group", {})
        for group_name, group in groups.items():
            opt_deps, opt_members = self.convert_deps_list(group["dependencies"])
            optional_deps[group_name] = opt_deps

        # convert authors to PEP 621 format
        author_tables = [self.get_author_name_email(author) for author in authors]
        authors = tomlkit.array()
        authors.extend(author_tables)

        optional_deps["dev"] = dev_deps

        # Construct the PEP 508 project table
        pep508_data = {
            "project": {
                "name": project_name,
                "version": version,
                "requires-python": python_version,
                "description": description,
                "authors": authors,
                "dependencies": deps,
            },
            "tool": {
                "uv": {
                    "sources": self.sources,
                },
                **tool_data,
            },
            "dependency-groups": optional_deps,
        }

        if "extras" in poetry_data:
            pep508_data["project"]["optional-dependencies"] = deepcopy(poetry_data["extras"])

        if not keep_poetry:
            pyproject_data.pop("build-system", None)

        # add the PEP 508 data to the pyproject.toml file
        pyproject_data.update(pep508_data)

        # Remove entries specified by the user
        for entry in self.remove_entries:
            dict_level = pyproject_data
            keys = entry.split(".")
            for key in keys[:-1]:
                dict_level = dict_level[key]
            if keys[-1] in dict_level:
                dict_level.pop(keys[-1])

        # create a new container to write the data to
        container = tomlkit.api.Container()
        container.update(pyproject_data)
        pyproject_data = container

        # Write the PEP 508 data to the output file
        with open(f"{self.project_dir}/{output_file}", "w") as f:
            tomlkit.dump(pyproject_data, f)

        # if specified, get exact versions from an exported requirements.txt file
        if exported_reqs:
            pyproject_data["project"]["dependencies"] = self.extract_from_requirements_txt(exported_reqs)
            optional_deps.clear()
            with open(f"{self.project_dir}/pyproject_pinned.toml", "w") as f:
                tomlkit.dump(pyproject_data, f)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("input_file", default="pyproject.toml", nargs="?", help="Input file")
    parser.add_argument("output_file", default="pyproject_pep508.toml", nargs="?", help="Output file")
    parser.add_argument("--project-dir", default=".", help="Project directory containing pyproject.toml")
    parser.add_argument("--requirements", dest="exported_reqs", help="input requirements file")
    parser.add_argument("--keep-poetry", action="store_true", help="Keep Poetry sections in the output file")
    parser.add_argument("--prompt-for-version", action="store_true", help="Prompt for version selection")
    parser.add_argument("--remove-entries", nargs="+", help="Remove entries from the pyproject.toml file")
    args = parser.parse_args()

    PyProject(
        **vars(args),
    )
