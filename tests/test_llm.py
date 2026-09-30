import json
import unittest
from io import BytesIO
from unittest.mock import patch,MagicMock
from llm import choose_llm,endpoint
from game import replay

class LLMTests(unittest.TestCase):
    def test_endpoint(self):
        self.assertEqual(endpoint('https://example.com/v1/'),'https://example.com/v1/chat/completions')
        self.assertEqual(endpoint('http://127.0.0.1:9999/v1/chat/completions'),'http://127.0.0.1:9999/v1/chat/completions')
        for u in ('file:///etc/passwd','https://a:b@example.com/v1','https://example.com/v1?key=secret','http://169.254.169.254/v1'):
            with self.assertRaises(ValueError):endpoint(u)
    def result(self,content):
        return BytesIO(json.dumps({'choices':[{'message':{'content':content}}],'usage':{'total_tokens':20},'private_metadata':'do not export'}).encode())
    def test_valid_response_and_no_credentials_in_record(self):
        g=replay(9,[0],kind='gomoku')
        opener=MagicMock();opener.open.return_value=self.result('```json\n{"choice":"B9"}\n```')
        with patch('llm.build_opener',return_value=opener):
            move,d,payload,response=choose_llm(g,{'base_url':'https://example.com/v1','model':'test-model','api_key':'test-secret'})
        self.assertEqual(move,1);self.assertEqual(d['provider'],'llm');self.assertIsNone(d['confidence'])
        export=json.dumps([d,payload,response]);self.assertNotIn('test-secret',export);self.assertNotIn('private_metadata',export)
        self.assertEqual(opener.open.call_args.args[0].get_header('Authorization'),'Bearer test-secret')
    def test_illegal_or_missing_choice_is_not_applied(self):
        for content in ('{"choice":"A9"}','{"choice":"PASS"}','{"choice":"Z99"}','{}','not json'):
            g=replay(9,[0],kind='gomoku');opener=MagicMock();opener.open.return_value=self.result(content)
            with patch('llm.build_opener',return_value=opener):
                with self.assertRaises(RuntimeError):choose_llm(g,{'base_url':'https://example.com/v1','model':'test','api_key':''})
            self.assertEqual(g.moves,[0])
    def test_identical_candidate_information(self):
        g=replay(9,[0,9,1,11,2,13,3],kind='gomoku');opener=MagicMock();opener.open.return_value=self.result('{"choice":"E9"}')
        with patch('llm.build_opener',return_value=opener):
            _,_,p,_=choose_llm(g,{'base_url':'https://example.com/v1','model':'test'})
        offered=json.loads(p['messages'][1]['content'])
        self.assertEqual(offered['criteria'],g.payload()['questions']['move']['criteria'])

    def test_deepseek_json_non_thinking_defaults(self):
        opener=MagicMock();opener.open.return_value=self.result('{"choice":"B9"}')
        with patch('llm.build_opener',return_value=opener):
            _,_,payload,_=choose_llm(replay(9,[0],kind='gomoku'),{'base_url':'https://api.deepseek.com/v1','model':'deepseek-flash','api_key':'test'})
        self.assertEqual(payload['response_format'],{'type':'json_object'})
        self.assertEqual(payload['thinking'],{'type':'disabled'})
        self.assertEqual(payload['max_tokens'],128)

    def test_billing_error_is_specific_without_echoing_key(self):
        from urllib.error import HTTPError
        opener=MagicMock();opener.open.side_effect=HTTPError('https://example.com',402,'Payment Required',{},BytesIO(b'sensitive upstream text'))
        with patch('llm.build_opener',return_value=opener):
            with self.assertRaisesRegex(RuntimeError,'余额不足'):
                choose_llm(replay(9,[],kind='gomoku'),{'base_url':'https://example.com/v1','model':'test','api_key':'test-secret'})

    def test_truncated_output_is_not_a_move(self):
        opener=MagicMock();opener.open.return_value=BytesIO(json.dumps({'choices':[{'finish_reason':'length','message':{'content':'{"choice":"B9"}'}}]}).encode())
        with patch('llm.build_opener',return_value=opener):
            with self.assertRaisesRegex(RuntimeError,'截断'):
                choose_llm(replay(9,[0],kind='gomoku'),{'base_url':'https://example.com/v1','model':'test'})

if __name__=='__main__':unittest.main()
