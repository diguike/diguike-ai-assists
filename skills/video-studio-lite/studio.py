# /// script
# requires-python = ">=3.10,<3.14"
# dependencies = [
#     "edge-tts==7.3.1",
#     "imageio-ffmpeg==0.6.0",
#     "jieba==0.42.1",
#     "numpy==2.2.6",
#     "pillow==12.3.0",
#     "playwright==1.58.0",
#     "pypinyin==0.55.0",
#     "scipy==1.15.3",
# ]
# ///
"""video-studio-lite: `uv run studio.py <command>` (commands: SKILL.md, or `uv run studio.py --help`).

uv builds the Python environment from the list above the first time (a minute or two) and
reuses it afterwards. The engine runs in UTF-8 mode, since Windows would otherwise read and
write the Chinese in scripts and subtitles as GBK. Videos go to ~/VideoStudio unless the
STUDIO_HOME environment variable points elsewhere (studio.json holds the defaults).
"""
import os
import subprocess
import sys
from pathlib import Path

if __name__ == '__main__':
    cli = Path(__file__).resolve().parent / 'engine' / 'cli.py'
    env = {**os.environ, 'PYTHONUTF8': '1'}
    try:
        sys.exit(subprocess.run([sys.executable, '-X', 'utf8', str(cli), *sys.argv[1:]], env=env).returncode)
    except KeyboardInterrupt:
        sys.exit(130)
