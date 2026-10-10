import json
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from game import Game
from llm import choose_llm

class DecisionsTests(unittest.TestCase):
    def test_valid_and_invalid(self):
        g=Game(5);criteria=g.payload()['questions']['move']['criteria']
        answer={'type':'choice','name':'move','choice':'A5','confidence':1.,'probabilities':[{'value':k,'probability':float(k=='A5')} for k in criteria]}
        config={'base_url':'https://example.com/v1/decisions','model':'test','api_key':'private-key'}
        def response(a):return SimpleNamespace(returncode=0,stdout=json.dumps({'answers':[a]})+'\n200')
        with patch('decisions.subprocess.run',return_value=response(answer)) as run:
            move,d,req,raw=choose_llm(g,config)
            self.assertEqual(move,0)
            self.assertEqual(req['questions'][0]['choices'],[{'value':k,'description':v} for k,v in criteria.items()])
            self.assertNotIn('private-key',json.dumps([d,req,raw,run.call_args.args]))
        for bad in [dict(answer,choice='Z99'),dict(answer,probabilities=[]),dict(answer,confidence=float('nan'))]:
            with patch('decisions.subprocess.run',return_value=response(bad)):
                with self.assertRaises(RuntimeError):choose_llm(g,config)
        self.assertEqual(g.moves,[])

class ForcedCandidateTests(unittest.TestCase):
    def test_singleton_pass_never_calls_aep(self):
        g=Game(5)
        source=g.payload();source['questions']['move']['criteria']={'PASS':'Pass'}
        with patch.object(g,'payload',return_value=source), patch('decisions.subprocess.run') as call:
            move,d,_,_=choose_llm(g,{'base_url':'https://example.com/v1/decisions','model':'test'})
        self.assertIsNone(move);self.assertTrue(d['forced']);self.assertEqual(d['provider'],'rules');call.assert_not_called()
    def test_singleton_pass_never_calls_jev(self):
        from server import choose_jev
        g=Game(5);source=g.payload();source['questions']['move']['criteria']={'PASS':'Pass'}
        with patch.dict('os.environ',{'TYPESAFE_API_KEY':'test'}), patch.object(g,'payload',return_value=source),patch('server.urlopen') as call:
            move,d,_,_=choose_jev(g)
        self.assertIsNone(move);self.assertTrue(d['forced']);call.assert_not_called()

class OfficialDecisionsTests(unittest.TestCase):
    def response(self,answer=None):
        if answer is None:
            criteria=Game(5).payload()['questions']['move']['criteria']
            answer={'name':'move','type':'choice','choice':'A5','confidence':1.,'probabilities':[{'value':k,'probability':float(k=='A5')} for k in criteria], 'private_metadata':'do-not-export'}
        return SimpleNamespace(returncode=0,stdout=json.dumps({'answers':[answer],'usage':{'input_tokens':50,'output_tokens':0,'total_tokens':50}})+'\n200')
    def config(self,**extra):
        return dict({'base_url':'https://api.openai.com/v1/decisions','model':'gpt-6-luna','api_key':'test-openai-key'},**extra)
    def test_official_bearer_and_no_private_export(self):
        with patch('decisions.subprocess.run',return_value=self.response()) as run:
            move,d,req,raw=choose_llm(Game(5),self.config())
        self.assertEqual(move,0)
        self.assertIn('Authorization: Bearer test-openai-key',run.call_args.kwargs['input'])
        self.assertNotIn('X-AEP',run.call_args.kwargs['input'])
        self.assertNotIn('test-openai-key',json.dumps([d,req,raw,run.call_args.args]))
        self.assertNotIn('private_metadata',json.dumps(raw))
        self.assertEqual(run.call_args.args[0][-1],'https://api.openai.com/v1/decisions')
        self.assertEqual(req['model'],'gpt-6-luna')
    def test_base_url_with_explicit_protocol(self):
        with patch('decisions.subprocess.run',return_value=self.response()) as run:
            choose_llm(Game(5),self.config(base_url='https://api.openai.com/v1',protocol='decisions'))
        self.assertEqual(run.call_args.args[0][-1],'https://api.openai.com/v1/decisions')
    def test_aep_is_explicit_opt_in(self):
        with patch('decisions.subprocess.run',return_value=self.response()) as run:
            choose_llm(Game(5),self.config(base_url='https://example.com/v1/decisions',auth_type='aep'))
        self.assertIn('X-AEP-CONSUMER-SECRET:',run.call_args.kwargs['input'])
        self.assertNotIn('Authorization:',run.call_args.kwargs['input'])
    def test_official_rejects_aep_and_missing_key_before_network(self):
        for config in (self.config(auth_type='aep'),self.config(api_key=''),self.config(auth_type='unknown')):
            with patch('decisions.subprocess.run') as run:
                with self.assertRaises(ValueError):choose_llm(Game(5),config)
                run.assert_not_called()
    def test_refusal_does_not_move(self):
        g=Game(5)
        with patch('decisions.subprocess.run',return_value=self.response({'name':'move','type':'refusal'})):
            with self.assertRaisesRegex(RuntimeError,'拒绝'):choose_llm(g,self.config())
        self.assertEqual(g.moves,[])
    def test_http_error_does_not_expose_upstream_body(self):
        with patch('decisions.subprocess.run',return_value=SimpleNamespace(returncode=0,stdout='secret provider diagnostic\n401')):
            with self.assertRaisesRegex(RuntimeError,'认证失败') as cm:choose_llm(Game(5),self.config())
        self.assertNotIn('secret provider',str(cm.exception))
    def test_duplicate_probability_rejected(self):
        r=self.response();data=json.loads(r.stdout.rsplit('\n',1)[0]);data['answers'][0]['probabilities'].append(data['answers'][0]['probabilities'][0])
        with patch('decisions.subprocess.run',return_value=SimpleNamespace(returncode=0,stdout=json.dumps(data)+'\n200')):
            with self.assertRaises(RuntimeError):choose_llm(Game(5),self.config())
