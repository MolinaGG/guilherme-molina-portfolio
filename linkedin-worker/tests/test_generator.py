import json
import unittest
from datetime import date

from generator import GenerationError, generate_daily

TODAY = date(2026, 11, 20)
URLS = ['https://www.postgresql.org/docs/current/queries.html', 'https://docs.python.org/3/library/csv.html', 'https://learn.microsoft.com/en-us/power-bi/guidance/star-schema']

def drafts():
    texts = ['Consultas SQL exigem atenção à granularidade dos dados. Antes de agregar valores, defina o que representa cada linha. Em um exemplo didático, pedidos e itens têm níveis distintos. Uma junção pode multiplicar registros e alterar a interpretação do indicador.',
             'Arquivos CSV precisam de regras explícitas de leitura. Delimitadores e aspas fazem parte do formato e merecem tratamento consistente. Um exemplo didático pode comparar exportações de sistemas diferentes antes de qualquer transformação em Python.',
             'Modelagem dimensional organiza a análise em fatos e dimensões. O desenho do modelo deve acompanhar as perguntas de negócio e as relações entre entidades. No Power BI, documentar essas escolhas facilita compreender o significado dos filtros aplicados.']
    return [dict(title=f'Tema {i}', body=t+'\nFonte: '+URLS[i], sources=[URLS[i]], visual_title=f'Tema {i}', visual_lines=['Contexto', 'Exemplo', 'Decisão']) for i,t in enumerate(texts)]

def reviews():
    return [dict(id=f'daily-{TODAY.isoformat()}-{slot.replace(":", "")}', approved=True, source_checks=[dict(url=URLS[i], supports='A documentação sustenta a explicação técnica e seus limites.')]) for i,slot in enumerate(('08:30','12:30','18:00'))]

def response(value, urls=URLS):
    return {'status':'completed', 'output':[{'type':'web_search_call', 'status':'completed','action':{'sources':[{'url':u} for u in urls]}}, {'type':'message','content':[{'type':'output_text','text':json.dumps(value)}]}]}

class GeneratorTests(unittest.TestCase):
    def run_generation(self, responses=None, catalog=None, before=None):
        self.events=[]; self.requests=[]
        queue=list(responses or [response({'posts':drafts()}),response({'reviews':reviews()})])
        def transport(request):
            self.events.append('network'); self.requests.append(json.loads(request.data)); return queue.pop(0)
        return generate_daily(catalog or [],TODAY,'test-key','configured-model',before or (lambda stage:self.events.append(stage)),transport=transport)

    def test_two_calls_with_prior_durable_intent_and_review_evidence(self):
        posts,audit=self.run_generation()
        self.assertEqual(self.events,['draft','network','review','network'])
        self.assertEqual(len(posts),3)
        self.assertEqual(posts[0]['image'],'media/pending.png')
        self.assertEqual(posts[0]['source_checks'][0]['checked_at'],TODAY.isoformat())
        self.assertTrue(posts[0]['reviewed'])
        self.assertEqual(audit['calls'],2)
        for req in self.requests:
            self.assertEqual(req['max_output_tokens'],8000)
            self.assertEqual(req['include'],['web_search_call.action.sources'])
            self.assertLessEqual(req['max_tool_calls'],6)
            self.assertEqual(req['model'],'configured-model')

    def test_draft_without_real_tool_evidence_stops_before_review(self):
        with self.assertRaises(GenerationError):self.run_generation([response({'posts':drafts()},[])])
        self.assertEqual(len(self.requests),1)

    def test_review_missing_evidence_or_id_or_approval_is_rejected(self):
        for kind in ('evidence','id','approval','support'):
            rs=reviews()
            if kind=='id':rs[2]['id']=rs[0]['id']
            if kind=='approval':rs[1]['approved']=False
            if kind=='support':rs[0]['source_checks'][0]['supports']=''
            with self.subTest(kind=kind),self.assertRaises(GenerationError):
                self.run_generation([response({'posts':drafts()}),response({'reviews':rs},[] if kind=='evidence' else URLS)])

    def test_similar_content_and_unofficial_source_rejected(self):
        with self.assertRaises(GenerationError):self.run_generation(catalog=[drafts()[0]])
        bad=drafts();bad[0]['sources']=['https://github.com/other/project'];bad[0]['body']+=' https://github.com/other/project'
        with self.assertRaises(GenerationError):self.run_generation([response({'posts':bad},URLS+bad[0]['sources'])])

    def test_failed_durable_callback_prevents_network(self):
        def fail(stage):raise RuntimeError('storage unavailable')
        with self.assertRaises(RuntimeError):self.run_generation(before=fail)
        self.assertEqual(self.requests,[])

    def test_network_exception_is_redacted_and_not_retried(self):
        calls=[]
        def fail(req):calls.append(req);raise RuntimeError('test-key private response')
        with self.assertRaises(GenerationError) as err:
            generate_daily([],TODAY,'test-key','configured-model',lambda stage:None,transport=fail)
        self.assertNotIn('test-key',str(err.exception));self.assertEqual(len(calls),1)

    def test_missing_configuration_does_not_consume_quota(self):
        events=[]
        with self.assertRaises(GenerationError):generate_daily([],TODAY,'key','',events.append)
        self.assertEqual(events,[])

    def test_incomplete_output_and_unsafe_editorial_content_stop_early(self):
        incomplete=response({'posts':drafts()});incomplete['status']='incomplete'
        with self.assertRaises(GenerationError):self.run_generation([incomplete])
        for suffix in (' 🚀',' Eu implementei este processo.', ' Em busca de oportunidades.'):
            rows=drafts();rows[0]['body']+=suffix
            with self.subTest(suffix=suffix),self.assertRaises(GenerationError):
                self.run_generation([response({'posts':rows})])
            self.assertEqual(len(self.requests),1)

    def test_failed_review_reservation_never_makes_second_request(self):
        def before(stage):
            if stage=='review':raise RuntimeError('reservation failure')
        with self.assertRaises(RuntimeError):self.run_generation(before=before)
        self.assertEqual(len(self.requests),1)

if __name__=='__main__':unittest.main()
