"""One bounded cloud invocation; durable intents precede every external mutation."""
import argparse
import json
import os
import tempfile
from datetime import datetime, timezone, date
from pathlib import Path

from buffer_client import BufferClient, check_public_image
from content import load_catalog, import_daily
from core import Journal, LOCAL_TZ, body_hash
from publisher import sync
import render_daily

ROOT=Path(__file__).resolve().parent

class WorkerError(RuntimeError): pass

def write_json(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')

class DurableJournal(Journal):
    def __init__(self,path,checkpoint):
        super().__init__(path);self.checkpoint=checkpoint
    def mark(self,*args,**kwargs):
        super().mark(*args,**kwargs);self.checkpoint(self.records())
    def reconcile(self,remote):
        before=self.records();super().reconcile(remote)
        if self.records()!=before:self.checkpoint(self.records())

class CloudWorker:
    def __init__(self,root,store,buffer,preflight=check_public_image,generator=None):
        self.root=Path(root);self.store=store;self.buffer=buffer
        self.preflight=preflight;self.generator=generator

    def run(self,now,generate=False,api_key='',model='',monthly_calls=64):
        if now.tzinfo is None:raise WorkerError('Timezone required')
        if not 2<=monthly_calls<=64:raise WorkerError('Monthly call limit must be between 2 and 64')
        config=json.loads((self.root/'config.json').read_text(encoding='utf-8'))
        if config.get('enabled') is not True:raise WorkerError('Publisher disabled; no cloud mutations allowed')
        state=self.store.load()
        if state is None:
            state=json.loads((self.root/'seed.json').read_text(encoding='utf-8'))
            self.store.save(state)
        if state.get('version')!=1:raise WorkerError('Unsupported state version')
        today=now.astimezone(LOCAL_TZ).date();day=today.isoformat();month=day[:7]
        state.setdefault('generation',{});state.setdefault('calls',{})
        state.setdefault('buffer_calls',{})
        if state['buffer_calls'].get(month,0)>870:
            raise WorkerError('Buffer monthly reserve reached; preserve remaining requests for recovery')
        def reserve_buffer_request():
            if state['buffer_calls'].get(month,0)>=900:raise WorkerError('Buffer monthly request limit reached')
            state['buffer_calls'][month]=state['buffer_calls'].get(month,0)+1
            self.store.save(state)
        self.buffer.before_request=reserve_buffer_request
        for stamp,item in state['generation'].items():
            if item['status']=='reviewed' and (today-date.fromisoformat(stamp)).days>7:
                item['status']='expired';item.pop('posts',None)
                self.store.save(state)
        # Each invocation restores only confirmed durable state, never an Actions cache.
        with tempfile.TemporaryDirectory(prefix='linkedin-worker-') as tmp:
            work=Path(tmp)
            write_json(work/'config.json',config)
            write_json(work/'catalog.json',state['catalog']);write_json(work/'media.json',state['media'])
            catalog=load_catalog(work/'catalog.json');byid={p['id']:p for p in catalog}
            journal=Journal(work/'state'/'journal.sqlite')
            for row in state['journal']:
                post=byid.get(row['id'])
                if not post or body_hash(post['body'])!=row['body_hash']:raise WorkerError('Journal/catalog integrity mismatch')
                journal.mark(row['id'],row['status'],post['body'],row.get('due_at'),row.get('remote_id'),row.get('detail'))
            def checkpoint(rows):
                state['journal']=rows;state['updated_at']=now.isoformat();self.store.save(state)
            factory=lambda path:DurableJournal(path,checkpoint)
            preview=sync(work,self.buffer,now,preflight=self.preflight,journal_factory=factory)
            if preview['status']=='blocked':return preview
            created=0
            sent={r['id'] for r in state['journal'] if r['status']=='sent'}
            backlog=sum(p['id'] not in sent for p in catalog)
            reviewed=sorted(k for k,v in state['generation'].items() if v['status']=='reviewed')
            if ((generate or reviewed) and preview['generation_ready'] and backlog<6
                    and not any(p.get('generated_on')==day for p in catalog)):
                attempt_day=reviewed[0] if reviewed else day
                attempt=state['generation'].get(attempt_day)
                if attempt and attempt['status']=='started':
                    raise WorkerError('Generation already attempted today; inspect failure before a later daily run')
                if not attempt:
                    if not api_key or not model:
                        # Flush existing approved backlog even when generation credentials are missing.
                        result=sync(work,self.buffer,now,apply=True,preflight=self.preflight,journal_factory=factory)
                        result.update(generation_status='blocked_missing_configuration')
                        return result
                    state['generation'][day]={'status':'started','stages':[]}
                    self.store.save(state)
                    def before_request(stage):
                        item=state['generation'][day]
                        if stage in item['stages'] or len(item['stages'])>=2:raise WorkerError('Daily request limit reached')
                        if state['calls'].get(month,0)>=monthly_calls:raise WorkerError('Monthly request limit reached')
                        item['stages'].append(stage);state['calls'][month]=state['calls'].get(month,0)+1
                        self.store.save(state)
                    if self.generator is None:
                        from generator import generate_daily
                        generator=generate_daily
                    else:generator=self.generator
                    posts,audit=generator(catalog,today,api_key,model,before_request,metrics=self.metrics())
                    state['generation'][day].update(status='reviewed',posts=posts,audit=audit)
                    self.store.save(state)
                posts=state['generation'][attempt_day]['posts']
                for post in posts:
                    render_daily.render(post,root=work)
                    url=self.store.publish_image(work/post['image'])
                    self.preflight(url)
                    state['media'][post['id']]=url
                # Import validates the entire batch atomically; no catalog change on bad content.
                created=import_daily(work/'catalog.json',posts,state['journal'],today)
                state['catalog']=load_catalog(work/'catalog.json')
                state['generation'][attempt_day]['status']='imported'
                state['generation'][attempt_day].pop('posts',None)
                write_json(work/'media.json',state['media'])
                self.store.save(state)
            result=sync(work,self.buffer,now,apply=True,preflight=self.preflight,journal_factory=factory)
            result.update(generated=created,calls_this_month=state['calls'].get(month,0))
            if not generate:result['generation_status']='disabled_zero_cost'
            result['buffer_calls_this_month']=state['buffer_calls'].get(month,0)
            self.compact(state)
            state['last_result']=result
            self.store.save(state)
            return result

    def metrics(self):
        path=self.root/'metrics.csv'
        if not path.exists():return None
        from engagement import summarize_metrics
        return summarize_metrics(path)

    @staticmethod
    def compact(state):
        sent={r['id'] for r in state['journal'] if r['status']=='sent'}
        daily=[p for p in state['catalog'] if p.get('batch')=='daily' and p['id'] in sent]
        remove={p['id'] for p in daily[:-180]}
        state['catalog']=[p for p in state['catalog'] if p['id'] not in remove]
        state['journal']=[r for r in state['journal'] if r['id'] not in remove]
        state['media']={k:v for k,v in state['media'].items() if k not in remove}
        state['generation']={k:state['generation'][k] for k in sorted(state['generation'])[-14:]}
        state['calls']={k:state['calls'][k] for k in sorted(state['calls'])[-3:]}
        state['buffer_calls']={k:state['buffer_calls'][k] for k in sorted(state.get('buffer_calls',{}))[-3:]}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    if not args.apply:raise WorkerError('Cloud worker requires --apply; local offline tests never publish')
    for name in ('GITHUB_TOKEN','GITHUB_REPOSITORY','BUFFER_API_KEY'):
        if not os.getenv(name):raise WorkerError('Missing required secret/configuration: '+name)
    from github_store import GitHubStore
    store=GitHubStore(os.environ['GITHUB_REPOSITORY'],os.environ['GITHUB_TOKEN'])
    worker=CloudWorker(ROOT,store,BufferClient(os.environ['BUFFER_API_KEY'],recent_history=os.getenv('BUFFER_FULL_HISTORY')!='true'))
    # Production is a zero-cost publisher. Do not read or pass paid AI credentials.
    result=worker.run(datetime.now(timezone.utc),generate=False,api_key='',model='')
    print(json.dumps(result,ensure_ascii=False))
    summary=os.getenv('GITHUB_STEP_SUMMARY')
    if summary:
        with open(summary,'a',encoding='utf-8') as f:
            f.write('## LinkedIn worker\n\n```json\n'+json.dumps(result,ensure_ascii=False,indent=2)+'\n```\n')
    return 2 if result.get('status')=='blocked' or result.get('generation_status','').startswith('blocked') else 0

if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:
        # Never echo transport payloads, env values or secrets in Actions logs.
        print(json.dumps({'status':'blocked','error_type':type(exc).__name__,'reason':'Worker stopped. Check durable state and configuration; no automatic retry.'}))
        raise SystemExit(2)
