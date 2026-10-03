#!/usr/bin/env python3
"""精确配图：代码生成的数学图形，标注 100% 准确。

原则：凡是"对错分明"的图形（几何、函数图像、数轴、统计图）一律代码生成，
不用生成式图像碰运气。场景插图才用 gpt-image。

用法：
    python3 diagrams.py --spec knowledge_points.example.json --out ./out/kp001/assets
    # 每个 diagram 声明生成一张 PNG：{seg_id}_{i}.png + manifest.json

也支持单张调试：
    python3 diagrams.py --demo triangle --out /tmp
"""
import argparse
import json
import os
import re

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# 中文字体：按可用性依次尝试
for _font in ["Noto Sans CJK SC", "WenQuanYi Micro Hei", "PingFang SC",
              "DejaVu Sans"]:
    try:
        plt.rcParams["font.sans-serif"] = [_font]
        plt.rcParams["axes.unicode_minus"] = False
        break
    except Exception:
        continue

FIGSIZE = (12.8, 7.2)  # 16:9，贴合 1920x1080 模板
DPI = 150


def number_line(params, path):
    """数轴：params={min, max, points:[{x,label}], highlight}"""
    fig, ax = plt.subplots(figsize=FIGSIZE)
    lo, hi = params.get("min", -5), params.get("max", 5)
    ax.set_xlim(lo - 0.5, hi + 0.5)
    ax.set_ylim(-1, 1)
    ax.axhline(0, color="black", lw=2)
    for x in range(lo, hi + 1):
        ax.plot([x, x], [0, -0.08], color="black", lw=1.5)
        ax.text(x, -0.25, str(x), ha="center", fontsize=18)
    for p in params.get("points", []):
        ax.plot(p["x"], 0, "o", ms=14,
                color="#2563eb" if p.get("hl") else "#111")
        ax.text(p["x"], 0.35, p.get("label", ""), ha="center",
                fontsize=20, color="#2563eb", weight="bold")
    ax.axis("off")
    fig.tight_layout()
    fig.savefig(path, dpi=DPI)
    plt.close(fig)


def coordinate(params, path):
    """坐标系函数图像：params={func:'x**2-2', x_range:[-3,3], points:[...]}"""
    import numpy as np
    fig, ax = plt.subplots(figsize=FIGSIZE)
    xs = np.linspace(*params.get("x_range", [-5, 5]), 400)
    f = eval(f"lambda x: {params['func']}", {"np": np})
    ax.plot(xs, f(xs), lw=3, color="#2563eb")
    ax.axhline(0, color="black", lw=1.2)
    ax.axvline(0, color="black", lw=1.2)
    ax.grid(alpha=0.25)
    for p in params.get("points", []):
        ax.plot(p["x"], p["y"], "o", ms=10, color="#dc2626")
        ax.text(p["x"], p["y"], f"  ({p['x']},{p['y']})", fontsize=16)
    ax.set_title(params.get("title", ""), fontsize=22)
    fig.tight_layout()
    fig.savefig(path, dpi=DPI)
    plt.close(fig)


def triangle(params, path):
    """标注三角形：params={vertices:{A:(0,0),B:(4,0),C:(1,3)}, labels, highlight}"""
    fig, ax = plt.subplots(figsize=FIGSIZE)
    v = params["vertices"]
    pts = [v[k] for k in "ABC"] + [v["A"]]
    xs, ys = zip(*pts)
    ax.plot(xs, ys, lw=3, color="#111")
    for name, (x, y) in v.items():
        ax.plot(x, y, "o", ms=8, color="#2563eb")
        ax.text(x + 0.12, y + 0.12, name, fontsize=22, weight="bold")
    for label in params.get("labels", []):
        ax.text(*label["at"], label["text"], fontsize=18,
                color="#dc2626", ha="center")
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title(params.get("title", ""), fontsize=22)
    fig.tight_layout()
    fig.savefig(path, dpi=DPI)
    plt.close(fig)


def bar(params, path):
    """条形统计图：params={categories:[], values:[], title}"""
    fig, ax = plt.subplots(figsize=FIGSIZE)
    cats, vals = params["categories"], params["values"]
    bars = ax.bar(cats, vals, color="#2563eb", edgecolor="#111")
    ax.bar_label(bars, fontsize=18)
    ax.set_title(params.get("title", ""), fontsize=22)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(path, dpi=DPI)
    plt.close(fig)


def equation_steps(params, path):
    """方程变形步骤图：params={steps:[...], highlight:行号}
    步骤用 mathtext 渲染，分式会显示为上下结构。"""
    fig, ax = plt.subplots(figsize=(12.8, 7.2))
    ax.axis("off")

    def mt(s):
        # 把 x/2 转成 \frac 形式，其余保持；已含 LaTeX 则直接用
        s = re.sub(r'([a-zA-Z0-9\)\]])/([a-zA-Z0-9\(\[])',
                   r'\\frac{\1}{\2}', s)
        s = s.replace('×', r'\times')
        return f"${s}$"

    for i, s in enumerate(params["steps"]):
        color = "#2563eb" if i == params.get("highlight") else "#111"
        weight = "bold" if i == params.get("highlight") else "normal"
        ax.text(0.5, 0.85 - i * 0.26, mt(s), fontsize=40, ha="center",
                color=color, weight=weight)
        if i and params.get("arrow", True):
            ax.annotate("", xy=(0.5, 0.85 - i * 0.26 - 0.03),
                        xytext=(0.5, 0.85 - i * 0.26 + 0.10),
                        arrowprops=dict(arrowstyle="->", color="#999",
                                        lw=2.5))
    fig.tight_layout()
    fig.savefig(path, dpi=DPI, facecolor="white")
    plt.close(fig)


TYPES = {"number_line": number_line, "coordinate": coordinate,
         "triangle": triangle, "bar": bar, "equation_steps": equation_steps}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", help="knowledge_points.json")
    ap.add_argument("--kp", default=None)
    ap.add_argument("--out", required=True)
    ap.add_argument("--demo", help="单张调试：diagram 类型名")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    manifest = []

    if args.demo:
        TYPES[args.demo]({}, os.path.join(args.out, f"{args.demo}.png"))
        print(f"demo → {args.out}/{args.demo}.png")
        return

    data = json.load(open(args.spec, encoding="utf-8"))
    for k in data["knowledge_points"]:
        if args.kp and k["id"] != args.kp:
            continue
        for seg in k["segments"]:
            for i, d in enumerate(seg.get("diagrams", [])):
                name = f"{k['id']}_{seg['id']}_{i}.png"
                path = os.path.join(args.out, name)
                TYPES[d["type"]](d.get("params", {}), path)
                manifest.append({"kp": k["id"], "seg": seg["id"],
                                 "file": name, "type": d["type"]})
                print(f"  {name}")
    json.dump(manifest, open(os.path.join(args.out, "manifest.json"), "w"),
              ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
