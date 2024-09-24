import os
import re

import tomlkit


class PyProject:

    version_pattern = re.compile(r'^([^\d]?)([\d.]+)')

    def __init__(self, input_file: str, output_file: str, exported_reqs: str = ''):
        self.convert_to_pep508(input_file, output_file, exported_reqs)

    @classmethod
    def from_file(cls, file_path: str):
        pass

    def convert_version_constraint(self, version: str) -> str:
        """Converts poetry version constraint specifications to PEP 621.."""

        constraints = []
        for constraint in str(version).split(','):
            pass
        if isinstance(version, tomlkit.items.Array):
            if len(version) > 1:
                raise NotImplementedError("Multiple constraints not supported")
            version = version[0]
            package_name = os.path.splitext(os.path.basename(version['git']))[0]
            if package_name in self.sources:
                raise NotImplementedError(f"Can not handle duped sources with name {package_name}!\n{self.sources[package_name]} -> {version['git']}")
            source = tomlkit.inline_table()
            source.update({'git': version['git']})
            self.sources[package_name] = source
            return f"{package_name} @ {version['rev']}"
        if (match := self.version_pattern.match(version)) is not None:
            symbols = match.group(1)
            numbers = match.group(2)
            if symbols in ['', '=']:
                symbols = "=="
            elif symbols == "*":
                return ""
            elif symbols == "^":
                symbols = ">="

            return f"{symbols}{numbers}"
        if version == '*':
            return ''
        return str(version)

    def convert_deps_list(self, deps_list):
        """
        returns list of normal deps and list of inherited projects
        """
        deps = tomlkit.array()
        deps.multiline(True)
        members = tomlkit.array()
        members.multiline(True)
        for name, dep_v in deps_list.items():
            if name == "python":
                python_version = dep_v
                continue
            if isinstance(dep_v, dict):
                members.append(dep_v['path'])
                continue
            elif dep_v:
                dep_v = self.convert_version_constraint(dep_v)
            deps.append(f"{name}{dep_v}")

        return deps, members


    def extract_from_requirements_txt(self, requirements_file: str):
        reqs = tomlkit.array()
        reqs.multiline(True)
        with open(requirements_file) as f:
            for line in f.readlines():
                split_line = line.split()
                if split_line[1] == ';':
                    reqs.append(split_line[0])
        return reqs


    def convert_to_pep508(self, input_file: str, output_file: str, exported_reqs: str = ''):
        """Converts a Poetry-style pyproject.toml to PEP 508 format.
        :param input_file: The input pyproject.toml file to read from.
        :param output_file: The output pyproject_pep508.toml file to write to.
        :param exported_reqs: The exported requirements.txt file to write to."""

        with open(input_file, 'r') as f:
            data = tomlkit.parse(f.read())

        # Extract relevant data from the Poetry section
        poetry_data = data.get('tool', {}).get('poetry', {})
        project_name = poetry_data.get('name')
        version = poetry_data.get('version')
        description = poetry_data.get('description')
        authors = poetry_data.get('authors')
        dependencies = poetry_data.get('dependencies', {})
        dev_dependencies = poetry_data.get('dev-dependencies', {})
        self.sources = {}

        # get main and dev deps
        python_version = dependencies['python']
        deps, members = self.convert_deps_list(dependencies)
        dev_deps, dev_members = self.convert_deps_list(dev_dependencies)
        members.extend(dev_members)

        # Construct the workspace table which specifies inherited projects
        workspace_table = tomlkit.inline_table()
        workspace_table.update({'members': members})

        # get optional deps groups
        optional_deps = {}
        groups = poetry_data.get('group', {})
        for group_name, group in groups.items():
            opt_deps, opt_members = self.convert_deps_list(group['dependencies'])
            optional_deps[group_name] = opt_deps

        # if specified, get exact versions from an exported requirements.txt file
        if exported_reqs:
            deps = self.extract_from_requirements_txt(exported_reqs)
            optional_deps = {}

        # Construct the PEP 508 project table
        pep508_data = {
            'project': {
                'name': project_name,
                'version': version,
                'requires-python': python_version,
                'description': description,
                'authors': authors,
                'dependencies': deps,
                'optional-dependencies': optional_deps,
            },
            'tool': {
                'uv': {
                    'dev-dependencies': dev_deps,
                    'workspace': workspace_table,
                    'sources': self.sources,
                }
            }
        }
        container = tomlkit.container.Container()
        container.update(pep508_data)
        pep508_data = container

        # Write the PEP 508 data to the output file
        with open(output_file, 'w') as f:
            tomlkit.dump(pep508_data, f)

    
if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('input_file', default='pyproject.toml', nargs='?', help='Input file')
    parser.add_argument('output_file', default='pyproject_pep508.toml', nargs='?', help='Output file')
    parser.add_argument('--requirements', help='input requirements file')
    args = parser.parse_args()
    
    PyProject(args.input_file, args.output_file, args.requirements)
