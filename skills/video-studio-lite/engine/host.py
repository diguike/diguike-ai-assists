"""This computer: where episodes live, which ffmpeg and which browser to use.

An optional studio.json next to engine/ changes the defaults of a copy of the
engine: {"home": workspace for episodes/ and work/, "base": base preset,
"defaults": META defaults}. Without it (this repo) everything stays in the repo.
STUDIO_HOME overrides home.
"""
import json
import os
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
_conf = REPO / 'studio.json'
CONF = json.loads(_conf.read_text(encoding='utf-8')) if _conf.exists() else {}
HOME = Path(os.environ.get('STUDIO_HOME') or CONF.get('home') or REPO).expanduser()


def ffmpeg():
    """ffmpeg on PATH, else the one bundled with the imageio-ffmpeg package (Windows without an install)."""
    exe = shutil.which('ffmpeg')
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def ffprobe():
    return shutil.which('ffprobe')


def browser():
    """An installed Chrome or Edge, or None for Playwright's own Chromium."""
    if sys.platform == 'darwin':
        apps = ['Google Chrome.app/Contents/MacOS/Google Chrome', 'Microsoft Edge.app/Contents/MacOS/Microsoft Edge']
        cands = [str(root / a) for a in apps for root in (Path('/Applications'), Path.home() / 'Applications')]
    elif os.name == 'nt':
        roots = [os.environ.get(k) for k in ('PROGRAMFILES', 'PROGRAMFILES(X86)', 'LOCALAPPDATA')]
        apps = [r'Google\Chrome\Application\chrome.exe', r'Microsoft\Edge\Application\msedge.exe']
        cands = [str(Path(r) / a) for a in apps for r in roots if r]
    else:
        cands = [shutil.which(n) or '' for n in ('google-chrome', 'google-chrome-stable', 'chromium', 'chromium-browser',
                                                  'microsoft-edge')]
    return next((c for c in cands if c and Path(c).exists()), None)


def place(src, dst):
    """dst standing for src: a symlink, or on Windows (no symlinks without developer mode) hard links or copies."""
    if os.name != 'nt':
        try:
            dst.symlink_to(src)
            return
        except OSError:
            pass
    if src.is_dir():
        shutil.copytree(src, dst, copy_function=_link)
    else:
        _link(src, dst)


def _link(src, dst):
    try:
        os.link(src, dst)
    except OSError:  # another drive
        shutil.copy2(src, dst)
