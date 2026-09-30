import unittest
from unittest.mock import patch
import json
from game import Game,IllegalMove,replay
from server import choose_jev

class Rules(unittest.TestCase):
    def setup_board(self, rows,turn=1):
        g=Game(5);g.board=[int(x) for row in rows for x in row];g.turn=turn;g.seen={tuple(g.board)};return g
    def test_capture(self):
        g=self.setup_board(['01000','12100','00000','00000','00000']);g.play(11)
        self.assertEqual(g.board[6],0);self.assertEqual(g.captures[1],1)
    def test_multi_capture(self):
        g=self.setup_board(['01100','12210','00100','00000','00000']);g.play(11)
        self.assertEqual(g.captures[1],2)
    def test_suicide_atomic(self):
        g=self.setup_board(['02000','20200','02000','00000','00000']);old=g.board.copy()
        with self.assertRaises(IllegalMove):g.play(6)
        self.assertEqual(g.board,old);self.assertEqual(g.turn,1)
    def test_capture_not_suicide(self):
        g=self.setup_board(['02100','21000','10000','00000','00000']);g.play(0)
        self.assertEqual(g.board[1],0)
    def test_ko(self):
        g=self.setup_board(['02100','21010','02100','00000','00000']);g.play(7)
        with self.assertRaises(IllegalMove):g.play(6)
    def test_superko_checks_all_history(self):
        g=Game(5);b=g.board.copy();b[0]=1;g.seen.add(tuple(b))
        with self.assertRaises(IllegalMove):g.play(0)
    def test_pass_end(self):
        g=replay(5,[None,None]);self.assertTrue(g.over);self.assertEqual(g.legal(),[])
        with self.assertRaises(IllegalMove):g.play(0)
    def test_validation(self):
        for move in [-1,25,True,'A1']:
            with self.assertRaises(IllegalMove):Game(5).play(move)
        with self.assertRaises(IllegalMove):replay(5,[0,0])
        with self.assertRaises(ValueError):replay(5,[None]*501)
    def test_area_empty_and_enclosed(self):
        self.assertEqual(Game(5).area()['neutral'],25)
        g=self.setup_board(['11111','10001','10001','10001','11111']);self.assertEqual(g.area()['black'],25)
    def test_payload_all_legal(self):
        g=Game(9);p=g.payload();self.assertEqual(len(p['questions']['move']['criteria']),81)
        self.assertEqual(p['state']['your_color'],'black')
    def test_local_is_legal(self):
        g=Game(5)
        for _ in range(100):
            if g.over:break
            m=g.local_move();self.assertTrue(m is None or m in g.legal());g.play(m)
    def test_missing_key_no_fallback(self):
        with patch.dict('os.environ',{},clear=True):
            with self.assertRaisesRegex(RuntimeError,'TYPESAFE_API_KEY'):choose_jev(Game(5))
    def test_invalid_api_answer_rejected(self):
        from io import BytesIO
        data={'answers':{'move':{'type':'choice','choice':'Z99'}}}
        with patch.dict('os.environ',{'TYPESAFE_API_KEY':'test'}),patch('server.urlopen',return_value=BytesIO(json.dumps(data).encode())):
            with self.assertRaisesRegex(RuntimeError,'无效选项'):choose_jev(Game(5))

if __name__=='__main__':unittest.main()
