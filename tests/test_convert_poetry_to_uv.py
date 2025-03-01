import difflib
from pathlib import Path
from sys import stderr

import pytest

from poetry2uv.convert_poetry_to_uv import PyProject

resources_path = Path(__file__).resolve().parent / "resources"


@pytest.fixture(scope="session")
def converter() -> PyProject:
    """Provides a fresh instance of VersionConverter for each test."""
    return PyProject("pyproject_in.toml", "pyproject_out.toml", resources_path, prompt_for_version=False)


@pytest.mark.parametrize(
    "constraint, expected",
    [
        # base cases
        ("*", ""),
        ("1.0", "==1.0"),  # No symbol => treat as '=='
        ("=1.2.3", "==1.2.3"),  # '=' => '=='
        # simple cases
        (">=3.2.4,<4.5", ">=3.2.4,<4.5"),  # multiple constraints
        (">3.8.2,<3.9", ">3.8.2,<3.9"),  # multiple constraints
        ("==1.2.3", "==1.2.3"),  # Explicit '==' => no change
        ("!=1.2.3", "!=1.2.3"),  # '!=' => no change
        ("<1.2.3", "<1.2.3"),  # '<' => no change
        ("<=1.2.3", "<=1.2.3"),  # '<=' => no change
        (">1.2.3", ">1.2.3"),  # '>' => no change
        (">=1.2.3", ">=1.2.3"),  # '>=' => no change
        # Edge cases
        ("", ""),  # Empty constraint => no constraint
        # tilde cases
        ("~1.2.3", ">=1.2.3,<1.3.0"),
        ("~1.2", ">=1.2,<1.3"),
        ("~1", ">=1,<2"),
        ("~0.1.0", ">=0.1.0,<0.2.0"),  # '~0.1.0' => ">=0.1.0,<0.2.0"
        ("~0.0.1", ">=0.0.1,<0.0.2"),  # '~0.0.1' => ">=0.0.1,<0.0.2"
        ("~2.1", ">=2.1,<2.2"),  # '~2.1' => ">=2.1,<2.2"
        ("~10", ">=10,<11"),  # '~10' => ">=10,<11"
        # caret cases
        ("^2.0", ">=2.0,<3"),  # '^2.0' => ">=2.0,<3"
        ("^2.1.3", ">=2.1.3,<3"),  # '^2.1.3' => ">=2.1.3,<3"
        ("^3.1.4", ">=3.1.4,<4"),  # '^3.1.4' => ">=3.1.4,<4"
        ("^0.1.0", ">=0.1.0,<0.2"),  # '^0.1.0' => ">=0.1.0,<0.2.0"
        ("^0.0.1", ">=0.0.1,<0.0.2"),  # '^0.0.1' => ">=0.0.1,<0.0.2"
        # Complex cases
        (">=1.0.0,<2.0.0,!=1.2.3", ">=1.0.0,<2.0.0,!=1.2.3"),  # Multiple constraints with '!='
        ("^1.0.0,!=1.0.1", ">=1.0.0,<2,!=1.0.1"),  # '^' with '!='
        ("~1.0.0,!=1.0.1", ">=1.0.0,<1.1.0,!=1.0.1"),  # '~' with '!='
        # Wildcard cases
        ("1.*", "==1.*"),  # Major version wildcard
        ("1.2.*", "==1.2.*"),  # Minor version wildcard
        ("1.2.3.*", "==1.2.3.*"),  # Patch version wildcard
        # extras
        ("^1.0.0-alpha", ">=1.0.0-alpha,<2"),  # Pre-release version with '^'
        ("~1.0.0-beta", ">=1.0.0-beta,<1.1.0"),  # Pre-release version with '~'
        # unusual cases
        ("1.2.3.4", "==1.2.3.4"),  # Version with more than 3 parts
        ("1.2.3-beta.2", "==1.2.3-beta.2"),  # Version with pre-release and build metadata
        # aspirational
        # ("~0.0.3-alpha", ">=0.0.3-alpha,<0.0.4"),  # Pre-release version with '~'
        # ("invalid", ""),  # Invalid constraint => no constraint
    ],
)
def test_version_pattern(converter: PyProject, constraint: str, expected: str):
    """Check various symbols and numeric patterns."""
    assert converter.convert_version_entry(constraint) == expected


@pytest.mark.parametrize("constraint", ["~a.b.c", "^a.b"])
def test_invalid_patterns(converter: PyProject, constraint: str):
    with pytest.raises(ValueError, match="Invalid version constraint:"):
        converter.convert_version_entry(constraint)


def assert_files_equal(file1: str | Path, file2: str | Path):
    """
    Reads two files, compares their contents, and raises an AssertionError
    if they differ. Also prints a unified diff for easy debugging.
    """
    with open(file1, "r") as f1, open(file2, "r") as f2:
        lines1 = f1.readlines()
        lines2 = f2.readlines()

    if lines1 != lines2:
        diff = difflib.unified_diff(
            lines1,
            lines2,
            fromfile=file1,
            tofile=file2,
            lineterm="",  # so we don’t get extra newlines
        )
        diff_text = "\n".join(diff)
        # Print the diff to stderr (pytest will show it in test output)
        print(diff_text, file=stderr)
        raise AssertionError(f"Files differ: {file1} vs. {file2}")


def test_convert_pyproject(converter: PyProject):
    assert_files_equal(str(resources_path / "pyproject_out.toml"), str(resources_path / "pyproject_expected.toml"))
