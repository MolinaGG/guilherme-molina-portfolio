import json
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timezone
from publisher import sync
from buffer_client import AmbiguousWrite, BufferError
from core import Journal

class FakeBuffer:
    def __init__(self,fail=False):self.remote=[];self.created=[];self.fail=fail
    def channels(self,org):return [{'id':'channel','service':'linkedin','name':'Guilherme Molina Solano'}]
    def list_posts(self,org,channel):return list(self.remote)
    def create_post(self,channel,text,due,image):
        self.created.append(text)
        if self.fail:raise AmbiguousWrite('Resposta perdida')
        p={'id':str(len(self.created)),'text':text,'dueAt':due,'status':'scheduled','channelId':'channel'}
        self.remote.append(p);return p

class PublisherTests(unittest.TestCase):
    def setup_root(self,root):
        (root/'config.json').write_text(json.dumps({'enabled':True,'organization_id':'org','channel_id':'channel','channel_name':'Guilherme Molina Solano'}))
        posts=[]
        for n,slot in enumerate(['08:30','12:30','18:00']):
            posts.append({'id':f'initial-{n}','title':str(n),'body':str(n)+' Exemplo didático de análise. '*20+' https://example.org/source','sources':['https://example.org/source'],'image':'image.png','slot':slot,'batch':'initial','order':n})
        (root/'catalog.json').write_text(json.dumps(posts))
        (root/'media.json').write_text(json.dumps({p['id']:'https://example.org/image.png' for p in posts}))
        (root/'image.png').write_bytes(b'png')
    def test_repeated_apply_does_not_duplicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.setup_root(root);client=FakeBuffer();now=datetime(2026,11,21,8,tzinfo=timezone.utc)
            one=sync(root,client,now,apply=True,preflight=lambda url:None)
            two=sync(root,client,now,apply=True,preflight=lambda url:None)
            self.assertEqual(len(client.created),3);self.assertEqual(one['scheduled'],3);self.assertEqual(two['scheduled'],0)
    def test_dry_run_never_calls_create(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.setup_root(root);client=FakeBuffer()
            sync(root,client,datetime(2026,11,21,8,tzinfo=timezone.utc),preflight=lambda url:None)
            self.assertEqual(client.created,[])
    def test_ambiguous_write_blocks_next_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.setup_root(root);client=FakeBuffer(True);now=datetime(2026,11,21,8,tzinfo=timezone.utc)
            one=sync(root,client,now,apply=True,preflight=lambda url:None)
            two=sync(root,client,now,apply=True,preflight=lambda url:None)
            self.assertEqual(len(client.created),1);self.assertEqual(one['status'],'blocked');self.assertEqual(two['status'],'blocked')
    def test_partial_failure_does_not_count_unconfirmed_creations(self):
        for error in (BufferError, AmbiguousWrite):
            with self.subTest(error=error), tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);self.setup_root(root);client=FakeBuffer()
                create=client.create_post
                def fail_second(*args):
                    if client.created:raise error('Second mutation failed')
                    return create(*args)
                client.create_post=fail_second
                result=sync(root,client,datetime(2026,11,21,8,tzinfo=timezone.utc),apply=True,preflight=lambda url:None)
                self.assertEqual(result['status'],'blocked')
                self.assertEqual(result['scheduled'],0)
                self.assertEqual(result['created_ids'],['initial-0'])
                self.assertTrue(result['created_ids_unconfirmed'])

    def test_missing_image_prevents_any_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.setup_root(root);client=FakeBuffer();(root/'media.json').write_text('{}')
            result=sync(root,client,datetime(2026,11,21,8,tzinfo=timezone.utc),apply=True,preflight=lambda url:None)
            self.assertEqual(result['status'],'blocked');self.assertEqual(client.created,[])

    def test_crash_before_readback_retains_uncertainty_and_checks_body(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.setup_root(root);client=FakeBuffer()
            now=datetime(2026,11,21,8,tzinfo=timezone.utc)
            original_list=client.list_posts
            def fail_readback(*args):
                if client.created:
                    raise OSError('Connection lost before readback')
                return original_list(*args)
            client.list_posts=fail_readback
            with self.assertRaises(OSError):
                sync(root,client,now,apply=True,preflight=lambda url:None)
            self.assertTrue(all(row['status']=='uncertain' for row in Journal(root/'state'/'journal.sqlite').records()))
            client.list_posts=original_list
            client.remote[0]['text']='Wrong remote text'
            result=sync(root,client,now,apply=True,preflight=lambda url:None)
            self.assertEqual(result['status'],'blocked')
            self.assertEqual(len(client.created),3)

if __name__=='__main__':unittest.main()
