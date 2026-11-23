#!/usr/bin/env python3
"""提交信息语言校验：标题英文、正文中文。

由 .githooks/commit-msg 调用（参数是 Git 生成的提交信息文件路径）。
校验通过返回 0；失败返回 1 并打印具体原因，Git 会中止本次提交。

规则来源：AGENTS.md / CLAUDE.md 的「Git 提交规则」。
"""
from __future__ import annotations

import re
import sys

SUBJECT_MAX_CHARS = 72
MIN_CJK_CHARS = 4
MIN_CJK_RATIO = 0.10

SUBJECT_LATIN_RE = re.compile(r"[A-Za-z]")
CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
LATIN_LETTER_RE = re.compile(r"[A-Za-z]")
# Git / rebase 自动生成的提交：正文由工具写死（英文），只校验标题
GENERATED_SUBJECT_PREFIXES = ("Merge ", "Revert ", "fixup! ", "squash! ", "amend! ")
SCISSORS_RE = re.compile(r"^#\s*-{4,}\s*>8\s*-{4,}")
ATTRIBUTION_RE = re.compile(
    r"^\s*co-authored-by\s*:"
    r"|^\s*(?:🤖\s*)?generated (?:with|by) (?:claude|chatgpt|copilot)\b",
    re.IGNORECASE,
)

RULES_HELP = """\
提交信息约定（AGENTS.md「Git 提交规则」）：
  标题：英文、纯 ASCII、≤ {max_subject} 字符，形如 fix(items): keep the timeline order stable
  正文：标题下空一行，用中文说明改了什么、为什么改（可夹带代码标识符）
  署名：禁止 Co-Authored-By 等任何 AI 相关署名
  修正：git commit --amend（或重新执行带 -m 的提交命令）""".format(
    max_subject=SUBJECT_MAX_CHARS
)


def _reconfigure_streams() -> None:
    """Windows 上 stderr 默认可能不是 UTF-8，否则中文报错会二次崩溃。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def _read_lines(path: str) -> list[str]:
    """读取提交信息，去掉 Git 模板注释 / verbose diff，并裁掉首尾空行。"""
    with open(path, encoding="utf-8", errors="replace") as handle:
        raw = handle.read()

    lines: list[str] = []
    for line in raw.splitlines():
        if SCISSORS_RE.match(line):
            break
        if line.startswith("#"):
            continue
        lines.append(line.rstrip())

    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    return lines


def _excerpt(text: str, limit: int = 60) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _fail(errors: list[str]) -> int:
    sys.stderr.write("\n提交信息未通过检查：\n")
    for error in errors:
        sys.stderr.write("  - {}\n".format(error))
    sys.stderr.write("\n" + RULES_HELP + "\n")
    return 1


def _check_subject(subject: str) -> list[str]:
    errors: list[str] = []
    offenders = sorted({ch for ch in subject if not 0x20 <= ord(ch) <= 0x7E})
    if offenders:
        shown = " ".join(repr(ch) for ch in offenders[:6])
        errors.append(
            "标题必须为英文（仅 ASCII），发现非 ASCII 字符 {}：{}".format(
                shown, _excerpt(subject)
            )
        )
    if not SUBJECT_LATIN_RE.search(subject):
        errors.append("标题必须包含英文单词：{}".format(_excerpt(subject)))
    if len(subject) > SUBJECT_MAX_CHARS:
        errors.append(
            "标题长度 {} 超过 {} 字符上限".format(len(subject), SUBJECT_MAX_CHARS)
        )
    return errors


def _check_body(body_text: str) -> list[str]:
    if not body_text:
        return ["正文必填：请在标题下空一行，用中文写明改动内容与原因"]

    errors: list[str] = []
    cjk = len(CJK_RE.findall(body_text))
    latin = len(LATIN_LETTER_RE.findall(body_text))
    if cjk < MIN_CJK_CHARS:
        errors.append(
            "正文必须用中文展开说明（当前 {} 个汉字，至少 {} 个）".format(
                cjk, MIN_CJK_CHARS
            )
        )
    elif cjk / (cjk + latin) < MIN_CJK_RATIO:
        errors.append(
            "正文以英文为主（汉字 {} / 拉丁字母 {}），请改用中文叙述".format(cjk, latin)
        )
    return errors


def main(argv: list[str]) -> int:
    _reconfigure_streams()
    if len(argv) != 2:
        sys.stderr.write("用法：check_commit_msg.py <commit-msg-file>\n")
        return 1

    lines = _read_lines(argv[1])
    if not lines:
        return _fail(["提交信息为空"])

    attribution_errors = [
        "禁止 AI 相关署名或生成声明：{}".format(_excerpt(line))
        for line in lines
        if ATTRIBUTION_RE.search(line)
    ]
    if attribution_errors:
        return _fail(attribution_errors)

    subject = lines[0]
    body_text = "\n".join(lines[1:]).strip()

    errors = _check_subject(subject)
    if not subject.startswith(GENERATED_SUBJECT_PREFIXES):
        errors.extend(_check_body(body_text))
    return _fail(errors) if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
