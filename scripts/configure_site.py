"""Wire a real GitHub source URL into the static site without a build framework."""
import argparse
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--repo-url', required=True)
args = parser.parse_args()
url = args.repo_url.rstrip('/').removesuffix('.git')
if not re.fullmatch(r'https://github\.com/[\w.-]+/[\w.-]+', url):
    raise SystemExit('Use an HTTPS GitHub OWNER/REPOSITORY URL with no credentials, query or fragment')
(ROOT / 'site/site-config.js').write_text('// Public source repository.\nwindow.MRI_SITE = ' + json.dumps({'repoUrl': url}) + ';\n')
print(f'Configured public source: {url}')
