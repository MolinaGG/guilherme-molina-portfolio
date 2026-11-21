"""Bounded, single-attempt GitHub Contents storage with optimistic locking.

An injected transport accepts urllib.request.Request and returns (status, bytes).
After a failed write discard the instance and reconcile using a fresh load.
"""
import base64
import hashlib
import json
import re
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener


MAX_CONTENT = 10 * 1024 * 1024
MAX_RESPONSE = 15 * 1024 * 1024


class StoreError(RuntimeError):
    """Safe storage failure; never contains server bodies or credentials."""


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _transport(request):
    opener = build_opener(_NoRedirect())
    try:
        with opener.open(request, timeout=45) as response:
            return response.status, response.read(MAX_RESPONSE + 1)
    except HTTPError as error:
        status = error.code
        error.close()
        return status, b''


class GitHubStore:
    def __init__(self, repo, token, branch='main',
                 state_path='linkedin-worker/runtime/state.json', transport=None):
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9_][A-Za-z0-9_.-]*', repo):
            raise ValueError('Repository must be owner/name')
        if not isinstance(token, str) or not token or any(c.isspace() for c in token):
            raise ValueError('A valid GitHub token is required')
        if not isinstance(branch, str) or not branch or any(ord(c) < 32 for c in branch):
            raise ValueError('A branch is required')
        self._validate_path(state_path)
        self.repo, self.branch, self.state_path = repo, branch, state_path
        self._token = token
        self._transport = transport or _transport
        self.sha = None
        self._loaded = False
        self._failed = False

    @staticmethod
    def _validate_path(path):
        if not isinstance(path, str) or not re.fullmatch(r'[A-Za-z0-9_./-]+', path) or any(p in ('', '.', '..') for p in path.split('/')):
            raise ValueError('Invalid repository path')

    def _request(self, method, endpoint, payload=None, raw=False):
        if self._failed:
            raise StoreError('Storage is blocked after a failed operation; reconcile with a fresh instance')
        headers = {'Authorization': 'Bearer ' + self._token,
                   'Accept': 'application/vnd.github.raw+json' if raw else 'application/vnd.github+json',
                   'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'linkedin-worker'}
        data = None
        if payload is not None:
            data = json.dumps(payload, allow_nan=False).encode('utf-8')
            headers['Content-Type'] = 'application/json'
        request = Request('https://api.github.com/repos/' + self.repo + endpoint,
                          data=data, headers=headers, method=method)
        try:
            status, body = self._transport(request)
            if not isinstance(body, bytes) or len(body) > MAX_RESPONSE:
                raise StoreError('GitHub response exceeded the supported size')
            if status not in (200, 201) and not (method == 'GET' and status == 404):
                raise StoreError('GitHub storage request failed (HTTP %d)' % status)
            return status, body
        except Exception:
            self._failed = True
            raise StoreError('GitHub storage request failed; no retry was attempted') from None

    @staticmethod
    def _json(body):
        try:
            result = json.loads(body)
            if not isinstance(result, dict):
                raise ValueError()
            return result
        except Exception:
            raise StoreError('Invalid GitHub JSON response') from None

    @staticmethod
    def _sha(value):
        if not isinstance(value, str) or not re.fullmatch(r'[0-9a-f]{40,64}', value):
            raise StoreError('Missing or invalid GitHub object SHA')
        return value

    def _read(self, path):
        status, body = self._request('GET', '/contents/' + quote(path, safe='/') + '?' + urlencode({'ref': self.branch}))
        if status == 404:
            return None, None
        metadata = self._json(body)
        sha = self._sha(metadata.get('sha'))
        if metadata.get('size', 0) > MAX_CONTENT:
            raise StoreError('GitHub file exceeds the supported 10 MiB limit')
        if metadata.get('encoding') == 'base64':
            try:
                content = base64.b64decode(''.join(metadata['content'].split()), validate=True)
            except Exception:
                raise StoreError('Invalid GitHub content encoding') from None
        elif metadata.get('encoding') == 'none':
            status, content = self._request('GET', '/git/blobs/' + sha, raw=True)
            if status == 404:
                raise StoreError('GitHub blob unavailable')
        else:
            raise StoreError('Unsupported GitHub content encoding')
        if len(content) > MAX_CONTENT:
            raise StoreError('GitHub file exceeds the supported 10 MiB limit')
        return content, sha

    def load(self):
        self._loaded = False
        content, sha = self._read(self.state_path)
        result = None if content is None else self._json(content)
        self.sha = sha
        self._loaded = True
        return result

    def _write(self, path, content, sha=None):
        if len(content) > MAX_CONTENT:
            raise StoreError('GitHub file exceeds the supported 10 MiB limit')
        payload = {'message': 'Update LinkedIn worker data', 'branch': self.branch,
                   'content': base64.b64encode(content).decode('ascii')}
        if sha is not None:
            payload['sha'] = sha
        try:
            _, body = self._request('PUT', '/contents/' + quote(path, safe='/'), payload)
            return self._sha(self._json(body).get('content', {}).get('sha'))
        except Exception:
            self._failed = True
            raise StoreError('GitHub write not confirmed; reconcile before proceeding') from None

    def save(self, state):
        if not self._loaded or self._failed:
            raise StoreError('Load durable state before saving; failed writes require reconciliation')
        if not isinstance(state, dict):
            raise ValueError('State must be a dictionary')
        content = json.dumps(state, ensure_ascii=False, sort_keys=True, allow_nan=False).encode('utf-8')
        self.sha = self._write(self.state_path, content, self.sha)

    def publish_image(self, path: Path):
        with Path(path).open('rb') as source:
            content = source.read(MAX_CONTENT + 1)
        if len(content) > MAX_CONTENT:
            raise StoreError('Image exceeds the supported 10 MiB limit')
        target = 'assets/linkedin/' + hashlib.sha256(content).hexdigest() + '.png'
        existing, _ = self._read(target)
        if existing is None:
            self._write(target, content)
        elif existing != content:
            raise StoreError('Existing hashed image differs; refusing overwrite')
        return 'https://raw.githubusercontent.com/' + self.repo + '/' + quote(self.branch, safe='') + '/' + target
