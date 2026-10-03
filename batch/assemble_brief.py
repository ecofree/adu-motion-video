#!/usr/bin/env python3
"""把知识点清单组装成 macro-plan 可用的 brief.json。

编号遵循仓库 references/template-catalog.md：
  01-B · 连续形变 → continuous-performance@1.0.0

适配约束（来自 scripts/adaptation.py 实测）：
- 每个 brief segment 独立匹配一个场景；场景原子不可拆。
- segment 意图/阶段/数量必须满足场景合约；时长必须落在
  [场景最小时长, 场景时长+360帧] 内。
- claim-into-container：intent=claim-method-proof-response，
  phases=claim→method→distribution→proof→response，
  counts={parts:3, receivers:3}，时长窗口 [835,1288]帧。
- 槽位通过 segment.inputs 填充（见 manifest 的 inputPath）。

模板 01-B 把 65 秒口播切成 4 个 ~14-19 秒的块，每块复用
claim-into-container 编舞，配不同的文字槽位。文案经 math2speech
转口语后写入 brief 与 SRT。

用法：
    python3 assemble_brief.py --input knowledge_points.example.json --kp kp001 \\
        --narration /tmp/k12-out/kp001 --out /tmp/k12-out/kp001/brief.json
"""
import argparse
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from math2speech import to_speech as speak

FPS = 60

# 音频块：(块id, 起止秒, 文案段id列表, 静音垫尾秒)
# 由 TTS 实际时长 + 句子边界定（见 transcript.srt）
CHUNKS = [
    ("seg0", 0.00, 17.91, ["why", "method"], 0.0),
    ("seg1", 17.91, 36.64, ["method"], 0.0),
    ("seg2", 36.64, 54.24, ["pitfall"], 0.0),
    ("seg3", 54.24, 65.12, ["close"], 3.5),
]

# 每块的导演标注：锚点 at=块内秒。
# 约束（adapt_project.py motion window 逻辑）：
# - container 必须落在 4.65s 处（±1帧），对齐源编舞 action-01；
# - proof、response 只需保持 container < proof < response 的顺序且在块内。
# 每块的导演标注：锚点 at=块内秒。
# 时序约束（adapt_project.py motion window 逻辑，反推自源编舞）：
# - container 必须落在 4.65s（279帧，±1帧），对齐源编舞 action-01；
# - proof→response 必须相隔 238帧（3.97s），对齐 action-02；
# - proof 只需满足 container < proof < response 且 response 在块内。
# 槽位字数上限见 packs/continuous-performance/1.0.0/manifest.json。
BLOCKS = [
    {
        "anchors": {"container": {"at": 4.65},
                    "proof": {"at": 11.5},
                    "response": {"at": 15.47}},
        "inputs": {
            "chapter": "一元一次方程", "label": "去分母",
            "claim": {"line1": "解带分母",
                      "line2": "先去分母",
                      "context": "不是通分而是去分母"},
            "parts": ["分母2", "分母3", "公倍数"],
            "receivers": ["x/2", "x/3", "5"],
            "container": {"heading": "去分母", "source": "人教版七上3.3",
                          "name": "x/2+x/3=5",
                          "contents": "两边同乘最小公倍数", "mark": "第一步"},
            "proof": {"heading": "目标",
                      "context": "方程不再出现分母",
                      "label": "化繁为简"},
            "response": {"context": "去分母后", "setup": "整式方程",
                         "impact": "计算更直接", "resolve": "分母消失"},
            "presenterLabel": "数学讲解",
        },
    },
    {
        "anchors": {"container": {"at": 4.65},
                    "proof": {"at": 12.0},
                    "response": {"at": 15.97}},
        "inputs": {
            "chapter": "一元一次方程", "label": "方法",
            "claim": {"line1": "两边同乘",
                      "line2": "公倍数6",
                      "context": "分母是2和3"},
            "parts": ["×6", "3x", "2x"],
            "receivers": ["项x/2", "项x/3", "项5"],
            "container": {"heading": "去分母", "source": "人教版七上3.3",
                          "name": "x/2+x/3=5",
                          "contents": "两边同乘6", "mark": "×6"},
            "proof": {"heading": "等式性质2",
                      "context": "两边乘同数等式成立",
                      "label": "依据"},
            "response": {"context": "去分母完成", "setup": "3x+2x=30",
                         "impact": "分母消失", "resolve": "得整式方程"},
            "presenterLabel": "数学讲解",
        },
    },
    {
        "anchors": {"container": {"at": 4.65},
                    "proof": {"at": 10.0},
                    "response": {"at": 13.97}},
        "inputs": {
            "chapter": "一元一次方程", "label": "避坑",
            "claim": {"line1": "最易错",
                      "line2": "有两处",
                      "context": "去分母避坑指南"},
            "parts": ["漏乘", "括号", "口诀"],
            "receivers": ["常数项", "分子", "你"],
            "container": {"heading": "常见错误", "source": "人教版七上3.3",
                          "name": "去分母两大坑",
                          "contents": "漏乘/忘加括号", "mark": "注意"},
            "proof": {"heading": "正确做法",
                      "context": "常数项也乘加括号",
                      "label": "纠正"},
            "response": {"context": "记住", "setup": "3(x+1)",
                         "impact": "避免失分", "resolve": "两处都避开"},
            "presenterLabel": "数学讲解",
        },
    },
    {
        # 最短块：proof 须 ≥8.03s（否则 action-02 前移与 action-01 重叠）
        "anchors": {"container": {"at": 4.65},
                    "proof": {"at": 8.5},
                    "response": {"at": 12.47}},
        "inputs": {
            "chapter": "一元一次方程", "label": "口诀",
            "claim": {"line1": "记住口诀",
                      "line2": "四步法",
                      "context": "去分母总结"},
            "parts": ["找公倍", "两边乘", "不漏乘"],
            "receivers": ["方法", "易错点", "下一讲"],
            "container": {"heading": "口诀", "source": "人教版七上3.3",
                          "name": "去分母口诀",
                          "contents": "找最小公倍数，两边同乘，不漏乘",
                          "mark": "背下来"},
            "proof": {"heading": "检验",
                      "context": "不漏乘加括号",
                      "label": "自查"},
            "response": {"context": "本讲结束", "setup": "下讲见",
                         "impact": "持续进步", "resolve": "练含括号去分母"},
            "presenterLabel": "数学讲解",
        },
    },
]

INTENT = "claim-method-proof-response"
PHASES = ["claim", "method", "distribution", "proof", "response"]
COUNTS = {"parts": 3, "receivers": 3}


def sh(cmd):
    subprocess.check_call(cmd)


def build_chunk_audio(narr_dir, seg_id, start, end, pad_silence):
    """从 seg_<id>.mp3 按绝对时间切出 [start, end)，必要时垫静音。"""
    out = os.path.join(narr_dir, f"{seg_id}.mp3")
    # 收集落在 [start, end) 内的源片段
    pieces, t = [], start
    for sid in ("why", "method", "pitfall", "close"):
        src = os.path.join(narr_dir, f"seg_{sid}.mp3")
        dur = float(subprocess.check_output(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", src], text=True).strip())
        # 该源文件在绝对时间轴上的区间
        s0 = {"why": 0.0, "method": 13.52,
              "pitfall": 36.64, "close": 54.24}[sid]
        s1 = s0 + dur
        a, b = max(start, s0), min(end, s1)
        if b > a + 0.01:
            piece = f"/tmp/_chunk_{seg_id}_{sid}.mp3"
            sh(["ffmpeg", "-y", "-v", "error", "-ss", f"{a - s0:.2f}",
                "-t", f"{b - a:.2f}", "-i", src,
                "-c:a", "libmp3lame", "-b:a", "128k", piece])
            pieces.append(piece)
    with open("/tmp/_chunk_concat.txt", "w") as f:
        for p in pieces:
            f.write(f"file '{p}'\n")
    if pad_silence > 0:
        sh(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
            "-i", "/tmp/_chunk_concat.txt",
            "-f", "lavfi", "-i",
            f"anullsrc=r=44100:cl=stereo:d={pad_silence}",
            "-filter_complex", "[0:a][1:a]concat=n=2:v=0:a=1",
            "-c:a", "libmp3lame", "-b:a", "128k", out])
    else:
        sh(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
            "-i", "/tmp/_chunk_concat.txt",
            "-c:a", "libmp3lame", "-b:a", "128k", out])
    return out


def write_srt(path, chunks_spoken):
    """chunks_spoken: [(start, end, spoken_text)]，按句子分句写 SRT。"""
    cues = []
    for start, end, text in chunks_spoken:
        sents = [s for s in re.split(r"(?<=[。！？])", text) if s.strip()]
        total = sum(len(s) for s in sents) or 1
        t = start
        for s in sents:
            d = (end - start) * len(s) / total
            cues.append((t, t + d, s.strip()))
            t += d

    def ts(x):
        h, m = int(x // 3600), int(x % 3600 // 60)
        s, ms = int(x % 60), int(round(x % 1 * 1000))
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    with open(path, "w", encoding="utf-8") as f:
        for i, (a, b, txt) in enumerate(cues, 1):
            f.write(f"{i}\n{ts(a)} --> {ts(b)}\n{txt}\n\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--kp", required=True)
    ap.add_argument("--narration", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--title", default="")
    args = ap.parse_args()

    data = json.load(open(args.input, encoding="utf-8"))
    kp = next(k for k in data["knowledge_points"] if k["id"] == args.kp)
    spoken = {s["id"]: speak(s["script"]) for s in kp["segments"]}

    out_dir = os.path.dirname(os.path.abspath(args.out))
    segments, chunks_spoken = [], []
    for (seg_id, start, end, seg_ids, pad), blk in zip(CHUNKS, BLOCKS):
        dur_s = (end - start) + pad
        frames = int(round(dur_s * FPS))
        if not 835 <= frames <= 1288:
            sys.exit(f"{seg_id} {dur_s:.1f}s（{frames}帧）超出 [835,1288]")
        audio = build_chunk_audio(args.narration, seg_id, start, end, pad)
        text = "".join(spoken[sid] for sid in seg_ids)
        chunks_spoken.append((start, end + pad, text))
        segments.append({
            "id": seg_id,
            "text": text,
            "intent": INTENT,
            "phases": PHASES,
            "durationFrames": frames,
            "counts": COUNTS,
            "anchors": blk["anchors"],
            "energy": 2,
            "candidates": {
                "claim-into-container": {"inputs": blk["inputs"]},
            },
            "preferredScenes": ["claim-into-container"],
            "audio": audio,
        })

    srt_path = os.path.join(out_dir, "transcript.srt")
    write_srt(srt_path, chunks_spoken)

    total_s = sum(s["durationFrames"] for s in segments) / FPS
    brief = {
        "schema": "adu-adaptation-brief/1",
        "title": args.title or kp["title"],
        "brand": "K12数学 · 初中",
        "fps": FPS,
        # Linux 无 macOS Vision 自动人脸追踪；K12 样片用固定裁剪
        "faceTracking": {"mode": "fixed", "cx": 0.5, "cy": 0.4, "h": 0.6},
        # 源包用 macOS SFM 等宽字体；Linux 用 Noto Sans Mono CJK SC 替代
        # （从系统 TTC 提取的 .otf，放在 brief 同级目录；build 时相对 spec.json 解析）
        "monoFontFile": "../NotoSansMonoCJKsc-Regular.otf",
        "segments": segments,
        "transcript": srt_path,
        "narrationDuration": round(total_s, 2),
        "knowledge_point": {"id": kp["id"],
                            "curriculum_ref": kp.get("curriculum_ref", "")},
    }
    json.dump(brief, open(args.out, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"brief.json → {args.out}（{len(segments)} 段，共 {total_s:.1f}s）")


if __name__ == "__main__":
    main()
