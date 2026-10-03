#!/usr/bin/env bash
# K12 批量生产编排：单个知识点的全流程。
# 用法：bash batch/batch_run.sh <knowledge_points.json> <kp_id> <out_dir>
# 整批：for kp in $(jq -r '.knowledge_points[].id' kp.json); do
#         bash batch/batch_run.sh kp.json $kp ./out || break
#       done
set -euo pipefail

KP_JSON="$1"; KP="$2"; OUT="$3"
PL="scripts/pipeline.sh"
export PATH="$HOME/workspace/ffmpeg9/bin:$PATH"

echo "=== [$KP] 1/7 知识库审核 ==="
python3 batch/review.py --kb ./kb --input "$KP_JSON" --kp "$KP"

echo "=== [$KP] 2/7 Gemini TTS 配音 ==="
python3 batch/tts_gemini.py --input "$KP_JSON" --kp "$KP" --out "$OUT"

echo "=== [$KP] 3/7 精确配图 ==="
python3 batch/diagrams.py --spec "$KP_JSON" --kp "$KP" --out "$OUT/$KP/assets"

echo "=== [$KP] 4/7 组装 brief ==="
python3 batch/assemble_brief.py --input "$KP_JSON" --kp "$KP" \
    --narration "$OUT/$KP" --assets "$OUT/$KP/assets" \
    --out "$OUT/$KP/brief.json"

TEMPLATE=$(python3 -c "import json;d=json.load(open('$KP_JSON'));k=next(x for x in d['knowledge_points'] if x['id']=='$KP');print(k.get('template') or d.get('default_template','01-B'))")
# 模板编号 → 包版本映射（见 references/template-catalog.md）
case "$TEMPLATE" in
  01-A) PACK="classic-performance@1.0.0" ;;
  01-B) PACK="continuous-performance@1.0.0" ;;
  01-C) PACK="stage-performance@1.0.0" ;;
  01-D) PACK="editorial-performance@1.0.0" ;;
  01-E) PACK="kinetic-performance@1.0.0" ;;
  02-A) PACK="paper-balance@1.0.0" ;;
  02-B) PACK="paper-ball-performance@1.0.0" ;;
  *) echo "未知模板 $TEMPLATE"; exit 1 ;;
esac

echo "=== [$KP] 5/7 macro-plan ($PACK) ==="
bash "$PL" macro-plan "$PACK" "$OUT/$KP/brief.json" "$OUT/$KP/plan"
READY=$(python3 -c "import json;print(json.load(open('$OUT/$KP/plan/report.json'))['ready'])")
if [ "$READY" != "True" ]; then
  echo "plan 未 ready，见 $OUT/$KP/plan/report.md，人工处理后重跑"
  exit 2
fi

echo "=== [$KP] 6/7 构建 + 渲染 ==="
bash "$PL" macro-build "$PACK" "$OUT/$KP/plan/spec.json" \
    "$OUT/$KP/narration.mp3" "$OUT/$KP/project"
bash "$PL" stills "$OUT/$KP/project" 0
bash "$PL" audio "$OUT/$KP/project"
bash "$PL" mix "$OUT/$KP/project"
bash "$PL" render "$OUT/$KP/project" "$OUT/$KP/${KP}_16x9_60fps.mp4"

echo "=== [$KP] 7/7 校验 ==="
bash "$PL" check "$OUT/$KP/${KP}_16x9_60fps.mp4"
echo "完成：$OUT/$KP/${KP}_16x9_60fps.mp4"
