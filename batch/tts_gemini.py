#!/usr/bin/env python3
"""Gemini 3.8 Flash TTS 配音：把每段口播文案转成语音。

模型：gemini-3.8-flash-tts（教学选它，支持逐句风格控制）
      gemini-3.8-flash-lite-tts（量大时更便宜，约 $0.54/小时）
费用：~$0.81/小时（2026-12-31 前），2027-01-01 起翻倍；batch 请求半价。
      一条 3 分钟视频约 $0.04。

前置：pip install 'google-genai>=2.25.0'；环境变量 GEMINI_API_KEY。

用法：
    # 1. 设计音色（一次，保存 voice_id 复用）
    python3 tts_gemini.py --design-voice "耐心、语速稍慢的初中数学老师" --save voice.json

    # 2. 费用估算
    python3 tts_gemini.py --input knowledge_points.example.json --dry-run

    # 3. 配音
    python3 tts_gemini.py --input knowledge_points.example.json --voice voice.json \\
        --out ./out/kp001 --kp kp001
    # 输出：seg_why.mp3 ... + narration.mp3 + durations.json（每段时长，供 assemble_brief 用）

注意：文案先过 math2speech.py；数字/公式写成口语（"x 的平方"而非 "x^2"）。
"""
import argparse
import json
import os
import subprocess
import sys

MODEL = "gemini-3.8-flash-tts"
MODEL_LITE = "gemini-3.8-flash-lite-tts"
# 音频按 25 token/秒计费
TOKENS_PER_SEC = 25
PRICE_PER_M_TOKENS = 9.0  # flash；lite 为 6.0；2027-01-01 起翻倍


def estimate_cost(chars: int, lite: bool = False) -> dict:
    # 中文约 1 字 ≈ 1.5 token；语速约 4 字/秒（教学慢速）
    secs = chars / 4.0
    tokens = secs * TOKENS_PER_SEC
    price = (6.0 if lite else PRICE_PER_M_TOKENS) / 1e6
    return {"chars": chars, "seconds": round(secs, 1),
            "usd": round(tokens * price, 4)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", help="knowledge_points.json")
    ap.add_argument("--kp", default=None, help="只处理该知识点 id")
    ap.add_argument("--out", required=False, default="./out")
    ap.add_argument("--voice", help="design-voice 保存的 voice.json")
    ap.add_argument("--design-voice", help="用文字描述设计音色并保存")
    ap.add_argument("--save", default="voice.json")
    ap.add_argument("--lite", action="store_true", help="用 flash-lite（更便宜）")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.design_voice:
        design_voice(args.design_voice, args.save,
                     MODEL_LITE if args.lite else MODEL)
        return

    data = json.load(open(args.input, encoding="utf-8"))
    kps = [k for k in data["knowledge_points"]
           if args.kp is None or k["id"] == args.kp]
    if args.dry_run:
        total = 0
        for k in kps:
            chars = sum(len(s["script"]) for s in k["segments"])
            c = estimate_cost(chars, args.lite)
            total += c["usd"]
            print(f"{k['id']} {k['title']}: {c['chars']}字 ≈ {c['seconds']}s ≈ ${c['usd']}")
        print(f"合计 ≈ ${round(total, 4)}（batch 请求可再半价）")
        return

    if "GEMINI_API_KEY" not in os.environ:
        sys.exit("缺少 GEMINI_API_KEY，可从 https://aistudio.google.com 获取")
    voice_id = json.load(open(args.voice, encoding="utf-8"))["voice_id"] \
        if args.voice else None
    try:
        from google import genai
    except ImportError:
        sys.exit("pip install 'google-genai>=2.25.0'")
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    model = MODEL_LITE if args.lite else MODEL

    for k in kps:
        outdir = os.path.join(args.out, k["id"])
        os.makedirs(outdir, exist_ok=True)
        durations, parts = {}, []
        for seg in k["segments"]:
            style = seg.get("style") or data.get("voice_style", "")
            mp3 = os.path.join(outdir, f"seg_{seg['id']}.mp3")
            synthesize(client, model, seg["script"], style, voice_id, mp3)
            dur = probe_duration(mp3)
            durations[seg["id"]] = dur
            parts.append(mp3)
            print(f"  {seg['id']}: {dur:.1f}s")
        # 拼接整条口播
        concat_mp3(parts, os.path.join(outdir, "narration.mp3"))
        json.dump(durations,
                  open(os.path.join(outdir, "durations.json"), "w"),
                  ensure_ascii=False, indent=2)
        print(f"{k['id']} 配音完成 → {outdir}/narration.mp3")


def design_voice(desc: str, save: str, model: str):
    from google import genai
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    v = client.voices.create(
        store=True,
        voice={"model": model, "type": "prompted",
               "display_name": desc[:40],
               "prompted": {"input": desc}},
    )
    json.dump({"voice_id": v.id, "description": desc},
              open(save, "w"), ensure_ascii=False, indent=2)
    print(f"音色已保存 → {save}（voice_id={v.id}，后续复用不再重复设计）")


def synthesize(client, model, text, style, voice_id, out_mp3):
    req = {
        "model": model,
        "input": [{"type": "user_input", "content": [{
            "type": "text", "text": text,
            "annotations": [{"type": "speech_metadata", "style": style}],
        }]}],
        "response_format": {"type": "audio"},
    }
    if voice_id:
        req["generation_config"] = {"speech_config": [{"voice": voice_id}]}
    interaction = client.interactions.create(**req)
    audio = interaction.output[0].audio  # bytes
    open(out_mp3, "wb").write(audio)


def probe_duration(mp3: str) -> float:
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", mp3], text=True)
    return float(out.strip())


def concat_mp3(parts: list, out: str):
    with open("/tmp/_concat.txt", "w") as f:
        f.writelines(f"file '{p}'\n" for p in parts)
    subprocess.check_call(
        ["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
         "-i", "/tmp/_concat.txt", "-c", "copy", out])


if __name__ == "__main__":
    main()
