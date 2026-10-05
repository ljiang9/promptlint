#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""promptlint - 像 lint 代码一样检查 prompt 文件。

纯本地、纯标准库的 prompt 静态检查：把 prompt 当代码做 lint，
发现指令冲突、模糊措辞、缺失要素等常见问题。不调用任何 LLM。
"""

import argparse
import json
import re
import sys

VERSION = "0.1.0"

VAGUE_WORDS = ["大概", "可能", "尽量", "适当", "一些", "相关", "等等", "或许", "基本上", "差不多"]
HEDGE_PHRASES = ["如果可以的话", "最好能", "不妨", "试着", "可以考虑"]


def _sentences(text):
    return [s for s in re.split(r"[。！？\n]+", text) if s.strip()]


def check_empty(text):
    if not text.strip():
        return ("error", "文件为空，没有可检查的 prompt")
    return None


def check_too_long(text):
    n = len(text)
    if n > 12000:
        return ("error", f"全文 {n} 字符，超过 12000 字符：建议拆分成多个子 prompt")
    if n > 4000:
        return ("warn", f"全文 {n} 字符，超过 4000 字符：考虑精简或拆分")
    return None


def check_conflict(text):
    pairs = [
        ("必须", ["不要", "不能", "禁止", "绝不", "避免"]),
        ("总是", ["从不", "绝不", "不要"]),
        ("一定", ["不要", "不能", "禁止"]),
        ("确保", ["不要", "不能", "避免"]),
    ]
    hits = []
    for s in _sentences(text):
        s = s.strip()
        for pos, negs in pairs:
            if pos in s:
                for neg in negs:
                    if neg in s:
                        frag = s if len(s) <= 40 else s[:40] + "…"
                        hits.append(f"「{frag}」同时含「{pos}」与「{neg}」")
                        break
    if hits:
        return ("error", "；".join(hits[:3]))
    return None


def check_vars(text):
    found = re.findall(r"\{\{\s*([^{}]+?)\s*\}\}", text)
    seen = list(dict.fromkeys(v.strip() for v in found if v.strip()))
    if not seen:
        return None
    documented = re.search(r"变量说明|参数说明|输入变量|变量列表|##\s*变量", text)
    detail = "发现变量：" + "、".join("{{" + v + "}}" for v in seen)
    if len(seen) > 5 and not documented:
        return ("warn", f"{detail}（共 {len(seen)} 个，超过 5 个且无变量说明段）")
    return ("info", detail)


def check_no_role(text):
    if re.search(r"你是一个|你是.{0,8}(专家|助手|顾问|老师)|作为.{0,8}(专家|助手)|扮演", text):
        return None
    return ("warn", "没有定义角色（如“你是一名…专家”）：明确角色能稳定输出风格")


def check_no_output_format(text):
    if re.search(r"JSON|表格|列表|输出格式|格式要求", text):
        return None
    return ("warn", "没有指定输出格式：加上 JSON / 表格 / 列表等格式要求，结果更稳定")


def check_no_examples(text):
    if re.search(r"示例|例子|[Ee]xample|few-shot", text):
        return None
    return ("info", "没有 few-shot 示例：加 1-2 个输入输出示例通常能明显提升效果")


def check_vague(text):
    total = sum(text.count(w) for w in VAGUE_WORDS)
    if total >= 5:
        return ("warn", f"模糊词出现 {total} 次（大概/可能/尽量/适当…）：模糊词会让模型自行脑补，建议量化")
    return None


def check_hedging(text):
    total = sum(text.count(p) for p in HEDGE_PHRASES)
    if total >= 3:
        return ("warn", f"委婉表达出现 {total} 次（如果可以的话/最好能/不妨…）：指令请直接，少用商量语气")
    return None


def check_buried(text):
    tail = text[-200:]
    if re.search(r"记住|注意|重要|务必|千万", tail):
        return ("warn", "结尾 200 字内出现“记住/注意/重要”等强指令：关键约束建议前置，避免被过度加权")
    return None


def check_no_length_constraint(text):
    if re.search(r"\d+\s*字以内|\d+\s*字左右|不超过.{0,12}字|字数.{0,8}(限制|要求)", text):
        return None
    return ("info", "没有长度约束：加上“不超过 N 字”等约束，避免输出过长或过短")


def check_placeholder(text):
    if re.search(r"TODO|TBD|待补充|\bXXX\b", text):
        return ("warn", "发现 TODO / 待补充 / XXX 占位：上线前请补全")
    return None


RULES = [
    ("empty-prompt", "空 prompt", check_empty,
     "空文件没有检查意义，先排除。"),
    ("too-long", "prompt 过长", check_too_long,
     "超长 prompt 会稀释关键指令，模型对中间内容的注意力显著下降。"),
    ("conflict", "指令冲突", check_conflict,
     "同一句里既要求又禁止，模型只能二选一，结果不可预测。"),
    ("undefined-vars", "变量未说明", check_vars,
     "变量超过 5 个又没有说明文档，接手的人（和模型）都容易填错。"),
    ("no-role", "缺少角色定义", check_no_role,
     "角色设定是成本最低的风格控制器，一句话就能稳定人设。"),
    ("no-output-format", "缺少输出格式", check_no_output_format,
     "不指定格式，模型每次输出结构都可能不一样，下游难解析。"),
    ("no-examples", "缺少示例", check_no_examples,
     "1-2 个 few-shot 示例胜过几百字描述，是性价比最高的 prompt 技巧。"),
    ("vague-words", "模糊词过多", check_vague,
     "“大概/尽量”这类词把决策推给模型，每次运行都可能不一样。"),
    ("hedging", "语气过度委婉", check_hedging,
     "对模型用商量语气会降低指令强度，直接下指令效果更好。"),
    ("buried-instruction", "关键指令埋在结尾", check_buried,
     "模型对结尾有位置偏好，重要约束放结尾容易被误解为最高优先级。"),
    ("no-length-constraint", "缺少长度约束", check_no_length_constraint,
     "没有长度约束的输出长短全凭运气，加一句上限更可控。"),
    ("placeholder", "残留占位符", check_placeholder,
     "TODO 进生产环境等于把半成品发出去。"),
]


def lint(text):
    """返回 findings 列表，按 error > warn > info 排序。"""
    findings = []
    for rid, title, fn, explain in RULES:
        r = fn(text)
        if r:
            level, detail = r
            findings.append({"rule": rid, "title": title, "level": level,
                             "detail": detail, "explain": explain})
    order = {"error": 0, "warn": 1, "info": 2}
    findings.sort(key=lambda f: order[f["level"]])
    return findings


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="promptlint",
        description="像 lint 代码一样检查 prompt 文件（纯本地，不调用 LLM）")
    ap.add_argument("file", nargs="?", help="要检查的 prompt 文件（Markdown / 文本）")
    ap.add_argument("--strict", action="store_true",
                    help="严格模式：warn 级别也导致非零退出（默认只有 error 导致非零退出）")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出检查结果")
    ap.add_argument("--explain", action="store_true", help="为每条发现附上一句原因")
    ap.add_argument("--version", action="store_true", help="显示版本")
    args = ap.parse_args(argv)

    if args.version:
        print("promptlint " + VERSION)
        return 0
    if not args.file:
        ap.error("需要指定要检查的文件")

    try:
        with open(args.file, encoding="utf-8") as f:
            text = f.read()
    except FileNotFoundError:
        sys.stderr.write(f"error: 文件不存在：{args.file}\n")
        return 2
    except OSError as e:
        sys.stderr.write(f"error: 读取文件失败：{e}\n")
        return 2

    findings = lint(text)
    counts = {"error": 0, "warn": 0, "info": 0}
    for fnd in findings:
        counts[fnd["level"]] += 1

    if args.json:
        print(json.dumps({"file": args.file, "findings": findings,
                          "summary": counts},
                         ensure_ascii=False, indent=2))
    elif not findings:
        print("✅ 未发现明显问题，prompt 看起来很健康。")
    else:
        w_rule = max(len(f["rule"]) for f in findings)
        print(f"{'规则'.ljust(w_rule)} | 级别 | 说明")
        print("-" * (w_rule + 60))
        lvl_cn = {"error": "错误", "warn": "警告", "info": "提示"}
        for fnd in findings:
            print(f"{fnd['rule'].ljust(w_rule)} | {lvl_cn[fnd['level']]} | "
                  f"{fnd['title']}：{fnd['detail']}")
        if args.explain:
            print("\n规则说明：")
            for fnd in findings:
                print(f"  [{fnd['rule']}] {fnd['explain']}")
        print(f"\n共 {len(findings)} 条：{counts['error']} 错误 / "
              f"{counts['warn']} 警告 / {counts['info']} 提示")

    if counts["error"] > 0:
        return 1
    if args.strict and counts["warn"] > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
