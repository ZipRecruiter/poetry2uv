# PoetryTwoUv
Conversion tool for converting poetry projects to uv projects. 
The resulting `pyproject.toml` file will be PEP 621 compliant and a `uv.lock` file will be generated.
This uv lock file will preserve the locked versions in the poetry.lock file


## Running
```bash
poetry2uv <path_to_poetry_project>
```


## Poetry to uv translation

### optional dependencies
Poetry 
```toml
[tool.poetry.dependencies]
datadog = { version = "*", optional = true }
yappi = { version = ">=1.2.4", optional = true }
"repoze.lru" = { version = ">=0.7", optional = true }

# A list of all the optional dependencies, some of which are included in the
# below `extras`. They can be opted into by apps.
[tool.poetry.extras]
statsd = ["datadog"]
zr_context = ["repoze.lru", "python-dateutil", "pytz"]
server_timing = ["yappi"]
```
translates to uv (PEP 735)
```toml
[project.optional-dependencies]
statsd = ["datadog"]
zr_context = ["repoze.lru", "python-dateutil", "pytz"]
server_timing = ["yappi"]
```

### Groups
```toml
[tool.poetry.group.X.dependencies]
foo = { version = "*" }
bar = { version = "*" }
```
translates to 
```toml
[dependency-groups]
X = [
    "foo", 
    "bar",
]
```
