#!/usr/bin/env python3
"""知识库 RAG 审核：文案进配音/渲染前的质量门。

四道关：R1 事实准确性 → R2 课标对齐 → R3 术语规范 → R4 年级适宜性。
prompt 见 review_prompts.md。任一道 error 级问题即拦截，需人工处理后重审。

知识库：kb/ 目录下放教材/课标/教参的 md/txt。首次运行建索引
（默认 TF-IDF 本地索引；量大时可换向量库，接口已留出）。

用法：
python3 review.py --kb./kb --input knowledge_points.example.json --kp kp001
python3 review.py --kb./kb --input knowledge_points.json --all --report./out/review.json

环境变量 REVIEW_MODEL：审核用模型（默认 gemini-2.5-flash，审核用快模型即可）。
需要 GEMINI_API_KEY。
"""
import argparse
import json
import math
import os
import re
import sys
from collections import Counter

PROMPTS = ["R1", "R2", "R3", "R4"]


# ---------- 极简本地检索（TF-IDF），kb 量大时替换为向量检索 ----------
def tokenize(t):
return re.findall(r'[\u4e00-\u9fff]+|[a-zA-Z0-9]+', t.lower())


class KbIndex:
def __init__(self, kb_dir):
self.docs = []
for root, _, files in os.walk(kb_dir):
for f in files:
if f.endswith((".md", ".txt")):
p = os.path.join(root, f)
text = open(p, encoding="utf-8").read()
# 按段落切分
for para in re.split(r'\n\s*\n', text):
para = para.strip()
if len(para) > 40:
self.docs.append({"file": f, "text": para})
df = Counter()
for d in self.docs:
for t in set(tokenize(d["text"])):
df[t] += 1
self.idf = {t: math.log(len(self.docs) / (1 + c))
for t, c in df.items()}

def search(self, query, top_k=4):
q = Counter(tokenize(query))
scored = []
for d in self.docs:
dt = Counter(tokenize(d["text"]))
s = sum(q[t] * dt[t] * self.idf.get(t, 0) for t in q)
if s:
scored.append((s, d))
scored.sort(reverse=True, key=lambda x: x[0])
return [d for _, d in scored[:top_k]]


PROMPT_TPL = {
"R1": ("你是初中数学教研审核员。只依据判断文案是否有事实错误。\n"
"\n{ctx}\n\n{script}\n"
"输出 JSON：{{\"passed\": true/false, \"issues\": [{{\"quote\":..., \"problem\":..., \"fix\":...}}]}}"),
"R2": ("你是课标审核员。判断文案是否超出或遗漏要点。\n"
"\n{ctx}\n\n{script}\n{grade}\n"
"输出 JSON，同上；超纲标 severity=warning，缺失标 severity=error。"),
"R3": ("你是教学语言审核员。检查关键术语{terms}是否准确、表述是否严谨、有无歧义。\n"
"\n{script}\n输出 JSON，同上。"),
"R4": ("你是{grade}学情专家。判断抽象程度、用词、例子是否适合该年级认知水平。\n"
"\n{script}\n输出 JSON，同上。"),
}


def judge(model, prompt):
"""调模型做判断，返回 parsed JSON。模型可换，接口保持一致。"""
# 预留：当前用 Gemini；要换 OpenAI/Claude 只需改这里
from google import genai
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
resp = client.models.generate_content(
model=model, contents=prompt,
config={"response_mime_type": "application/json"})
return json.loads(resp.text)


def review_kp(kp, grade, kb: KbIndex, model):
full_script = "\n".join(s["script"] for s in kp["segments"])
terms = ", ".join(kp.get("key_terms", []))
report = {"kp": kp["id"], "title": kp["title"], "rounds": {},
"passed": True}
for r in PROMPTS:
ctx = ""
if r in ("R1", "R2"):
hits = kb.search(full_script + " " + terms)
ctx = "\n---\n".join(
f"[{h['file']}] {h['text'][:600]}" for h in hits)
prompt = PROMPT_TPL[r].format(
ctx=ctx, script=full_script, grade=grade, terms=terms)
try:
res = judge(model, prompt)
except Exception as e:
res = {"passed": False,
"issues": [{"problem": f"审核调用失败: {e}"}]}
report["rounds"][r] = res
errs = [i for i in res.get("issues", [])
if i.get("severity", "error") == "error"]
if not res.get("passed") and errs:
report["passed"] = False
report["blocked_at"] = r
break # error 级拦截，后续轮次不再跑
return report


def main():
ap = argparse.ArgumentParser()
ap.add_argument("--kb", required=True)
ap.add_argument("--input", required=True)
ap.add_argument("--kp", default=None)
ap.add_argument("--all", action="store_true")
ap.add_argument("--report", default=None)
args = ap.parse_args()

data = json.load(open(args.input, encoding="utf-8"))
kb = KbIndex(args.kb)
print(f"知识库：{len(kb.docs)} 个段落")
model = os.environ.get("REVIEW_MODEL", "gemini-2.5-flash")

kps = [k for k in data["knowledge_points"]
if args.all or k["id"] == (args.kp or k["id"])]
reports = [review_kp(k, data.get("grade", ""), kb, model) for k in kps]

failed = [r for r in reports if not r["passed"]]
for r in reports:
flag = "通过" if r["passed"] else f"拦截@{r.get('blocked_at')}"
print(f"{r['kp']} {r['title']}: {flag}")
for rnd, res in r["rounds"].items():
for i in res.get("issues", []):
print(f" [{rnd}] {i.get('quote','')[:30]} → {i.get('problem','')}")
if args.report:
json.dump(reports, open(args.report, "w"), ensure_ascii=False, indent=2)
sys.exit(1 if failed else 0)


if __name__ == "__main__":
main()
