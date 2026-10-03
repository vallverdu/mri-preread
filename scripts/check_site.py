"""Check static website links, assets, accessibility basics and JavaScript syntax offline."""
import argparse
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
import subprocess
import tempfile
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]


class Page(HTMLParser):
    def __init__(self, source):
        super().__init__(convert_charrefs=True)
        self.ids = []
        self.refs = []
        self.copy_targets = []
        self.scripts = []
        self.problems = []
        self.current_script = None
        self.title = False
        self.lang = False
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if a.get('id'):
            self.ids.append(a['id'])
        if tag == 'html':
            self.lang = bool(a.get('lang'))
        if tag == 'title':
            self.title = True
        if tag == 'img' and 'alt' not in a:
            self.problems.append('image has no alt attribute')
        if 'data-copy' in a:
            self.copy_targets.append(a['data-copy'])
        for attr in ('href', 'src', 'data-volume', 'data-renderer'):
            if a.get(attr):
                self.refs.append((tag, attr, a[attr]))
        if tag == 'script' and not a.get('src') and a.get('type', 'text/javascript') in ('text/javascript', 'module'):
            self.current_script = (a.get('type', 'text/javascript'), [])

    def handle_data(self, data):
        if self.current_script:
            self.current_script[1].append(data)

    def handle_endtag(self, tag):
        if tag == 'script' and self.current_script:
            kind, chunks = self.current_script
            self.scripts.append((kind, ''.join(chunks)))
            self.current_script = None


def check(site):
    pages = {p.resolve(): Page(p.read_text()) for p in site.rglob('*.html')}
    issues = []
    for path, page in pages.items():
        name = path.relative_to(site).as_posix()
        for problem in page.problems:
            issues.append(f'{name}: {problem}')
        if not page.title or not page.lang:
            issues.append(f'{name}: missing page title or language')
        duplicates = [key for key, count in Counter(page.ids).items() if count > 1]
        if duplicates:
            issues.append(f'{name}: duplicate IDs: {duplicates}')
        for target in page.copy_targets:
            if target not in page.ids:
                issues.append(f'{name}: missing copy target {target}')
        for tag, attr, ref in page.refs:
            url = urlsplit(ref)
            asset = attr in ('src', 'data-volume', 'data-renderer') or tag == 'link'
            if url.scheme in ('http', 'https', 'mailto') or url.netloc:
                if asset:
                    issues.append(f'{name}: remote runtime asset {ref}')
                continue
            if url.scheme:
                if url.scheme == 'data' and tag == 'img':
                    continue
                issues.append(f'{name}: unexpected URL scheme in {tag}')
                continue
            target = (path.parent / unquote(url.path)).resolve() if url.path else path
            if not target.is_relative_to(site):
                issues.append(f'{name}: link escapes the site: {ref}')
                continue
            if target.is_dir():
                target /= 'index.html'
            if not target.is_file():
                issues.append(f'{name}: missing local target {ref}')
            elif url.fragment and target in pages and target.relative_to(site).as_posix() != 'demo/index.html':
                if unquote(url.fragment) not in pages[target].ids:
                    issues.append(f'{name}: missing fragment {ref}')
        for kind, script in page.scripts:
            suffix = '.mjs' if kind == 'module' else '.js'
            with tempfile.NamedTemporaryFile(mode='w', suffix=suffix) as f:
                f.write(script); f.flush()
                result = subprocess.run(['node', '--check', f.name], capture_output=True, text=True)
                if result.returncode:
                    issues.append(f'{name}: inline JavaScript syntax failed: {result.stderr.strip()}')
    for path in site.rglob('*.js'):
        result = subprocess.run(['node', '--check', str(path)], capture_output=True, text=True)
        if result.returncode:
            issues.append(f'{path.relative_to(site)}: JavaScript syntax failed: {result.stderr.strip()}')
    return issues, len(pages)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--site', type=Path, default=ROOT / 'site')
    site = parser.parse_args().site.resolve()
    if not (site / 'index.html').is_file():
        raise SystemExit('Expected a static site directory with index.html')
    issues, count = check(site)
    for issue in issues:
        print(f'FAIL {issue}')
    print(f'Checked {count} HTML pages, local links/assets and JavaScript; {len(issues)} issue(s).')
    raise SystemExit(bool(issues))


if __name__ == '__main__':
    main()
