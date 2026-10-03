# K12 学科批量生产管线（batch）

在 adu-motion-video 模板管线之上，加一层"一个知识点一条视频"的批量编排。
每个知识点走完：文案 → 知识库 AI 审核 → Gemini TTS 配音 → 配图 → brief.json →
macro-plan → macro-build → render → check。

## 目录

| 文件 | 作用 |
| --- | --- |
| `knowledge_points.schema.json` | 知识点输入格式说明 |
| `knowledge_points.example.json` | 示例：初中数学《一元一次方程——去分母》 |
| `math2speech.py` | 数学公式 → 口语中文预处理（TTS 前必跑） |
| `tts_gemini.py` | Gemini 3.8 Flash TTS 配音，逐句可控语速风格 |
| `diagrams.py` | matplotlib 精确配图（几何/坐标/数轴，标注 100% 准确） |
| `review.py` | 知识库 RAG 审核框架（事实/课标/术语/年级适宜性） |
| `review_prompts.md` | 四道审核的 prompt 模板 |
| `assemble_brief.py` | 组装 `adu-adaptation-brief/1` 标准的 brief.json |
| `batch_run.sh` | 批量编排脚本 |

## 数据流

```
knowledge_points.json
  → review.py            # 知识库审核，不通过则拦截
  → math2speech.py       # 公式转口语
  → tts_gemini.py        # 配音 → narration.mp3 (+ 分段时长)
  → diagrams.py          # 精确配图 → 素材目录
  → assemble_brief.py    # brief.json（文本/意图/分段/锚点）
  → pipeline.sh macro-plan → macro-build → stills/audio/mix → render → check
```

## 配图策略（重要）

- **精确图形**（几何、函数图像、数轴、带标注的图）：一律用 `diagrams.py`
  以代码生成，标注准确是教学红线，不能用生成式图像碰运气。
- **场景插图**（生活实例、概念示意）：可用 gpt-image 等生成，
  输出后仍建议人工抽检，放入素材目录即可，模板不挑来源。

## 前置条件

1. `GEMINI_API_KEY` 环境变量（[Google AI Studio](https://aistudio.google.com) 获取）。
   另见 `tts_gemini.py` 头部说明。密钥不要进仓库。
2. 知识库目录 `kb/`：放入教材 / 课标 / 教参的 md/txt，
   `review.py` 会建索引。教材改版时同步更新 kb。
3. 本仓库主流程已通过 `pipeline.sh doctor`（FFmpeg 9+、Chromium、音频对齐）。

## 快速开始

```bash
# 1. 审核文案
python3 batch/review.py --kb ./kb --input batch/knowledge_points.example.json

# 2. 配音（先 dry-run 看费用估算）
python3 batch/tts_gemini.py --input batch/knowledge_points.example.json \
    --out ./out/kp001 --dry-run

# 3. 配图
python3 batch/diagrams.py --spec batch/knowledge_points.example.json --out ./out/kp001/assets

# 4. 组装 brief 并进主流程
python3 batch/assemble_brief.py --input batch/knowledge_points.example.json \
    --narration ./out/kp001 --out ./out/kp001/brief.json
bash scripts/pipeline.sh macro-plan continuous-performance@1.0.0 \
    ./out/kp001/brief.json ./out/kp001/plan
```

整批跑：`bash batch/batch_run.sh knowledge_points.json ./out`。
