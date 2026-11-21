import json
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from buffer_client import BufferClient, BufferError, AmbiguousWrite, check_public_image

class Fake:
    def __init__(self, *responses): self.responses=list(responses); self.requests=[]
    def __call__(self, request):
        self.requests.append(request)
        result=self.responses.pop(0)
        if isinstance(result, Exception): raise result
        return result

class ClientTests(unittest.TestCase):
    def test_recent_history_paginates_entire_unsent_queue_and_limits_sent(self):
        def page(items, more=False, cursor=None):
            return 200, {'data': {'posts': {'edges': [{'node': p} for p in items], 'pageInfo': {'hasNextPage': more, 'endCursor': cursor}}}}
        fake=Fake(page([{'id':'future','status':'scheduled'}],True,'next'),
                  page([{'id':'transition','status':'sending'}]),
                  page([{'id':'transition','status':'sent'},{'id':'recent','status':'sent'}]))
        with patch('buffer_client._utcnow',return_value=datetime(2026,11,20,9,tzinfo=timezone.utc)):
            posts=BufferClient('secret',fake,recent_history=True).list_posts('o','c')
        self.assertEqual({p['id']:p['status'] for p in posts},{'future':'scheduled','transition':'sent','recent':'sent'})
        queries=[json.loads(r.data)['query'] for r in fake.requests]
        for query in queries[:2]:
            self.assertIn('status: [draft, error, needs_approval, scheduled, sending]',query)
            self.assertNotIn('startDate',query)
        self.assertIn('after: "next"',queries[1])
        self.assertIn('status: [sent], startDate: "2026-11-13T09:00:00Z"',queries[2])

    def test_budget_callback_precedes_reads_and_writes_and_preserves_failure(self):
        fake=Fake()
        def denied():raise ValueError('Budget exhausted')
        client=BufferClient('secret',fake,before_request=denied)
        with self.assertRaisesRegex(ValueError,'Budget exhausted'):client.organizations()
        with self.assertRaisesRegex(ValueError,'Budget exhausted'):client.create_post('c','text','date','url')
        self.assertEqual(fake.requests,[])

    def test_discovery(self):
        fake=Fake((200, {'data': {'account': {'organizations': [{'id':'o','name':'Org'}]}}}), (200, {'data': {'channels': [{'id':'c','name':'Me','service':'linkedin'}]}}))
        client=BufferClient('secret',fake)
        self.assertEqual(client.organizations()[0]['id'],'o')
        self.assertEqual(client.channels('o')[0]['service'],'linkedin')
        self.assertEqual(fake.requests[0].get_header('Authorization'),'Bearer secret')
        self.assertEqual(fake.requests[0].full_url,'https://api.buffer.com')
    def test_pagination_all_statuses_and_escaping(self):
        def page(items,more,cursor): return (200,{'data':{'posts':{'edges':[{'node': x} for x in items], 'pageInfo': {'hasNextPage':more,'endCursor':cursor}}}})
        fake=Fake(page([{'id':'1','status':'sent'}],True,'next"'),page([{'id':'2','status':'scheduled'}],False,None))
        result=BufferClient('secret',fake).list_posts('o','c')
        self.assertEqual(len(result),2)
        query=json.loads(fake.requests[1].data)['query']
        self.assertIn('after: "next\\""',query)
        self.assertNotIn('status:',query)
    def test_create(self):
        post={'id':'p','dueAt':'2026-12-01T12:00:00Z','status':'scheduled','assets':[{'id':'a','mimeType':'image/png'}]}
        fake=Fake((200,{'data':{'createPost':{'__typename':'PostActionSuccess','post':post}}}))
        self.assertEqual(BufferClient('secret',fake).create_post('c','hello "world"',post['dueAt'],'https://example.org/i.png'),post)
        query=json.loads(fake.requests[0].data)['query']
        self.assertIn('mode: customScheduled',query)
        self.assertIn('hello \\"world\\"',query)
    def test_uncertain_write_is_never_retried(self):
        for result in [TimeoutError('secret'),(503,b'error'),(200,b'broken'),(200,{'data':{'createPost':None}}),(200,{'errors':[{'message':'secret'}]})]:
            fake=Fake(result)
            with self.assertRaises(AmbiguousWrite) as ctx: BufferClient('secret',fake).create_post('c','t','date','https://example.org/a.png')
            self.assertNotIn('secret',str(ctx.exception))
            self.assertEqual(len(fake.requests),1)
    def test_known_errors(self):
        for result in [(401,b'secret'),(403,b'secret'),(429,b'secret'),(200,{'data':{'createPost':{'__typename':'MutationError','message':'secret'}}})]:
            with self.assertRaises(BufferError) as ctx: BufferClient('secret',Fake(result)).create_post('c','t','date','https://example.org/a.png')
            self.assertNotIsInstance(ctx.exception,AmbiguousWrite)
            self.assertNotIn('secret',str(ctx.exception))
    def test_bad_pagination_fails_closed(self):
        fake=Fake((200,{'data':{'posts':{'edges':[],'pageInfo':{'hasNextPage':True,'endCursor':None}}}}))
        with self.assertRaises(BufferError): BufferClient('secret',fake).list_posts('o','c')
    def test_empty_token(self):
        with self.assertRaises(BufferError): BufferClient('')

class MediaTests(unittest.TestCase):
    def test_rejects_local_preview_credentials(self):
        for url in ['http://example.com/a.png','https://127.0.0.1/a','https://[::1]/a','https://localhost/a','https://user:pass@example.com/a','https://drive.google.com/file/d/id/view','https://example.com/a?token=secret']:
            with self.subTest(url=url), self.assertRaises(BufferError): check_public_image(url)
    def test_rejects_private_dns(self):
        with patch('buffer_client.socket.getaddrinfo',return_value=[(2,1,6,'',('10.0.0.2',443))]):
            with self.assertRaises(BufferError): check_public_image('https://example.com/a.png')



class MediaFetchTests(unittest.TestCase):
    def dns(self, host, *args, **kwargs):
        return [(2,1,6,'',('127.0.0.1' if host == 'private.example.com' else '93.184.216.34',443))]
    def test_public_image(self):
        with patch('buffer_client.socket.getaddrinfo', side_effect=self.dns), patch('buffer_client._fetch_image', return_value=(206,{'Content-Type':'image/png'},b'PNG')):
            result=check_public_image('https://example.com/card.png')
        self.assertEqual(result['mime_type'],'image/png')
        self.assertEqual(result['bytes_checked'],3)
    def test_redirect_to_private_is_blocked_before_fetch(self):
        with patch('buffer_client.socket.getaddrinfo', side_effect=self.dns), patch('buffer_client._fetch_image', return_value=(302,{'Location':'https://private.example.com/card.png'},b'')) as fetch:
            with self.assertRaises(BufferError): check_public_image('https://example.com/card.png')
            self.assertEqual(fetch.call_count,1)
    def test_html_empty_and_bad_status_are_rejected(self):
        for result in [(200,{'Content-Type':'text/html'},b'preview'),(200,{'Content-Type':'image/png'},b''),(403,{'Content-Type':'image/png'},b'error')]:
            with patch('buffer_client.socket.getaddrinfo', side_effect=self.dns), patch('buffer_client._fetch_image', return_value=result):
                with self.assertRaises(BufferError): check_public_image('https://example.com/card.png')
    def test_relative_public_redirect(self):
        with patch('buffer_client.socket.getaddrinfo', side_effect=self.dns), patch('buffer_client._fetch_image', side_effect=[(302,{'Location':'/real.png'},b''),(200,{'Content-Type':'image/webp'},b'abc')]):
            self.assertEqual(check_public_image('https://example.com/start')['url'],'https://example.com/real.png')

if __name__ == '__main__': unittest.main()

