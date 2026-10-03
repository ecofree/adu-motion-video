#!/usr/bin/env python3
"""数学符号 → 口语中文。TTS 之前必跑：把 LaTeX/数学符号转成能直接朗读的文本。

用法：
    echo '解 $\\frac{x}{2} + x^2 = 5$' | python3 math2speech.py
    python3 math2speech.py --text '...'        # 单条
    python3 math2speech.py --check '...'       # 只检查是否还有未处理的符号

规则是可扩展的：按学科在 SYMBOL_RULES 里加。转换后仍建议人工听一遍，
尤其是多层分式和根号嵌套。
"""
import argparse
import re
import sys

# 顺序很重要：先处理复杂结构，再处理单个符号
LATEX_RULES = [
    # \frac{a}{b} → b分之a（教学口语习惯）
    (re.compile(r'\\frac\{([^{}]+)\}\{([^{}]+)\}'),
     lambda m: f"{_speak(m.group(2))}分之{_speak(m.group(1))}"),
    # x^{2} / x^2 → x的平方；x^{n} → x的n次方
    (re.compile(r'\^(\{(\d+)\}|(\d+))'),
     lambda m: '的平方' if (m.group(2) or m.group(3)) == '2'
     else f"的{(m.group(2) or m.group(3))}次方"),
    # \sqrt{x} → 根号x；\sqrt[n]{x} → n次根号x
    (re.compile(r'\\sqrt\[(\d+)\]\{([^{}]+)\}'),
     lambda m: f"{m.group(1)}次根号{_speak(m.group(2))}"),
    (re.compile(r'\\sqrt\{([^{}]+)\}'),
     lambda m: f"根号{_speak(m.group(1))}"),
    (re.compile(r'\\sqrt\s*([a-zA-Z0-9])'),
     lambda m: f"根号{m.group(1)}"),
]

SYMBOL_RULES = [
    ('×', '乘'), ('÷', '除以'), ('±', '正负'), ('≠', '不等于'),
    ('≈', '约等于'), ('≤', '小于等于'), ('≥', '大于等于'),
    ('∠', '角'), ('△', '三角形'), ('∥', '平行'), ('⊥', '垂直'),
    ('∞', '无穷大'), ('π', '派'), ('°', '度'),
    ('→', '得到'), ('⇒', '所以'), ('∴', '所以'), ('∵', '因为'),
    ('∈', '属于'), ('∪', '并'), ('∩', '交'),
    ('…', '，以此类推'), ('...', '，以此类推'),
]

GREEK = {'α': '阿尔法', 'β': '贝塔', 'γ': '伽马', 'θ': '西塔',
         'λ': '兰姆达', 'μ': '缪', 'Δ': '德尔塔', 'δ': '德尔塔',
         'Σ': '西格玛', 'σ': '西格玛', 'φ': '斐', 'ω': '欧米伽'}


def _speak(s: str) -> str:
    """递归处理嵌套在 \frac{}{} 里的简短表达式。"""
    s = s.strip()
    for pat, rep in LATEX_RULES:
        s = pat.sub(rep, s)
    for src, dst in SYMBOL_RULES:
        s = s.replace(src, dst)
    for src, dst in GREEK.items():
        s = s.replace(src, dst)
    return s


def to_speech(text: str) -> str:
    # 去掉 $ 包裹
    text = re.sub(r'\$([^\$]+)\$', lambda m: _speak(m.group(1)), text)
    # 行间公式 \[ \]
    text = re.sub(r'\\\[(.+?)\\\]', lambda m: _speak(m.group(1)), text,
                  flags=re.S)
    # 残留的 LaTeX 命令 → 去掉反斜杠
    text = re.sub(r'\\([a-zA-Z]+)', r'\1', text)
    text = re.sub(r'[{}]', '', text)
    # 普通符号（∠ ° △ 等）全文转换，不只公式内
    for src, dst in SYMBOL_RULES:
        text = text.replace(src, dst)
    for src, dst in GREEK.items():
        text = text.replace(src, dst)
    # 多余空白
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def check_leftover(text: str) -> list:
    """返回疑似未处理的符号/命令，供人工复核。"""
    found = []
    for pat in (r'\\[a-zA-Z]+', r'\^', r'_', r'\$'):
        for m in re.finditer(pat, text):
            found.append(m.group(0))
    return sorted(set(found))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--text', default=None)
    ap.add_argument('--check', default=None)
    args = ap.parse_args()
    if args.check is not None:
        converted = to_speech(args.check)
        left = check_leftover(converted)
        print('OK' if not left else f"待处理: {left}\n转换后: {converted}")
        return 0 if not left else 1
    text = args.text if args.text is not None else sys.stdin.read()
    print(to_speech(text))


if __name__ == '__main__':
    main()
