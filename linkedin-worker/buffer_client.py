"""Minimal official Buffer GraphQL client. No retries and no secret-bearing errors.

API examples verified against developers.buffer.com on 2026-11-20.
Injected transport: callable(Request) -> (status, bytes or decoded JSON dict).
"""
import http.client
import ipaddress
import json
import socket
import ssl
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError
from urllib.parse import parse_qsl, urljoin, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler


class BufferError(RuntimeError):
    """A read failed, local configuration is invalid, or a write was rejected."""


class AmbiguousWrite(BufferError):
    """A mutation may have committed. Reconcile before any further attempt."""


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _transport(request):
    try:
        with build_opener(_NoRedirect).open(request, timeout=30) as response:
            return response.status, response.read(4 * 1024 * 1024)
    except HTTPError as exc:
        return exc.code, b''


def _literal(value):
    if not isinstance(value, str) or not value.strip():
        raise BufferError('A required Buffer input is missing.')
    return json.dumps(value, ensure_ascii=True)


def _utcnow():
    return datetime.now(timezone.utc)


class BufferClient:
    def __init__(self, token, transport=None, *, recent_history=False, before_request=None):
        if not isinstance(token, str) or not token.strip() or '\n' in token or '\r' in token:
            raise BufferError('Configure BUFFER_API_KEY before connecting.')
        self._token = token.strip()
        self._transport = transport or _transport
        self.recent_history = recent_history
        self.before_request = before_request

    def _execute(self, query, mutation=False):
        failure = AmbiguousWrite if mutation else BufferError
        request = Request('https://api.buffer.com', data=json.dumps({'query':query}).encode(),
                          headers={'Authorization':'Bearer ' + self._token,
                                   'Content-Type':'application/json'}, method='POST')
        if self.before_request is not None:
            self.before_request()
        try:
            status, body = self._transport(request)
        except Exception:
            raise failure('Buffer connection failed; reconcile any pending write.') from None
        if status in (401,403):
            raise BufferError('Buffer authentication or permission was rejected.')
        if status == 429:
            raise BufferError('Buffer rate limit reached; wait before another run.')
        if status != 200:
            raise failure('Buffer returned an unsuccessful HTTP response; reconcile pending writes.')
        try:
            payload = json.loads(body) if isinstance(body,(str,bytes,bytearray)) else body
            if not isinstance(payload,dict) or payload.get('errors') or not isinstance(payload.get('data'),dict):
                raise ValueError()
            return payload['data']
        except Exception:
            raise failure('Buffer response was incomplete or contained GraphQL errors.') from None

    def organizations(self):
        data = self._execute('query { account { organizations { id name } } }')
        try:
            items = data['account']['organizations']
            if not isinstance(items,list): raise ValueError()
            return items
        except (KeyError,TypeError,ValueError):
            raise BufferError('Buffer organization response was incomplete.') from None

    def channels(self, org_id):
        data = self._execute('query { channels(input: {organizationId: ' + _literal(org_id) + '}) {id name service} }')
        if not isinstance(data.get('channels'),list):
            raise BufferError('Buffer channel response was incomplete.')
        return data['channels']

    def list_posts(self, org_id, channel_id):
        """Fetch complete history by default, or all unsent plus seven-day sent.

        Recent mode requires an authoritative durable journal. An unresolved
        write older than this window must remain blocked until a full scan.
        Verified schema: developers.buffer.com/types/PostsFiltersInput.html and
        developers.buffer.com/types/PostStatus.html (2026-11-20).
        """
        if not self.recent_history:
            return self._list_posts_filtered(org_id, channel_id)
        since = (_utcnow() - timedelta(days=7)).isoformat().replace('+00:00', 'Z')
        unsent = self._list_posts_filtered(org_id, channel_id,
                    ', status: [draft, error, needs_approval, scheduled, sending]')
        sent = self._list_posts_filtered(org_id, channel_id,
                    ', status: [sent], dueAt: {start: ' + _literal(since) + '}')
        # A post can transition while the two independently paginated scans run.
        return list({post['id']: post for post in unsent + sent}.values())

    def _list_posts_filtered(self, org_id, channel_id, extra_filter=''):
        posts, cursor, seen = [], None, set()
        while True:
            after = '' if cursor is None else ', after: ' + _literal(cursor)
            query = ('query { posts(first: 100' + after + ', input: {organizationId: ' + _literal(org_id)
                     + ', filter: {channelIds: [' + _literal(channel_id) + ']' + extra_filter + '}}) '
                     '{edges {node {id text dueAt status channelId}} pageInfo {hasNextPage endCursor}} }')
            data = self._execute(query)
            try:
                page = data['posts']
                if not isinstance(page['edges'],list): raise ValueError()
                for edge in page['edges']:
                    node = edge['node']
                    if not isinstance(node,dict) or not node.get('id'): raise ValueError()
                    posts.append(node)
                info = page['pageInfo']
                if not isinstance(info['hasNextPage'],bool): raise ValueError()
                if not info['hasNextPage']: return posts
                cursor = info['endCursor']
                if not isinstance(cursor,str) or not cursor or cursor in seen: raise ValueError()
                seen.add(cursor)
            except (KeyError,TypeError,ValueError):
                raise BufferError('Buffer pagination response was incomplete or repeated.') from None

    def create_post(self, channel_id, text, due_at, image_url):
        query = ('mutation { createPost(input: {channelId: ' + _literal(channel_id)
                 + ', text: ' + _literal(text) + ', schedulingType: automatic, mode: customScheduled, dueAt: '
                 + _literal(due_at) + ', assets: [{image: {url: ' + _literal(image_url) + '}}]}) '
                 '{__typename ... on PostActionSuccess {post {id dueAt status assets {id mimeType}}} '
                 '... on MutationError {message}} }')
        data = self._execute(query, mutation=True)
        result = data.get('createPost')
        if isinstance(result,dict):
            if result.get('__typename') == 'MutationError' or ('message' in result and not result.get('post')):
                raise BufferError('Buffer rejected the post; inspect channel and scheduling configuration.')
            post = result.get('post')
            if (isinstance(post,dict) and post.get('id') and post.get('dueAt') and post.get('status')
                    and isinstance(post.get('assets'),list) and post['assets']):
                return post
        raise AmbiguousWrite('Buffer did not confirm the complete image post; reconcile before retrying.')


def _public_target(url):
    try:
        parsed = urlsplit(url)
        host = parsed.hostname
        if parsed.scheme != 'https' or not host or parsed.username or parsed.password or parsed.port not in (None,443):
            raise ValueError()
        if parsed.fragment or host.lower().endswith(('.localhost','.local','.internal')) or '.' not in host and ':' not in host:
            raise ValueError()
        if host.lower() in ('drive.google.com','docs.google.com','www.dropbox.com','dropbox.com','1drv.ms'):
            raise ValueError()
        if any(any(term in key.lower() for term in ('token','signature','credential','auth','key','expires')) for key,_ in parse_qsl(parsed.query)):
            raise ValueError()
        addresses = socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
            raise ValueError()
        return parsed, addresses[0][4][0]
    except Exception:
        raise BufferError('Image URL must be stable public HTTPS without credentials, previews or private addresses.') from None


def _fetch_image(parsed, address):
    # Pin the validated address while retaining TLS certificate validation/SNI.
    # This avoids a second DNS lookup and prevents DNS rebinding to private hosts.
    connection = http.client.HTTPSConnection(parsed.hostname,443,timeout=15,context=ssl.create_default_context())
    connection._create_connection = lambda destination, timeout, source_address=None: socket.create_connection((address,443),timeout,source_address)
    path = parsed.path or '/'
    if parsed.query: path += '?' + parsed.query
    try:
        connection.request('GET',path,headers={'User-Agent':'LinkedInMediaPreflight/1.0','Range':'bytes=0-1023'})
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read(1024)
    finally:
        connection.close()


def check_public_image(url):
    """Check a bounded public image response; follows only validated public HTTPS redirects."""
    current = url
    for _ in range(5):
        parsed, address = _public_target(current)
        try:
            status, headers, body = _fetch_image(parsed,address)
        except Exception:
            raise BufferError('Public image could not be fetched.') from None
        headers = {key.lower():value for key,value in headers.items()}
        if status in (301,302,303,307,308):
            location = headers.get('location')
            if not location: raise BufferError('Image redirect has no destination.')
            current = urljoin(current,location)
            continue
        mime = headers.get('content-type','').split(';')[0].strip().lower()
        if status not in (200,206) or mime not in ('image/png','image/jpeg','image/webp') or not body:
            raise BufferError('Image must return nonempty PNG, JPEG or WebP bytes.')
        return {'url':current,'mime_type':mime,'bytes_checked':len(body)}
    raise BufferError('Image exceeded the redirect limit.')
