"""Optional aggregate feedback from real exported metrics, never fabricated analytics."""
import csv
from collections import defaultdict

def summarize_metrics(path):
    groups=defaultdict(lambda:dict(posts=0,impressions=0,comments=0,shares=0))
    seen=set()
    with open(path,encoding='utf-8-sig',newline='') as f:
        for row in csv.DictReader(f):
            ident=row['post_id'].strip();topic=row['topic'].strip()
            if not ident or ident in seen or not topic or len(topic)>100:raise ValueError('Invalid or duplicate metric row')
            seen.add(ident);values={k:int(row[k]) for k in ('impressions','comments','shares')}
            if min(values.values())<0:raise ValueError('Metrics cannot be negative')
            data=groups[topic];data['posts']+=1
            for k,v in values.items():data[k]+=v
    result=[]
    for topic,data in groups.items():
        rate=(data['comments']+data['shares'])/data['impressions'] if data['impressions'] else None
        result.append(dict(topic=topic,**data,interaction_rate=rate))
    result.sort(key=lambda r:r['interaction_rate'] or 0,reverse=True)
    return {'source':'user-supplied metrics.csv','topics':result[:20],
            'limitation':'Comentários+compartilhamentos/impressões; amostras pequenas não provam causalidade. Não são analytics automáticos do LinkedIn.'}
