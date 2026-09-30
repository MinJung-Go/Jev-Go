import unittest
from game import Game,replay,IllegalMove
from gomoku import Gomoku

class Variants(unittest.TestCase):
    def test_go_sizes_and_model_candidate_limit(self):
        for size in (5,9,13,19):
            g=Game(size);self.assertEqual(len(g.legal()),size*size)
            candidates=g.payload()['questions']['move']['criteria']
            self.assertLessEqual(len(candidates),255)
            self.assertNotIn('PASS',candidates)
        self.assertEqual(Game(19).coord(360),'T1')
    def test_black_first_white_cannot_pass_opening(self):
        g=replay(9,[40]);self.assertEqual(g.turn,2)
        self.assertNotIn('PASS',g.payload()['questions']['move']['criteria'])
    def test_human_pass_can_be_answered(self):
        g=replay(19,[None]);self.assertIn('PASS',g.payload()['questions']['move']['criteria'])
    def test_gomoku_alternation_and_no_pass(self):
        g=replay(9,[0,1,2],kind='gomoku')
        self.assertEqual(g.board[:3],[1,2,1]);self.assertEqual(g.turn,2)
        with self.assertRaises(IllegalMove):g.play(None)
    def test_wins_all_directions(self):
        for moves in ([0,9,1,10,2,11,3,12,4],[0,1,9,2,18,3,27,4,36],[0,1,10,2,20,3,30,4,40],[4,0,12,1,20,2,28,3,36]):
            g=replay(9,list(moves),kind='gomoku')
            self.assertEqual(g.winner,1);self.assertTrue(g.over)
            with self.assertRaises(IllegalMove):g.play(80)
    def test_overline_wins(self):
        g=Gomoku(9)
        for i in [0,1,2,4,5]:g.board[i]=1
        g.play(3);self.assertEqual(g.winner,1)
    def test_win_precedes_block(self):
        g=Gomoku(9);g.board[:4]=[1]*4;g.board[9:13]=[2]*4
        candidates,note=g.candidates();self.assertEqual(set(candidates),{'E9'})
        self.assertIn('成五',note)
    def test_white_blocks_immediate_black_win(self):
        g=replay(9,[0,9,1,11,2,13,3],kind='gomoku')
        self.assertEqual(set(g.payload()['questions']['move']['criteria']),{'E9'})
    def test_full_board_draw_without_five(self):
        g=Gomoku(9);g.board=[1+((r+2*c)%4//2) for r in range(9) for c in range(9)]
        self.assertTrue(g.over);self.assertEqual(g.winner,0);self.assertEqual(g.legal(),[])
    def test_invalid_variant(self):
        with self.assertRaises(ValueError):replay(9,[],kind='chess')
        with self.assertRaises(ValueError):Gomoku(19)

if __name__=='__main__':unittest.main()
