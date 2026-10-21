"""Install or update Event Horizon in Pythonista from GitHub.

Put this one file in Pythonista and run it; run it again whenever you're online to update.
Your config/operation.json and saved app state are kept. If the repository is private, the
first run asks for a GitHub fine-grained token with read-only "Contents" access to it and keeps
the token in the iOS keychain, not in this file.
"""

import io
import os
import shutil
import zipfile

import console
import keychain
import requests

REPO = 'DudebromanUT/event-horizon-wfm'
BRANCH = 'main'
DEST = os.path.expanduser('~/Documents/event-horizon')
SERVICE, ACCOUNT = 'event-horizon', 'github-token'


def token():
    saved = keychain.get_password(SERVICE, ACCOUNT)
    if saved:
        return saved
    entered = console.input_alert('GitHub token', 'Read-only token for %s' % REPO, '', 'Save').strip()
    keychain.set_password(SERVICE, ACCOUNT, entered)
    return entered


def download(url, key=None):
    headers = {'Accept': 'application/vnd.github+json'}
    if key:
        headers['Authorization'] = 'Bearer ' + key
    return requests.get(url, headers=headers, timeout=120)


def main():
    url = 'https://api.github.com/repos/%s/zipball/%s' % (REPO, BRANCH)
    r = download(url)
    if r.status_code == 404:
        # GitHub answers 404 for a private repository when no token is sent.
        r = download(url, token())
        if r.status_code in (401, 403, 404):
            keychain.delete_password(SERVICE, ACCOUNT)
            console.alert('GitHub said %d' % r.status_code,
                          'Check that the token can read %s, then run this again.' % REPO,
                          'OK', hide_cancel_button=True)
            return
    r.raise_for_status()
    archive = zipfile.ZipFile(io.BytesIO(r.content))
    root = os.path.abspath(DEST)
    written = 0
    for name in archive.namelist():
        rel = name.split('/', 1)[1] if '/' in name else ''
        if not rel or name.endswith('/'):
            continue
        target = os.path.abspath(os.path.join(root, rel))
        if not target.startswith(root + os.sep):
            continue
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with archive.open(name) as src, open(target, 'wb') as out:
            shutil.copyfileobj(src, out)
        written += 1
    console.hud_alert('Event Horizon updated (%d files)' % written)
    print('Installed to', DEST)
    print('Open event-horizon/horizon_app.py and tap Run.')


if __name__ == '__main__':
    main()
