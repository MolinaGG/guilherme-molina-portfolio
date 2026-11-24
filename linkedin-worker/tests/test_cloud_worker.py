import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import os
from datetime import datetime, timezone, timedelta
from core import Journal
from test_publisher import FakeBuffer
import test_publisher
from cloud_worker import CloudWorker, WorkerError, main

class MemoryStore:
    def __init__(self): self.value=None; self.snapshots=[]; self.fail_intent=False
    def load(self): return copy.deepcopy(self.value)
    def save(self,value):
        if self.fail_intent and any(r['status']=='inflight' for r in value['journal']):
            raise RuntimeError('Persistence unavailable')
        self.value=copy.deepcopy(value);self.snapshots.append(copy.deepcopy(value))
    def publish_image(self,path): return 'https://example.org/image.png'

class CloudWorkerTests(unittest.TestCase):
    now=datetime(2026,11,21,9,tzinfo=timezone.utc)
    def setup_root(self,root):
        test_publisher.PublisherTests().setup_root(root)
        (root/'seed.json').write_text(json.dumps({'version':1,'catalog':json.loads((root/'catalog.json').read_text()),'media':json.loads((root/'media.json').read_text()),'journal':[],'generation':{},'calls':{}}))
    def test_intent_saved_before_buffer_write_and_repeated_run_safe(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.setup_root(root);store=MemoryStore();client=FakeBuffer()
            original=client.create_post
            def create(*args):
                self.assertTrue(any(r['status']=='inflight' for r in store.value['journal']))
                return original(*args)
            client.create_post=create
            worker=CloudWorker(root,store,client,preflight=lambda u:None)
            self.assertEqual(worker.run(self.now)['scheduled'],3)
            self.assertEqual(worker.run(self.now)['scheduled'],0)
            self.assertEqual(len(client.created),3)
    def test_failed_durable_intent_prevents_publication(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.setup_root(root);store=MemoryStore();store.fail_intent=True;client=FakeBuffer()
            with self.assertRaises(RuntimeError):CloudWorker(root,store,client,preflight=lambda u:None).run(self.now)
            self.assertEqual(client.created,[])
    def test_generation_attempt_not_repeated_after_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.setup_root(root);store=MemoryStore();client=FakeBuffer()
            seed=json.loads((root/'seed.json').read_text());seed['catalog']=[];seed['media']={};(root/'seed.json').write_text(json.dumps(seed))
            calls=[]
            def fail(catalog,today,key,model,before_request,**kw):
                before_request('draft');calls.append('called');raise ValueError('Invalid draft')
            worker=CloudWorker(root,store,client,preflight=lambda u:None,generator=fail)
            with self.assertRaises(ValueError):worker.run(self.now,generate=True,api_key='test',model='test')
            with self.assertRaises(WorkerError):worker.run(self.now,generate=True,api_key='test',model='test')
            self.assertEqual(calls,['called'])
            self.assertEqual(store.value['calls']['2026-11'],1)
    def test_monthly_limit_prevents_generation_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.setup_root(root);store=MemoryStore();client=FakeBuffer()
            seed=json.loads((root/'seed.json').read_text());seed['catalog']=[];seed['calls']={'2026-11':64};(root/'seed.json').write_text(json.dumps(seed))
            calls=[]
            def generator(catalog,today,key,model,before_request,**kw):before_request('draft');calls.append(1)
            worker=CloudWorker(root,store,client,preflight=lambda u:None,generator=generator)
            with self.assertRaises(WorkerError):worker.run(self.now,generate=True,api_key='test',model='test')
            self.assertEqual(calls,[])
    def test_reviewed_batch_recovers_next_day_without_new_ai_calls(self):
        from test_generator import drafts
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.setup_root(root);store=MemoryStore();client=FakeBuffer();calls=[]
            seed=json.loads((root/'seed.json').read_text());seed['catalog']=[];seed['media']={};(root/'seed.json').write_text(json.dumps(seed))
            def generate(catalog,today,key,model,before_request,**kw):
                before_request('draft');before_request('review');calls.append(1)
                posts=drafts()
                for n,(p,slot) in enumerate(zip(posts,('08:30','12:30','18:00'))):
                    p.update(id=f'daily-{today}-{n}',slot=slot,image='media/pending.png',reviewed=True,
                             source_checks=[{'url':p['sources'][0],'checked_at':str(today),'supports':'Official technical documentation.'}])
                return posts,{'calls':2}
            original=store.publish_image
            def fail(path):raise RuntimeError('image host failed')
            store.publish_image=fail
            worker=CloudWorker(root,store,client,preflight=lambda u:None,generator=generate)
            with self.assertRaises(RuntimeError):worker.run(self.now,generate=True,api_key='test',model='test')
            store.publish_image=original
            result=worker.run(self.now+timedelta(days=1),generate=True,api_key='test',model='test')
            self.assertEqual(result['generated'],3);self.assertEqual(result['scheduled'],3)
            self.assertEqual(calls,[1]);self.assertEqual(len(client.created),3)
    def test_free_mode_still_schedules_preapproved_backlog(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.setup_root(root);store=MemoryStore();client=FakeBuffer()
            def forbidden(*args, **kwargs): self.fail('paid generator invoked in free mode')
            worker=CloudWorker(root,store,client,preflight=lambda u:None,generator=forbidden)
            result=worker.run(self.now,generate=False,api_key='unexpected-key',model='test')
            self.assertEqual(result['scheduled'],3)
            self.assertEqual(result['generation_status'],'disabled_zero_cost')
            self.assertEqual(store.value['calls'],{})

    def test_exhausted_free_catalog_ignores_prior_failed_paid_attempt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.setup_root(root);store=MemoryStore();client=FakeBuffer()
            path=root/'seed.json'
            seed=json.loads(path.read_text())
            seed.update(catalog=[],media={},generation={'2026-11-21':{'status':'started','stages':['draft']}})
            path.write_text(json.dumps(seed))
            def forbidden(*args, **kwargs): self.fail('paid generator invoked in free mode')
            worker=CloudWorker(root,store,client,preflight=lambda u:None,generator=forbidden)
            result=worker.run(self.now,api_key='unexpected-key',model='test')
            self.assertEqual(result['scheduled'],0)
            self.assertEqual(result['generation_status'],'disabled_zero_cost')
            self.assertEqual(client.created,[])
            self.assertEqual(store.value['calls'],{})
            self.assertEqual(store.value['last_result'],result)

    def test_production_entrypoint_does_not_opt_in_via_environment(self):
        env={'GITHUB_TOKEN':'test','GITHUB_REPOSITORY':'owner/repo','BUFFER_API_KEY':'test',
             'ENABLE_GENERATION':'true','OPENAI_API_KEY':'unexpected-key','OPENAI_MODEL':'test'}
        with patch.dict(os.environ,env,clear=True), patch('sys.argv',['cloud_worker.py','--apply']), \
             patch('github_store.GitHubStore'), patch('cloud_worker.CloudWorker') as worker:
            worker.return_value.run.return_value={'status':'ok','generation_status':'disabled_zero_cost'}
            self.assertEqual(main(),0)
            self.assertFalse(worker.return_value.run.call_args.kwargs['generate'])
            self.assertEqual(worker.return_value.run.call_args.kwargs['api_key'],'')

    def test_workflow_push_validates_but_cannot_publish(self):
        workflow=(Path(__file__).resolve().parents[2]/'.github/workflows/linkedin-worker.yml').read_text()
        self.assertIn('  push:',workflow.split('jobs:',1)[0])
        validate,publish=workflow.split('  validate:',1)[1].split('  publish:',1)
        self.assertNotIn('    if:',validate)
        gate=next(line.strip()[len('if: '):] for line in publish.splitlines() if line.startswith('    if: '))
        self.assertEqual(gate,"github.ref == 'refs/heads/main' && (github.event_name == 'schedule' || github.event_name == 'workflow_dispatch') && vars.LINKEDIN_WORKER_PAUSED != 'true'")

    def test_disabled_worker_makes_no_cloud_mutations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.setup_root(root);store=MemoryStore();client=FakeBuffer()
            config=json.loads((root/'config.json').read_text());config['enabled']=False;(root/'config.json').write_text(json.dumps(config))
            with self.assertRaises(WorkerError):CloudWorker(root,store,client).run(self.now)
            self.assertEqual(store.snapshots,[]);self.assertEqual(client.created,[])

if __name__=='__main__':unittest.main()
