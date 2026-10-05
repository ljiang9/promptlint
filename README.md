# promptlint

像 lint 代码一样检查你的 prompt 文件。纯本地、纯 Python 标准库，不调用任何 LLM。

把 prompt 当代码做静态检查：指令冲突、模糊措辞、缺失角色/格式/示例等 12 条规则，一条命令出报告。

## 安装

零依赖，Python 3.10+ 直接运行：

```bash
python -m promptlint your-prompt.md
# 或
python promptlint.py your-prompt.md
```

## 用法

```bash
promptlint prompt.md            # 检查并打印报告
promptlint prompt.md --strict   # 严格模式：warn 也导致非零退出（可接 CI）
promptlint prompt.md --json     # JSON 输出
promptlint prompt.md --explain  # 为每条发现附上一句原因
```

退出码：`0` 无问题（或仅提示）；`1` 发现 error（`--strict` 下 warn 也算）；`2` 文件读不出。

## 规则（12 条）

| 规则 | 级别 | 检查内容 |
|---|---|---|
| `empty-prompt` | 错误 | 文件为空 |
| `too-long` | 警告/错误 | >4000 字符警告，>12000 字符错误 |
| `conflict` | 错误 | 同一句内同时出现"必须"与"不要"等正反指令 |
| `undefined-vars` | 警告/提示 | `{{变量}}` 超过 5 个且无变量说明段 |
| `no-role` | 警告 | 缺少"你是一名…专家"类角色定义 |
| `no-output-format` | 警告 | 未指定 JSON / 表格 / 列表等输出格式 |
| `no-examples` | 提示 | 缺少 few-shot 示例 |
| `vague-words` | 警告 | 大概/可能/尽量/适当等模糊词 ≥5 次 |
| `hedging` | 警告 | "如果可以的话/最好能"等委婉表达 ≥3 次 |
| `buried-instruction` | 警告 | 结尾 200 字内藏着"记住/注意/重要"强指令 |
| `no-length-constraint` | 提示 | 缺少"不超过 N 字"类长度约束 |
| `placeholder` | 警告 | 残留 TODO / 待补充 / XXX |

示例：

```
$ python -m promptlint examples/bad.md
conflict             | 错误 | 指令冲突：「回复必须简洁，不要省略任何细节…」同时含「必须」与「不要」
too-long             | 警告 | prompt 过长：全文 6290 字符，超过 4000 字符：考虑精简或拆分
undefined-vars       | 警告 | 变量未说明：发现变量：{{user_name}}、{{order_id}}…（共 7 个，超过 5 个且无变量说明段）
...
共 9 条：1 错误 / 6 警告 / 2 提示
```

`examples/good.md` 只剩 1 条提示（变量清单），`examples/bad.md` 故意埋了 9 个问题，可对照看。

## 诚实说明

- 这是**启发式风格检查**，不是 prompt 质量保证：规则全过不代表 prompt 一定好用，最终还得看实际输出。
- `conflict` 只看同一句内的正反关键词对（如"必须…不要"），"必须包含 A，不要包含 B"这类正常写法也会被标出来——请人工确认，这是故意的（宁可误报，不漏报）。
- 模糊词/委婉表达的阈值（5 次 / 3 次）是拍脑袋定的，不服可以改源码顶部的常量。
- 中文为主、英文 prompt 的部分规则（如 `no-role`）可能不触发。

## License

MIT，Copyright (c) 2026 ljiang9
