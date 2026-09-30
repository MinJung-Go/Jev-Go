"""Freestyle Gomoku: alternating turns, no captures, >=5 wins, no forbidden moves."""
from game import IllegalMove
COLS='ABCDEFGHJKLMNOP'
class Gomoku:
    def __init__(self,size=9):
        if type(size) is not int or size not in (9,15):raise ValueError('五子棋支持9路或15路')
        self.size=size;self.board=[0]*(size*size);self.turn=1;self.moves=[];self.winner=0
    @property
    def over(self):return bool(self.winner) or all(self.board)
    def coord(self,i):return COLS[i%self.size]+str(self.size-i//self.size)
    def lines(self,i,color):
        r,c=divmod(i,self.size);result=[]
        for dr,dc in ((0,1),(1,0),(1,1),(1,-1)):
            count=1;ends=0
            for sign in (-1,1):
                rr,cc=r+sign*dr,c+sign*dc
                while 0<=rr<self.size and 0<=cc<self.size and self.board[rr*self.size+cc]==color:
                    count+=1;rr+=sign*dr;cc+=sign*dc
                if 0<=rr<self.size and 0<=cc<self.size and self.board[rr*self.size+cc]==0:ends+=1
            result.append((count,ends))
        return result
    def legal(self):return [] if self.over else [i for i,v in enumerate(self.board) if not v]
    def play(self,i):
        if self.over:raise IllegalMove('对局已结束')
        if type(i) is not int or not 0<=i<len(self.board):raise IllegalMove('五子棋必须在棋盘空点落子，不允许停手')
        if self.board[i]:raise IllegalMove('这里已经有棋子')
        if max(n for n,_ in self.lines(i,self.turn))>=5:self.winner=self.turn
        self.board[i]=self.turn;self.moves.append(i);self.turn=3-self.turn
    def public(self):
        return dict(kind='gomoku',size=self.size,board=self.board,turn=self.turn,moves=self.moves,legal=self.legal(),over=self.over,winner=self.winner,captures={1:0,2:0},passes=0,area=None)
    def features(self):
        return {self.coord(i):dict(index=i,own=self.lines(i,self.turn),opponent=self.lines(i,3-self.turn)) for i in self.legal()}
    def candidates(self):
        features=self.features()
        wins={c:f for c,f in features.items() if max(n for n,_ in f['own'])>=5}
        blocks={c:f for c,f in features.items() if max(n for n,_ in f['opponent'])>=5}
        if wins:return wins,'代码筛选：本手成五'
        if blocks:return blocks,'代码筛选：阻挡对方下一手成五（不保证能挡住双威胁）'
        return features,'全部合法落点；代码提供连续棋子与开放端点特征'
    def payload(self,model='jev-1.13.0'):
        features,note=self.candidates()
        criteria={c:f"Play {c}. Your resulting (run length, open ends) in horizontal/vertical/two diagonals: {f['own']}. Opponent if they instead play here: {f['opponent']}." for c,f in features.items()}
        n=self.size
        return dict(model=model,state=dict(game='Freestyle Gomoku, NOT Go',board_size=n,board_rows_top_to_bottom=[''.join('.XO'[v] for v in self.board[r*n:(r+1)*n]) for r in range(n)],columns=list(COLS[:n]),row_numbers_top_to_bottom=list(range(n,0,-1)),legend={'X':'black','O':'white','.':'empty'},your_color='black' if self.turn==1 else 'white',rules='Alternate one stone each. No captures, no passes, no forbidden moves. Five or more contiguous stones wins.',candidate_policy=note),questions={'move':dict(type='choice',instructions='Win by making a contiguous line of at least five. Prioritize immediate win, then block opponent immediate win. Create open fours and double threats, block opponent open fours. Prefer open threes over closed runs. Early in the game develop connected threats near center. Features count contiguous runs only, so also inspect gaps on the board. Select exactly one offered coordinate.',criteria=criteria)})
    def local_move(self):
        f,_=self.candidates()
        def score(item):
            x=item[1];r,c=divmod(x['index'],self.size);mid=(self.size-1)/2
            def strength(lines):return sum((10**min(n,5))*(1+ends) for n,ends in lines if ends or n>=5)
            return strength(x['own'])+1.1*strength(x['opponent'])-abs(r-mid)-abs(c-mid)
        return max(f.items(),key=score)[1]['index'] if f else None
