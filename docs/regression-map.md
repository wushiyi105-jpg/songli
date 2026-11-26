# 回归测试映射

这一轮改的 4 个 issue 与测试的对应关系。写下来是为了下次动 `rules.py` / `web.py` 时知道哪条测试会挡住。

## #3 非法或截断 JSON 回 500,还带解析器原文

**原来**:`json.loads` 抛 `JSONDecodeError`,落到兜底 `except Exception`,回 500 并把 `str(e)` 原样给前端,用户看到「请求失败:Unterminated string starting at: line 1 column 10」。

**改法**:`do_POST` 先单独 `try` 读体,解析失败回 **400** + `{"error": "请求体不是合法 JSON"}`;兜底 500 只回 `{"error": "服务器内部错误"}`。读体放在判路径之前,未知路径与非法 JSON 走同一条路径。

- 测试:`TestHttp.test_truncated_json_is_400` —— 断言 400、断言响应里有「不是合法 JSON」、断言**没有** `Unterminated` / `Expecting`。
- 连带:`TestHttp.test_empty_body_is_not_500` —— 空 body 仍按 `{}` 处理。

## #4 「爸妈」「外婆」「外甥女」判不出关系,还提示「没写送给谁」

**原来**:`rules.parse()` 只认 `RELATIONS` 里 9 个词,口语称呼一个都不在,判不出来之后 `mock.risks()` 又无条件写「没写送给谁,关系决定价位与话术」,等于告诉用户他没写过。

**改法**:加 `SYNONYMS` 把口语称呼映射到 9 个类别(爸妈→父母、外婆/舅舅→长辈、外甥女/侄子→孩子、老板→领导、闺蜜/同学→朋友);判不出时提示改成「没写关系类别(…),话术按通用口径」,不再断言「没写送给谁」。

- 测试:`TestRules.test_relation_synonyms` —— 五个代表性称呼各自归到对的类别。
- 测试:`TestRules.test_no_relation_risk_does_not_claim_unwritten` —— 风险里必须有「关系类别」,且**不能**出现「没写送给谁」。

## #5 预算 50 元时包装一格是 -5

**原来**:`split_budget()` 三格先各按比例取整,`wrap = budget - main - flower - card` 兜底;50 元时 40 + 10 + 5 = 55 超了预算,兜底那格变负。

**改法**:三格之和一旦超预算,先砍花、再砍卡(不低于 0)、最后主礼兜底,四格不允许负数,合计严格等于预算。50 元现在是 40 / 5 / 5 / 0。

- 测试:`TestRules.test_split_budget_never_negative` —— 9 个预算逐格断言非负、合计等于预算。
- 测试:`TestRules.test_split_budget_big_numbers_unchanged` —— 500 / 800 的比例不能被这次改动带偏。
- 测试:`TestCli.test_plan_small_budget_no_negative` —— 走真进程,输出里不能出现 `-5`。

## #6 「预算五百」被吞掉

**原来**:`BUDGET_RE` 只匹配阿拉伯数字,中文数字(五十 / 两百五 / 五百 / 一千二 / 一万五)完全没有覆盖,`预算` 判成未写,拆分整块消失。

**改法**:加 `ZH_BUDGET_RE` 与 `zh_number()`,支持「千以内 + 省略说法」(一百五 = 150、一千二 = 1200、两百五 = 250);阿拉伯数字仍优先,区间写法取上限。

- 测试:`TestRules.test_zh_budget_five_hundred` —— 五百 / 八百 / 一千二 / 两百五 / 十五。
- 测试:`TestRules.test_digit_budget_still_wins` —— 原有 `预算 500` 与 `500-800` 不受影响。

## #7 「满月」三套方案全空,标题照打

**原来**:`data/gifts.json` 里没有一条 `occasions` 含「满月」,`pool()` 过滤后为空,`schemes()` 只有「去掉预算再试」一层退路,于是返回 `[]`,`cli.render()` 未判空,照样打「🎯 三套方案」标题。

**改法**:`schemes()` 加退路(场合空 → 去掉场合按关系+预算 → 再放开预算),`check()` 给出 `note`,风险里明说「礼物池里还没有『满月』场合的对应品类,方案按关系与预算挑,时机与话术仍按场合给」;`render()` 判空时打印提示而不是空标题。

**没做的**:没有往池里补婴儿棉品 / 洗护品类——那要动 200 条数据与 README 的数字,留给数据集那一轮。这条 note 是临时的诚实交代,不是解决方案。

- 测试:`TestRules.test_month_occasion_falls_back_with_note`
- 测试:`TestCases.test_case04_has_schemes_and_note`
