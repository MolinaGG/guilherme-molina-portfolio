import json
import tempfile
import unittest
from pathlib import Path
from datetime import date

from content import validate_post, import_daily, generation_ready

class ContentTests(unittest.TestCase):
    def post(self, n=0):
        return {'id':f'daily-2026-12-21-{n}', 'title':f'Métrica {n}',
            'body':f'Métrica {n}\n\n'+'Um exemplo hipotético para explicar uma decisão de negócio. '*8+'\nFonte: https://example.org/source',
            'sources':['https://example.org/source'], 'slot':['08:30','12:30','18:00'][n],
            'image':f'media/{n}.png', 'visual_title':f'Métrica {n}', 'visual_lines':['Defina','Confira','Explique'],
            'reviewed':True, 'source_checks':[{'url':'https://example.org/source','checked_at':'2026-12-21','supports':'Definição técnica usada no exemplo.'}]}
    def test_missing_source_or_image_is_rejected(self):
        p=self.post(); p['sources']=[]
        with self.assertRaises(ValueError): validate_post(p)
        p=self.post(); p['image']=''
        with self.assertRaises(ValueError): validate_post(p)
    def test_emoji_and_job_search_are_rejected(self):
        for text in [' Olá 😀', ' Estou em busca de oportunidades.']:
            p=self.post();p['body']+=text
            with self.assertRaises(ValueError):validate_post(p)
    def test_generation_waits_for_every_initial_post_sent(self):
        c=[{'id':'initial-001','batch':'initial'},{'id':'initial-002','batch':'initial'}]
        self.assertFalse(generation_ready(c,[{'id':'initial-001','status':'sent'}]))
        self.assertTrue(generation_ready(c,[{'id':x['id'],'status':'sent'} for x in c]))
    def test_daily_import_is_atomic_and_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path=root/'catalog.json';path.write_text('[]')
            (root/'media').mkdir()
            for n in range(3):(root/'media'/f'{n}.png').write_bytes(b'png')
            posts=[self.post(n) for n in range(3)]
            import_daily(path,posts,[],date(2026,12,21))
            self.assertEqual(len(json.loads(path.read_text())),3)
            with self.assertRaises(ValueError):import_daily(path,posts,[],date(2026,12,21))
            self.assertEqual(len(json.loads(path.read_text())),3)
    def test_stale_source_check_is_rejected(self):
        p=self.post();p['source_checks'][0]['checked_at']='2026-01-01'
        with self.assertRaises(ValueError):validate_post(p,new=True,today=date(2026,12,21))
    def test_initial_gate_and_wrong_slots_do_not_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'catalog.json';path.write_text('[{"id":"initial-001","batch":"initial"}]')
            with self.assertRaises(ValueError):import_daily(path,[self.post(n) for n in range(3)],[],date(2026,12,21))
            self.assertEqual(len(json.loads(path.read_text())),1)

if __name__=='__main__':unittest.main()
