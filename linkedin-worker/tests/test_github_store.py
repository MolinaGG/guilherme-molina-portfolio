import base64
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from github_store import GitHubStore, StoreError, _NoRedirect


class Transport:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        status, body = result
        return status, json.dumps(body).encode() if isinstance(body, dict) else body


class GitHubStoreTests(unittest.TestCase):
    def test_load_save_uses_observed_sha_and_branch(self):
        transport = Transport((200, {'sha': 'a' * 40, 'encoding': 'base64', 'content': base64.b64encode(b'{"n":1}').decode()}), (200, {'content': {'sha': 'b' * 40}}))
        store = GitHubStore('owner/repo', 'secret', branch='work/branch', transport=transport)
        self.assertEqual(store.load(), {'n': 1})
        store.save({'n': 2})
        payload = json.loads(transport.requests[1].data)
        self.assertEqual(payload['sha'], 'a' * 40)
        self.assertEqual(payload['branch'], 'work/branch')
        self.assertEqual(json.loads(base64.b64decode(payload['content'])), {'n': 2})
        self.assertIn('ref=work%2Fbranch', transport.requests[0].full_url)
        self.assertEqual(store.sha, 'b' * 40)

    def test_absent_creation_and_conflict_fail_closed_without_retry(self):
        for failure in [(409, b'secret'), OSError('secret')]:
            transport = Transport((404, b''), failure)
            store = GitHubStore('owner/repo', 'secret', transport=transport)
            self.assertIsNone(store.load())
            with self.assertRaises(StoreError) as caught:
                store.save({'n': 1})
            self.assertNotIn('secret', str(caught.exception))
            self.assertNotIn('sha', json.loads(transport.requests[1].data))
            with self.assertRaises(StoreError):
                store.save({'n': 2})
            self.assertEqual(len(transport.requests), 2)

    def test_requires_load_before_save(self):
        store = GitHubStore('owner/repo', 'secret', transport=Transport())
        with self.assertRaises(StoreError):
            store.save({})

    def test_lost_update_retains_sha_and_blocks_further_writes(self):
        transport = Transport((200, {'sha': 'a' * 40, 'encoding': 'base64', 'content': 'e30='}), OSError('secret'))
        store = GitHubStore('owner/repo', 'secret', transport=transport)
        store.load()
        with self.assertRaises(StoreError):
            store.save({'intent': 'pending'})
        self.assertEqual(store.sha, 'a' * 40)
        with self.assertRaises(StoreError):
            store.load()
        self.assertEqual(len(transport.requests), 2)

    def test_redirect_handler_never_forwards_authenticated_request(self):
        self.assertIsNone(_NoRedirect().redirect_request(None, None, 302, '', {}, 'https://evil.test'))

    def test_oversized_state_refused_before_blob_download(self):
        transport = Transport((200, {'sha': 'a' * 40, 'encoding': 'none', 'size': 11 * 1024 * 1024}))
        with self.assertRaisesRegex(StoreError, '10 MiB'):
            GitHubStore('owner/repo', 'secret', transport=transport).load()
        self.assertEqual(len(transport.requests), 1)

    def test_large_content_uses_blob_sha_not_mutable_branch(self):
        transport = Transport((200, {'sha': 'a' * 40, 'encoding': 'none', 'size': 2_000_000}), (200, b'{"n":1}'))
        store = GitHubStore('owner/repo', 'secret', transport=transport)
        self.assertEqual(store.load(), {'n': 1})
        self.assertTrue(transport.requests[1].full_url.endswith('/git/blobs/' + 'a' * 40))

    def test_image_idempotence_and_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'test.png'
            path.write_bytes(b'png-bytes')
            for content, should_fail in [(b'png-bytes', False), (b'different', True)]:
                transport = Transport((200, {'sha': 'a' * 40, 'encoding': 'base64', 'content': base64.b64encode(content).decode()}))
                store = GitHubStore('owner/repo', 'secret', transport=transport)
                if should_fail:
                    with self.assertRaises(StoreError):
                        store.publish_image(path)
                else:
                    url = store.publish_image(path)
                    self.assertEqual(url, 'https://raw.githubusercontent.com/owner/repo/main/assets/linkedin/' + hashlib.sha256(b'png-bytes').hexdigest() + '.png')
                self.assertEqual(len(transport.requests), 1)

    def test_image_create_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'test.png'
            path.write_bytes(b'png')
            transport = Transport((404, b''), (201, {'content': {'sha': 'a' * 40}}))
            GitHubStore('owner/repo', 'secret', transport=transport).publish_image(path)
            self.assertNotIn('sha', json.loads(transport.requests[1].data))

    def test_untrusted_names_and_redirects_rejected(self):
        for repo in ['https://evil/a', 'a/b/c', 'a/..', 'a/b?x']:
            with self.assertRaises(ValueError):
                GitHubStore(repo, 'secret')
        for path in ['../x', '/x', 'a//b', 'a/../b', 'a?b']:
            with self.assertRaises(ValueError):
                GitHubStore('owner/repo', 'secret', state_path=path)
        transport = Transport((302, b'secret'))
        with self.assertRaises(StoreError):
            GitHubStore('owner/repo', 'secret', transport=transport).load()
        self.assertEqual(len(transport.requests), 1)
