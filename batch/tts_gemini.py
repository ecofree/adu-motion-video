#!/usr/bin/env python3
"""Gemini 3.8 Flash TTS 配音：把每段口播文案转成语音。

模型：gemini-3.8-flash-tts（教学选它，支持逐句风格控制）
      gemini-3.8-flash-lite-tts（量大时更便宜，约 $0.54/小时）
费用：~$0.81/小时（2026-12-31 前），2027-01-01 起翻倍；batch 请求半价。
      一条 3 分钟视频约 $0.04。

前置：pip install 'google-genai>=2.25.0'；环境变量 GEMINI_API_KEY。
注意：httpx 旧版本解析 no_proxy 中的 [::1] 会报错，运行时建议
  env no_proxy='localhost,127.0.0.1,198.19.0.1' NO_PROXY='localhost,127.0.0.1,198.19.0.1'

用法：
    # 1. 费用估算
    python3 tts_gemini.py --input knowledge_points.example.json --dry-run

    # 2. 配音（--voice-name 选预置音色，默认 Kore，中文可用）
    python3 tts_gemini.py --input knowledge_points.example.json \\
        --voice-name Kore --out ./out/kp001 --kp kp001
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
    # 修复 httpx 解析 no_proxy 中 [::1] 崩溃的问题（保留代理本身）
    for k in ("no_proxy", "NO_PROXY"):
        v = os.environ.get(k, "")
        if "[" in v:
            os.environ[k] = ",".join(p for p in v.split(",") if "[" not in p)
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", help="knowledge_points.json")
    ap.add_argument("--kp", default=None, help="只处理该知识点 id")
    ap.add_argument("--out", required=False, default="./out")
    ap.add_argument("--voice-name", default="Kore",
                    help="预置音色名，如 Kore/Charon/Fenrir（30+ 可选）")
    ap.add_argument("--lite", action="store_true", help="用 flash-lite（更便宜）")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

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
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    model = MODEL_LITE if args.lite else MODEL

    for k in kps:
        outdir = os.path.join(args.out, k["id"])
        os.makedirs(outdir, exist_ok=True)
        durations, parts = {}, []
        for seg in k["segments"]:
            mp3 = os.path.join(outdir, f"seg_{seg['id']}.mp3")
            synthesize(client, types, model, seg["script"],
                       args.voice_name, mp3)
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


def synthesize(client, types, model, text, voice_name, out_mp3):
    """用 generate_content + AUDIO modality 配音（实测可用的稳定路径）。"""
    resp = client.models.generate_content(
        model=model,
        contents=text,
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=voice_name))),
        ),
    )
    data = resp.candidates[0].content.parts[0].inline_data.data
    with open(out_mp3, "wb") as f:
        f.write(data)


def probe_duration(mp3: str) -> float:
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", mp3], text=True)
    return float(out.strip())


def concat_mp3(parts: list, out: str):
    with open("/tmp/_concat.txt", "w") as f:
        for p in parts:
            f.write(f"file '{os.path.abspath(p)}'\n")
    # 不用 -c copy：不同请求的 MP3 编码参数可能有细微差异，重编码最稳
    subprocess.check_call(
        ["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
         "-i", "/tmp/_concat.txt", "-c:a", "libmp3lame", "-b:a", "128k",
         out])


if __name__ == "__main__":
    main()
