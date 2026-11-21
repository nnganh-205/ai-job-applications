import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class EnvConfigTests(unittest.TestCase):
    def test_env_file_loads_outside_project_directory_and_exports_win(self):
        root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / '.env'
            path.write_text('GROQ_API_KEY=demo-from-file\nGROQ_TASKS=profile,assistant\nGROQ_MODEL=openai/gpt-oss-120b\n')
            env = {k:v for k,v in os.environ.items() if not k.startswith('GROQ_')}
            env.update(KLTN_ENV_FILE=str(path), PYTHONPATH=str(root))
            code = "from backend.app.core.config import settings; assert settings.groq_api_key == 'demo-from-file'; assert settings.provider_for_task('profile') == 'groq'; assert settings.provider_for_task('writer') == 'ollama'"
            subprocess.run([sys.executable, '-B', '-c', code], cwd=folder, env=env, check=True, capture_output=True)
            env['GROQ_API_KEY'] = 'exported-demo'
            code = "from backend.app.core.config import settings; assert settings.groq_api_key == 'exported-demo'"
            subprocess.run([sys.executable, '-B', '-c', code], cwd=folder, env=env, check=True, capture_output=True)

    def test_env_loading_can_be_disabled_for_isolated_tests(self):
        env = {k:v for k,v in os.environ.items() if not k.startswith('GROQ_')}
        env['KLTN_ENV_FILE'] = os.devnull
        code = "from backend.app.core.config import settings; assert settings.groq_api_key is None; assert settings.provider_for_task('profile') == 'ollama'"
        subprocess.run([sys.executable, '-B', '-c', code], env=env, check=True, capture_output=True)
