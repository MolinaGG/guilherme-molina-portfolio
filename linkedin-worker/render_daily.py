"""Render original text cards for a daily JSON batch. Does not publish or import."""
import hashlib
import json
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parent

def font(size,bold=False):
    paths=[Path('C:/Windows/Fonts')/('arialbd.ttf' if bold else 'arial.ttf'),Path('/usr/share/fonts/truetype/dejavu')/('DejaVuSans-Bold.ttf' if bold else 'DejaVuSans.ttf')]
    for p in paths:
        if p.exists():return ImageFont.truetype(str(p),size)
    raise RuntimeError('Instale Arial ou DejaVu Sans para gerar as imagens.')

def wrap(draw,text,face,width):
    lines=[];current=''
    for word in text.split():
        trial=(current+' '+word).strip()
        if draw.textlength(trial,font=face)>width and current:lines.append(current);current=word
        else:current=trial
    if current:lines.append(current)
    return lines

def render(post,root=None):
    palette={'08:30':('#78d6c0','DADOS NA PRÁTICA'),'12:30':('#8ebfff','PROJETOS E MÉTODO'),'18:00':('#efc580','BI E DECISÃO')}
    accent,label=palette[post['slot']]
    im=Image.new('RGB',(1200,1200),'#101c2c');draw=ImageDraw.Draw(im)
    draw.rectangle((0,0,18,1200),fill=accent);draw.text((70,65),label,font=font(25,True),fill=accent)
    title=post['visual_title'];size=64
    while size>38 and len(wrap(draw,title,font(size,True),1040))>3:size-=2
    lines=wrap(draw,title,font(size,True),1040)
    if len(lines)>3:raise ValueError('Encurte o título visual.')
    y=145
    for line in lines:draw.text((70,y),line,font=font(size,True),fill='white');y+=size+12
    y=max(420,y+40)
    if len(post['visual_lines'])!=3:raise ValueError('A imagem precisa de três pontos.')
    for n,line in enumerate(post['visual_lines'],1):
        lines=wrap(draw,line,font(33),930)
        if len(lines)>3:raise ValueError('Encurte um dos pontos visuais.')
        draw.rounded_rectangle((70,y,1130,y+145),radius=15,fill='#1a2b41')
        draw.text((92,y+28),str(n).zfill(2),font=font(29,True),fill=accent)
        for j,part in enumerate(lines):draw.text((160,y+25+j*40),part,font=font(33),fill='#e7edf5')
        y+=170
    draw.line((70,1035,1130,1035),fill='#3a4a60',width=2)
    draw.text((70,1060),'GUILHERME MOLINA SOLANO',font=font(25,True),fill='white')
    draw.text((70,1105),'Dados & Business Intelligence | Fontes na publicação',font=font(24),fill='#b0bed0')
    name=hashlib.sha256(post['body'].encode()).hexdigest()[:24]+'.png'
    folder=Path(root or ROOT)/'media';folder.mkdir(exist_ok=True)
    im.save(folder/name)
    post['image']='media/'+name
    return post

if __name__=='__main__':
    path=Path(sys.argv[1]);posts=json.loads(path.read_text(encoding='utf-8-sig'))
    for p in posts:render(p)
    path.write_text(json.dumps(posts,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'rendered':len(posts),'not_published':True}))
