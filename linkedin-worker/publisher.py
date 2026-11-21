"""Official Buffer API publishing; dry-run by default, never drives a browser."""
import argparse
import getpass
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from buffer_client import BufferClient, BufferError, AmbiguousWrite, check_public_image
from content import load_catalog, import_daily, generation_ready
from core import Journal, run_lock, plan_posts, body_hash, LOCAL_TZ

ROOT=Path(__file__).resolve().parent

def read_json(path,default=None):
    return json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else default

def token_for(root):
    token=os.getenv('BUFFER_API_KEY','').strip()
    keyfile=root/'.buffer-key'
    if not token and keyfile.exists():token=keyfile.read_text(encoding='utf-8').strip()
    if not token:raise BufferError('Chave Buffer não configurada. Execute configure no seu terminal; não envie a chave no chat.')
    return token

def settings(root):
    cfg=read_json(root/'config.json',{})
    if not cfg.get('organization_id') or not cfg.get('channel_id') or not cfg.get('channel_name'):
        raise BufferError('Conta/canal Buffer não configurados. Execute configure.')
    return cfg

def sync(root,client,now,apply=False,preflight=check_public_image,journal_factory=Journal):
    root=Path(root);cfg=settings(root);catalog=load_catalog(root/'catalog.json')
    media=read_json(root/'media.json',{})
    if apply and cfg.get('enabled') is not True:raise BufferError('Publicador desativado na configuração.')
    with run_lock(root/'state'/'run.lock'):
        journal=journal_factory(root/'state'/'journal.sqlite')
        channels=client.channels(cfg['organization_id'])
        selected=[c for c in channels if c['id']==cfg['channel_id'] and c['service']=='linkedin' and c['name']==cfg['channel_name']]
        if len(selected)!=1:raise BufferError('Canal LinkedIn não confere com a conexão escolhida. Reconfigure antes de publicar.')
        remote=client.list_posts(cfg['organization_id'],cfg['channel_id'])
        if any(p.get('channelId')!=cfg['channel_id'] for p in remote):raise BufferError('Resposta contém outro canal; nenhuma publicação enviada.')
        journal.reconcile(remote)
        known={r['id'] for r in journal.records()}
        for p in catalog:
            if p['id'] in known:continue
            matches=[r for r in remote if body_hash(r.get('text',''))==body_hash(p['body'])]
            if len(matches)>1:journal.mark(p['id'],'conflict',p['body'],detail='Texto encontrado mais de uma vez no Buffer.')
            elif matches:
                r=matches[0];journal.mark(p['id'],r['status'],p['body'],r.get('dueAt'),r['id'],'Conteúdo existente reconhecido.')
        records=journal.records();remote_ids={p['id'] for p in remote}
        blockers=[r['id'] for r in records if r['status'] in ('pending','inflight','uncertain','conflict','error') or (r['status']=='scheduled' and r.get('remote_id') not in remote_ids)]
        base={'scheduled':0,'generation_ready':generation_ready(catalog,records),'remote_queue':sum(p['status']=='scheduled' for p in remote)}
        if blockers:return dict(base,status='blocked',reason='Reconciliar falhas/incertezas antes de enviar novos posts.',items=blockers)
        planned=plan_posts(catalog,remote,records,now)
        summary=[{'id':p['id'],'title':p['title'],'due_at':p['due_at'],'image_url':media.get(p['id'])} for p in planned]
        if not apply:return dict(base,status='dry_run',planned=summary)
        # Preflight the whole batch before starting mutations, so missing media cannot yield a half-filled batch.
        for p in planned:
            if not media.get(p['id']):return dict(base,status='blocked',reason='Imagem pública não configurada.',items=[p['id']])
            try:preflight(media[p['id']])
            except BufferError as exc:return dict(base,status='blocked',reason=str(exc),items=[p['id']])
        created=[]
        for p in planned:
            journal.mark(p['id'],'inflight',p['body'],p['due_at'],detail='Intent persisted before Buffer mutation.')
            try:
                result=client.create_post(cfg['channel_id'],p['body'],p['due_at'],media[p['id']])
            except AmbiguousWrite:
                journal.mark(p['id'],'uncertain',p['body'],p['due_at'],detail='Resposta incerta; não reenviar automaticamente.')
                return dict(base,status='blocked',scheduled=0,created_ids=created,created_ids_unconfirmed=True,reason='Resposta incerta. Próxima execução reconciliará antes de qualquer envio.',items=[p['id']])
            except BufferError as exc:
                journal.mark(p['id'],'error',p['body'],p['due_at'],detail=str(exc))
                return dict(base,status='blocked',scheduled=0,created_ids=created,created_ids_unconfirmed=True,reason=str(exc),items=[p['id']])
            journal.mark(p['id'],'uncertain',p['body'],p['due_at'],result['id'],'Create mutation returned success; readback pending.')
            created.append(p['id'])
        if created:
            confirmed=client.list_posts(cfg['organization_id'],cfg['channel_id'])
            journal.reconcile(confirmed)
            byid={r['id']:r for r in journal.records()}
            for p in planned:
                r=byid[p['id']]
                matches=[x for x in confirmed if x['id']==r['remote_id'] and x['status']=='scheduled' and x['text']==p['body'] and datetime.fromisoformat(x['dueAt'].replace('Z','+00:00'))==datetime.fromisoformat(p['due_at'].replace('Z','+00:00'))]
                if len(matches)!=1:
                    journal.mark(p['id'],'uncertain',p['body'],p['due_at'],r['remote_id'],'Readback did not confirm text/time/status.')
                    return dict(base,status='blocked',scheduled=0,created_ids=created,reason='Agendamento retornou sucesso, mas releitura não confirmou o lote. Não reenviar.')
        return dict(base,status='ok',scheduled=len(created),items=created)

def configure(root):
    key=os.getenv('BUFFER_API_KEY') or getpass.getpass('Chave API do Buffer (entrada oculta): ')
    client=BufferClient(key.strip())
    choices=[]
    for org in client.organizations():
        for channel in client.channels(org['id']):
            if channel['service']=='linkedin':choices.append((org,channel))
    if not choices:raise BufferError('Nenhum LinkedIn conectado. Conecte seu perfil no Buffer primeiro.')
    for n,(org,c) in enumerate(choices,1):print(f'{n}. {org.get("name",org["id"])} / {c["name"]}')
    chosen=int(input('Número do seu perfil Guilherme Molina Solano: '))-1
    if not 0<=chosen<len(choices):raise BufferError('Seleção inválida.')
    org,c=choices[chosen]
    cfg=read_json(root/'config.json',{})
    cfg.update(enabled=True,organization_id=org['id'],channel_id=c['id'],channel_name=c['name'],timezone='America/Sao_Paulo',queue_limit=10)
    (root/'.buffer-key').write_text(key.strip(),encoding='utf-8');os.chmod(root/'.buffer-key',0o600)
    (root/'config.json').write_text(json.dumps(cfg,ensure_ascii=False,indent=2),encoding='utf-8')
    return {'status':'configured','channel':c['name'],'posts_created':0,'note':'Credencial salva somente no arquivo local .buffer-key, excluído do pacote e do Git.'}

def status(root):
    catalog=load_catalog(root/'catalog.json');journal=Journal(root/'state'/'journal.sqlite');rows=journal.records()
    counts=Counter(r['status'] for r in rows)
    return {'catalog':len(catalog),'initial':sum(p.get('batch')=='initial' for p in catalog),'states':dict(counts),'generation_ready':generation_ready(catalog,rows),'source':'local journal; execute sync to refresh from Buffer','automation_registered':None}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['doctor','configure','discover','status','plan','sync','import-daily'])
    parser.add_argument('--apply',action='store_true');parser.add_argument('--now');parser.add_argument('--file',type=Path)
    args=parser.parse_args()
    now=datetime.fromisoformat(args.now.replace('Z','+00:00')) if args.now else datetime.now(timezone.utc)
    if now.tzinfo is None:parser.error('--now precisa incluir fuso.')
    if args.apply and (args.command!='sync' or args.now):parser.error('--apply só é permitido com sync e o relógio real.')
    if args.command=='configure':result=configure(ROOT)
    elif args.command=='status':result=status(ROOT)
    elif args.command=='plan':
        catalog=load_catalog(ROOT/'catalog.json')
        planned=plan_posts(catalog,[],[],now)
        result={'status':'offline_simulation','not_scheduled':True,'ignores_remote_queue':True,'planned':[{'id':p['id'],'title':p['title'],'due_at':p['due_at']} for p in planned]}
    elif args.command=='doctor':
        catalog=load_catalog(ROOT/'catalog.json');media=read_json(ROOT/'media.json',{});cfg=read_json(ROOT/'config.json',{})
        try:token_for(ROOT);key=True
        except BufferError:key=False
        result={'catalog_valid':True,'posts':len(catalog),'local_images':sum((ROOT/p['image']).is_file() for p in catalog),'public_image_urls':sum(bool(media.get(p['id'])) for p in catalog),'buffer_key_configured':key,'buffer_channel_configured':bool(cfg.get('channel_id')),'codex_task_registered':None,'note':'doctor é local; registro da tarefa Codex não é observável pela CLI. sync confirma conta, fila e imagens pela rede.'}
    elif args.command=='discover':
        client=BufferClient(token_for(ROOT));result=[{'organization':o,'channels':client.channels(o['id'])} for o in client.organizations()]
    elif args.command=='import-daily':
        if not args.file:parser.error('--file é obrigatório.')
        with run_lock(ROOT/'state'/'run.lock'):
            rows=Journal(ROOT/'state'/'journal.sqlite').records()
            result={'imported':import_daily(ROOT/'catalog.json',read_json(args.file),rows,now.astimezone(LOCAL_TZ).date())}
    else:result=sync(ROOT,BufferClient(token_for(ROOT)),now,apply=args.apply)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 2 if isinstance(result,dict) and result.get('status')=='blocked' else 0

if __name__=='__main__':
    try:sys.exit(main())
    except (BufferError,ValueError,FileExistsError) as exc:
        print(json.dumps({'status':'blocked','reason':str(exc)},ensure_ascii=False));sys.exit(2)
