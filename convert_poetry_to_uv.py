import os
import re

import tomlkit


class PyProject:

    version_pattern = re.compile(r'^([^\d]?)([\d.]+)')
    author_pattern = re.compile(r"^(.*?)\s+<([^>]+)>$")
    git_source_keys = {'git', 'rev', 'tag', 'branch'}

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
            source.update({k: v for k, v in version.items() if k in self.git_source_keys})
            self.sources[package_name] = source
            return ''
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
            elif isinstance(dep_v, dict):
                if 'path' in dep_v:
                    members.append(dep_v.pop('path'))
                    if 'develop' in dep_v:
                        print(f"warning, {members[-1]} was labeled as 'develop'={dep_v.pop('develop')}, but workspace members are always editable")
                vers = ''
                if 'extras' in dep_v:
                    vers = dep_v.pop('extras')
                if 'version' in dep_v:
                    conv_v = self.convert_version_constraint(dep_v.pop('version'))
                    vers = f"{vers}{conv_v}"
                if vers:
                    deps.append(f"{name}{vers}")
                if dep_v:
                    raise NotImplementedError(f"Remaining key{'s' if len(dep_v.keys()) > 1 else ''} in deps entry: {dep_v.keys()}")
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
                if len(split_line) > 0 and (len(split_line) == 1 or split_line[1] == ';'):
                    reqs.append(split_line[0])
        return reqs

    def get_author_name_email(self, author_full: str) -> tomlkit.items.InlineTable:
        author_table = tomlkit.inline_table()
        if (match := self.author_pattern.match(author_full)) is not None:
            name, email = match.groups()
            author_table.update({'name': name, 'email': email})
        else:
            author_table.update({'name': author_full})
        return author_table

    def convert_to_pep508(self, input_file: str, output_file: str, exported_reqs: str = ''):
        """Converts a Poetry-style pyproject.toml to PEP 508 format.
        :param input_file: The input pyproject.toml file to read from.
        :param output_file: The output pyproject_pep508.toml file to write to.
        :param exported_reqs: The exported requirements.txt file to write to."""

        with open(input_file, 'r') as f:
            data = tomlkit.parse(f.read())

        # Extract relevant data from the Poetry section
        tool = data.pop('tool', {})
        poetry_data = tool.pop('poetry')
        project_name = poetry_data.pop('name')
        version = poetry_data.pop('version')
        description = poetry_data.pop('description')
        authors = poetry_data.pop('authors')
        dependencies = poetry_data.pop('dependencies', {})
        dev_dependencies = poetry_data.pop('dev-dependencies', {})
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

        # convert authors to PEP 621 format
        author_tables = [self.get_author_name_email(author) for author in authors]
        authors = tomlkit.array()
        authors.extend(author_tables)

        # get any entries that remain
        if tool:
            print('remaining keys in tool:', tool.keys())
            #raise

        # remove keys known to be unneeded
        data.pop('build-system', None)
        if data:
            print('remaining keys in data:', data.keys())

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
                },
                **tool,
            }
        }
        container = tomlkit.container.Container()
        container.update(pep508_data)
        pep508_data = container

        # Write the PEP 508 data to the output file
        with open(output_file, 'w') as f:
            tomlkit.dump(pep508_data, f)

        # if specified, get exact versions from an exported requirements.txt file
        if exported_reqs:
            pep508_data['project']['dependencies'] = self.extract_from_requirements_txt(exported_reqs)
            optional_deps.clear()
            with open('pyproject_pinned.toml', 'w') as f:
                tomlkit.dump(pep508_data, f)

    
if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('input_file', default='pyproject.toml', nargs='?', help='Input file')
    parser.add_argument('output_file', default='pyproject_pep508.toml', nargs='?', help='Output file')
    parser.add_argument('--requirements', help='input requirements file')
    args = parser.parse_args()
    
    PyProject(args.input_file, args.output_file, args.requirements)
