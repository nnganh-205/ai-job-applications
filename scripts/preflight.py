"""Read-only readiness report; never launches services or changes data."""
import importlib.util
import json
from pathlib import Path
import os
import shutil
import sys
from urllib.request import urlopen


def main():
    report = {'python': sys.version.split()[0], 'tools': {name: shutil.which(name) for name in ('bun', 'node', 'docker', 'ollama')}, 'storage': os.getenv('KLTN_STORAGE', 'json')}
    root = Path(__file__).resolve().parents[1]
    report['pdf'] = {'pillow': importlib.util.find_spec('PIL') is not None,
                     'fonts': all((root / 'frontend/public/fonts' / name).is_file() for name in ('NotoSans.ttf','NotoSerif.ttf'))}
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as engine:
            binary = os.getenv('CV_CHROME_BINARY') or engine.chromium.executable_path
            # --only-shell installs a separate headless-shell executable.
            cache_default = Path.home() / ('Library/Caches/ms-playwright' if sys.platform == 'darwin' else '.cache/ms-playwright')
            cache = Path(os.getenv('PLAYWRIGHT_BROWSERS_PATH',str(cache_default)))
            report['pdf']['chromium_installed'] = Path(binary).is_file() or (not os.getenv('CV_CHROME_BINARY') and any(cache.glob('chromium_headless_shell-*/**/chrome-headless-shell')))
    except ImportError:
        report['pdf']['chromium_installed'] = False
    report['assets'] = {'directory': os.getenv('KLTN_ASSET_STORAGE',str(root / 'backend/storage/assets')),
                        'owner': os.getenv('WORKSPACE_OWNER_ID','local-demo')}
    report['worker_enabled'] = os.getenv('KLTN_WORKER_ENABLED','1') == '1'
    try:
        with urlopen(os.getenv('OLLAMA_BASE_URL', 'http://127.0.0.1:11434') + '/api/tags', timeout=5) as response:
            report['models'] = [model['name'] for model in json.load(response)['models']]
    except Exception as error:
        report['ollama_error'] = type(error).__name__
    if report['storage'] == 'postgres':
        from backend.app.db.database import connect
        try:
            with connect() as connection:
                report['database'] = connection.execute('SELECT current_database() AS name, version() AS version').fetchone()
                report['records'] = connection.execute('SELECT kind,count(*) AS count FROM kltn_app.records GROUP BY kind ORDER BY kind').fetchall()
                report['postings'] = connection.execute('SELECT count(*) AS count FROM kltn_app.job_postings').fetchone()['count']
        except Exception as error:
            report['database_error'] = type(error).__name__
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if 'ollama_error' in report or 'database_error' in report or not all(report['pdf'].values()) else 0


if __name__ == '__main__':
    raise SystemExit(main())
