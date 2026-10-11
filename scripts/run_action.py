"""Run the selected action revision without interpolating inputs into a shell."""
import glob
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path


def main():
    paths = []
    for pattern in shlex.split(os.environ.get('CITEAUDIT_PATHS', 'README.md')):
        paths.extend(sorted(glob.glob(pattern)) or [pattern])
    if not paths or any(p.startswith('-') for p in paths):
        raise ValueError('provide at least one document path; option-like paths need a ./ prefix')
    args = ['--strict'] if os.environ.get('CITEAUDIT_STRICT') == 'true' else []
    if os.environ.get('CITEAUDIT_FAIL_UNDER'):
        args += ['--fail-under', os.environ['CITEAUDIT_FAIL_UNDER']]
    base = [sys.executable, '-m', 'citeaudit.cli', *paths]
    code = subprocess.run([*base, '--format', 'json', '-o', 'citeaudit.json', *args]).returncode
    subprocess.run([*base, '--format', 'html', '-o', os.environ.get('CITEAUDIT_REPORT_PATH', 'citeaudit.html'), '--quiet'])
    subprocess.run([*base, '--format', 'terminal', *args])
    output = Path('citeaudit.json')
    if output.exists():
        summary = json.loads(output.read_text())['summary']
        score = summary['integrity_score']
        lines = [f"total={summary['total_citations']}",
                 f"failures={summary['not_found']+summary['mismatch']+summary['malformed']}",
                 f"score={'' if score is None else round(score*100,1)}"]
        if os.environ.get('GITHUB_OUTPUT'):
            with open(os.environ['GITHUB_OUTPUT'], 'a') as out:
                out.write('\n'.join(lines)+'\n')
    return code if os.environ.get('CITEAUDIT_FAIL_ON_FINDINGS') == 'true' else 0


if __name__ == '__main__':
    raise SystemExit(main())
