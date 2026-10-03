#!/usr/bin/env python3
"""组装 brief.json（adu-adaptation-brief/1），喂给 macro-plan。

输入：
  --input  knowledge_points.json（文案已过 review.py，且 math2speech 已处理）
  --kp     知识点 id
  --narration  tts_gemini.py 的输出目录（含 durations.json）
  --assets     diagrams.py 的输出目录（含 manifest.json）
  --out    输出 brief.json 路径

分段时长：用真实配音时长（durations.json）换算成帧数；
意图/锚点/数量槽位按文案结构填充，关键词时码在配音对齐后回填。
"""
import argparse
import json
import os

from math2speech import to_speech  # 同目录


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--kp", required=True)
    ap.add_argument("--narration", required=True)
    ap.add_argument("--assets", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--fps", type=int, default=60)
    args = ap.parse_args()

    data = json.load(open(args.input, encoding="utf-8"))
    kp = next(k for k in data["knowledge_points"] if k["id"] == args.kp)
    durations = json.load(open(os.path.join(args.narration, "durations.json"),
                               encoding="utf-8"))
    manifest = json.load(open(os.path.join(args.assets, "manifest.json"),
                              encoding="utf-8"))
    by_seg = {}
    for m in manifest:
        by_seg.setdefault(m["seg"], []).append(m["file"])

    segments = []
    for seg in kp["segments"]:
        dur = durations.get(seg["id"])
        if dur is None:
            raise SystemExit(f"缺少配音时长：{seg['id']}，先跑 tts_gemini.py")
        segments.append({
            "id": seg["id"],
            "text": to_speech(seg["script"]),
            "intent": seg["intent"],
            "phases": ["open", "develop", "close"],
            "durationFrames": int(dur * args.fps),
            "counts": {"objects": len(by_seg.get(seg["id"], []))},
            "anchors": {"media": by_seg.get(seg["id"], []),
                        "keywords": []},  # 关键词时码：对齐后回填
            "candidates": {},
        })

    brief = {
        "schema": "adu-adaptation-brief/1",
        "fps": args.fps,
        "brand": data.get("series", ""),
        "description": f"{kp['title']}（{kp.get('curriculum_ref','')}）",
        "template": kp.get("template") or data.get("default_template", "01-B"),
        "narration": os.path.abspath(os.path.join(args.narration,
                                                  "narration.mp3")),
        "segments": segments,
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    json.dump(brief, open(args.out, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    total = sum(s["durationFrames"] for s in segments) / args.fps
    print(f"brief.json → {args.out}（{len(segments)} 段，共 {total:.1f}s）")


if __name__ == "__main__":
    main()
