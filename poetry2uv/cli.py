import subprocess
import sys
from pathlib import Path


def main():
    script_path = str(Path(__file__).parent.parent / 'bin' / 'convert_poetry_to_uv.sh')
    result = subprocess.run([script_path] + sys.argv[1:], capture_output=True, text=True)
    print(result.stdout)
    print(result.stderr, file=sys.stderr)
    if result.returncode != 0:
        raise SystemExit(result.returncode)
    sys.exit(result.returncode)


if __name__ == '__main__':
    main()