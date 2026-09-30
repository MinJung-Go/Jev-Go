# 中断局重赛

按用户要求，将原20局中断的10局从空盘重新开始，沿用原局号与黑白分配（DeepSeek执黑8局、Jev执黑2局）。模型、提示词、输出预算与规则辅助保持不变。获胜或满盘结束，输出错误立即停止；原记录完整保留，已完成局未重赛。

| 原局号 | 黑方 | 手数 | 本次结果 |
| --- | --- | --- | --- |
| 1 | DeepSeek | 13 | DeepSeek 胜 |
| 3 | DeepSeek | 4 | 再次中断 |
| 5 | DeepSeek | 11 | DeepSeek 胜 |
| 6 | Jev | 18 | DeepSeek 胜 |
| 7 | DeepSeek | 2 | 再次中断 |
| 10 | Jev | 3 | 再次中断 |
| 11 | DeepSeek | 4 | 再次中断 |
| 13 | DeepSeek | 2 | 再次中断 |
| 15 | DeepSeek | 4 | 再次中断 |
| 17 | DeepSeek | 9 | DeepSeek 胜 |

本次重赛：{'llm': 4, 'jev': 0, 'draws': 0, 'errors': 6}。结合原来10局已完成的结果：{'jev_wins': 8, 'deepseek_wins': 6, 'draws': 0, 'unresolved': 6}。重赛不抹去此前10次失败，不能将完成率重写为100%；筛选重赛后的胜负也不是无条件总体胜率。

每手状态已重放核对，并独立扫描四个方向确认连五终局。summary.json仅统计本次重赛；combined-summary.json按原20个局号合并当前结果。runner.py保留实际脚本，plan.json保存原记录来源与局号。
