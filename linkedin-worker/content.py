"""Editorial catalog rules. These validate structure, not the truth of a source."""
import hashlib
import json
import re
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

SLOTS = ('08:30', '12:30', '18:00')

def load_catalog(path):
    data=json.loads(Path(path).read_text(encoding='utf-8-sig'))
    if not isinstance(data,list): raise ValueError('Catálogo deve ser uma lista.')
    ids=set(); bodies=set()
    for p in data:
        validate_post(p)
        digest=hashlib.sha256(p['body'].encode()).hexdigest()
        if p['id'] in ids or digest in bodies: raise ValueError('ID ou texto duplicado no catálogo.')
        ids.add(p['id']);bodies.add(digest)
    return data

def validate_post(post, new=False, today=None):
    for key in ('id','title','body','image','slot'):
        if not isinstance(post.get(key),str) or not post[key].strip():raise ValueError(f'Campo obrigatório: {key}')
    if post['slot'] not in SLOTS:raise ValueError('Horário fora da grade aprovada.')
    if not 200<=len(post['body'])<=3000:raise ValueError('Texto deve ter entre 200 e 3000 caracteres.')
    if re.search('[\U0001F000-\U0001FAFF\u2600-\u27BF]',post['body']):raise ValueError('Emojis não são permitidos.')
    for phrase in ('em busca de oportunidades','buscando emprego','open to work','buscando uma vaga','disponível para vagas'):
        if phrase in post['body'].casefold():raise ValueError('Indicação de busca de emprego não autorizada no conteúdo público.')
    sources=post.get('sources')
    if not isinstance(sources,list) or not sources:raise ValueError('Cada post exige fontes.')
    for source in sources:
        parsed=urlparse(source)
        if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password:raise ValueError('Fonte precisa de URL HTTPS sem credenciais.')
        if source not in post['body']:raise ValueError('Inclua o link da fonte no texto.')
    if new:
        today=today or date.today()
        if post.get('reviewed') is not True:raise ValueError('Revisão editorial do Codex pendente.')
        checks={c.get('url'):c for c in post.get('source_checks',[]) if isinstance(c,dict)}
        for source in sources:
            check=checks.get(source,{})
            try:checked=date.fromisoformat(check.get('checked_at','')[:10])
            except (ValueError,TypeError):raise ValueError('Data de verificação da fonte ausente.')
            if not 0<=(today-checked).days<=7 or not check.get('supports','').strip():raise ValueError('Fonte sem verificação recente e evidência descrita.')
        if not post.get('visual_title') or len(post.get('visual_lines',[]))!=3:raise ValueError('Imagem precisa de título e três pontos.')

def generation_ready(catalog,records):
    sent={r['id'] for r in records if r['status']=='sent'}
    return all(p['id'] in sent for p in catalog if p.get('batch')=='initial')

def import_daily(path,posts,records,today):
    path=Path(path)
    current=json.loads(path.read_text(encoding='utf-8-sig'))
    if not generation_ready(current,records):raise ValueError('O lote inicial ainda não terminou de publicar.')
    if len(posts)!=3 or {p.get('slot') for p in posts}!=set(SLOTS):raise ValueError('Importe exatamente três posts, um por horário.')
    if any(p.get('generated_on')==today.isoformat() for p in current):raise ValueError('O lote diário já existe.')
    ids={p['id'] for p in current}; texts={p.get('body') for p in current};titles={p.get('title','').casefold() for p in current}
    additions=[]
    for p in posts:
        validate_post(p,new=True,today=today)
        if p['id'] in ids or p['body'] in texts or p['title'].casefold() in titles:raise ValueError('Conteúdo diário duplicado.')
        img=(path.parent/p['image']).resolve()
        if not img.is_relative_to(path.parent.resolve()) or not img.is_file():raise ValueError('Imagem diária ausente ou fora da pasta do projeto.')
        ids.add(p['id']);texts.add(p['body']);titles.add(p['title'].casefold())
        additions.append(dict(p,batch='daily',order=len(current)+len(additions),generated_on=today.isoformat()))
    temp=path.with_suffix('.tmp')
    temp.write_text(json.dumps(current+additions,ensure_ascii=False,indent=2),encoding='utf-8')
    temp.replace(path)
    return len(additions)
