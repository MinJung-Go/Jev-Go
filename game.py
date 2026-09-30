"""Small-board Go: positional superko, no suicide, area scoring, no dead-stone adjudication."""
from copy import deepcopy

COLS = 'ABCDEFGHJKLMNOPQRST'

class IllegalMove(ValueError):
    pass

class Game:
    def __init__(self, size=9):
        if type(size) is not int or size not in (5, 9, 13, 19):
            raise ValueError('棋盘支持 5、9、13 或 19 路')
        self.size = size
        self.board = [0] * (size * size)
        self.turn = 1
        self.moves = []
        self.seen = {tuple(self.board)}
        self.passes = 0
        self.captures = {1: 0, 2: 0}

    def neighbors(self, i):
        r, c = divmod(i, self.size)
        for dr, dc in ((-1,0),(1,0),(0,-1),(0,1)):
            rr, cc = r+dr, c+dc
            if 0 <= rr < self.size and 0 <= cc < self.size:
                yield rr*self.size+cc

    def group(self, board, i):
        color = board[i]
        stones, liberties, todo = {i}, set(), [i]
        while todo:
            for j in self.neighbors(todo.pop()):
                if board[j] == 0:
                    liberties.add(j)
                elif board[j] == color and j not in stones:
                    stones.add(j); todo.append(j)
        return stones, liberties

    @property
    def over(self):
        return self.passes >= 2

    def coord(self, i):
        return 'PASS' if i is None else COLS[i % self.size] + str(self.size-i//self.size)

    def simulate(self, i):
        if self.over:
            raise IllegalMove('对局已结束，请重新开局')
        if type(i) is not int or not 0 <= i < len(self.board):
            raise IllegalMove('落点超出棋盘')
        if self.board[i]:
            raise IllegalMove('这里已经有棋子')
        board = self.board.copy(); board[i] = self.turn
        removed = set()
        for j in self.neighbors(i):
            if board[j] == 3-self.turn:
                stones, libs = self.group(board, j)
                if not libs: removed.update(stones)
        for j in removed: board[j] = 0
        _, libs = self.group(board, i)
        if not libs: raise IllegalMove('禁止自杀落子')
        if tuple(board) in self.seen: raise IllegalMove('禁止重复出现已有盘面（全局同形禁着）')
        return board, len(removed), len(libs)

    def play(self, i):
        if self.over: raise IllegalMove('对局已结束')
        if i is None:
            self.passes += 1
        else:
            board, removed, _ = self.simulate(i)
            self.board = board
            self.captures[self.turn] += removed
            self.seen.add(tuple(board)); self.passes = 0
        self.moves.append(i); self.turn = 3-self.turn

    def legal(self):
        if self.over: return []
        result = []
        for i, v in enumerate(self.board):
            if not v:
                try: self.simulate(i); result.append(i)
                except IllegalMove: pass
        return result

    def area(self):
        score = {1:self.board.count(1),2:self.board.count(2)}
        visited = set(); neutral = 0
        for i, v in enumerate(self.board):
            if v or i in visited: continue
            region, border, todo = {i}, set(), [i]; visited.add(i)
            while todo:
                for j in self.neighbors(todo.pop()):
                    if self.board[j]: border.add(self.board[j])
                    elif j not in visited:
                        visited.add(j); region.add(j); todo.append(j)
            if len(border) == 1: score[next(iter(border))] += len(region)
            else: neutral += len(region)
        return {'black':score[1], 'white':score[2], 'komi':6.5,
                'white_total':score[2]+6.5, 'neutral':neutral,
                'lead':score[1]-score[2]-6.5}

    def public(self):
        return dict(kind="go",size=self.size, board=self.board, turn=self.turn, moves=self.moves,
                    legal=self.legal(), passes=self.passes, over=self.over,
                    captures=self.captures, area=self.area())

    def options(self):
        result = {}
        for i in self.legal():
            board, captures, libs = self.simulate(i)
            friends = set()
            rescue = 0
            for j in self.neighbors(i):
                if self.board[j] == self.turn and j not in friends:
                    stones, oldlibs = self.group(self.board,j); friends.update(stones)
                    if len(oldlibs)==1 and libs>1: rescue += len(stones)
            touches = [self.board[j] for j in self.neighbors(i)]
            eye = bool(touches) and all(v==self.turn for v in touches) and not captures
            r,c = divmod(i,self.size)
            result[self.coord(i)] = dict(index=i, captures=captures, liberties=libs,
                rescued_stones=rescue, fills_surrounded_point=eye,
                adjacent_friend=touches.count(self.turn), adjacent_opponent=touches.count(3-self.turn),
                edge_distance=min(r,c,self.size-1-r,self.size-1-c))
        return result

    def payload(self, model='jev-1.13.0'):
        options = self.options()
        candidate_note = '全部合法落点'
        if len(options)>240:
            occupied=[divmod(i,self.size) for i,v in enumerate(self.board) if v]
            mid=(self.size-1)/2
            def priority(item):
                f=item[1];r,c=divmod(f['index'],self.size)
                near=min((max(abs(r-rr),abs(c-cc)) for rr,cc in occupied),default=0)
                return (bool(f['captures'] or f['rescued_stones']),-near,-abs(r-mid)-abs(c-mid))
            options=dict(sorted(options.items(),key=priority,reverse=True)[:240])
            candidate_note='代码预筛240个落点：优先提子/救子，其次距已有棋子近，再靠近中心；可能遗漏好棋，无全局搜索'
        criteria = {}
        for coord, f in options.items():
            criteria[coord] = (f'Play at {coord}. Captures {f["captures"]} opposing stones immediately; '
                f'own resulting connected group has {f["liberties"]} liberties; '
                f'rescues {f["rescued_stones"]} friendly stones from immediate atari; '
                f'fills a point surrounded by own stones: {f["fills_surrounded_point"]}; '
                f'distance from edge: {f["edge_distance"]}.')
        # An explicit opening policy, not a change to legal Go moves.
        if len(self.moves)>=self.size*2 or self.passes or not options:
            criteria['PASS'] = 'Pass only if no useful territory, rescue or attack remains. Two passes end the game.'
        rows = [''.join('.XO'[v] for v in self.board[r*self.size:(r+1)*self.size]) for r in range(self.size)]
        return {'model':model, 'state':{'game':'Go', 'board_size':self.size,
            'board_rows_top_to_bottom':rows,'columns':list(COLS[:self.size]),
            'row_numbers_top_to_bottom':list(range(self.size,0,-1)),
            'legend':{'X':'black','.':'empty','O':'white'},
            'your_color':'black' if self.turn==1 else 'white',
            'previous_move_passed':self.passes==1,'white_komi':6.5,
            'recent_moves':[{'color':'black' if k%2==0 else 'white','move':self.coord(m)} for k,m in list(enumerate(self.moves))[-10:]],
            'candidate_policy':candidate_note+'；开局少于棋盘路数两倍手数且对方未停手、有合法落点时，候选不含PASS',
            'note':'All offered placements are legal. Arithmetic and immediate tactical features were computed by code, not by you.'},
            'questions':{'move':{'type':'choice','instructions':
                'You play the stated your_color, not always black. Select one legal move. Do not pass merely because no capture is available. Develop territory and connected groups. Prioritize saving valuable threatened groups and useful captures; '
                'avoid self-atari and unnecessary filling of your own eyes. Consider future territory, not just immediate captures. '
                'Pass when further play has no useful benefit. This is one-step judgment; no tree search is supplied.',
                'criteria':criteria}}}

    def local_move(self):
        """Explicitly labelled handcrafted opponent; never presented as Jev."""
        options = self.options()
        if not options: return None
        scored = []
        for f in options.values():
            score = 12*f['captures']+9*f['rescued_stones'] + min(f['liberties'],4)
            score += f['edge_distance']*.15 + f['adjacent_opponent']*.2
            if f['liberties']==1: score -= 15
            if f['fills_surrounded_point']: score -= 20
            scored.append((score, -f['index'], f['index']))
        top = max(scored)
        return top[2] if top[0] > 0 else None


def replay(size, moves, kind="go"):
    if kind not in ("go","gomoku"):raise ValueError("未知棋种")
    if not isinstance(moves,list) or len(moves)>500:
        raise ValueError('棋谱必须是最多 500 手的列表')
    if kind=="gomoku":
        from gomoku import Gomoku
        g=Gomoku(size)
    else:g=Game(size)
    for m in moves: g.play(m)
    return g
