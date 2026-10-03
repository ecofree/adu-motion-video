# 审核 prompt 模板（review.py 调用）

四道审核按顺序跑，前一道不通过直接拦截。`{kb_context}` 是从知识库检索到的
相关片段，`{script}` 是待审口播文案，`{key_terms}` 是关键术语表。

---

## R1 · 事实准确性

```
你是初中数学教研审核员。只依据下面判断文案是否有事实错误，
不要用你自己的知识脑补超出依据的结论。


{kb_context}


{script}

逐句检查，输出 JSON：
{"passed": true/false, "issues": [{"quote": "原文", "problem": "问题描述", "fix": "修改建议"}]}
```

## R2 · 课标对齐

```
你是课程标准审核员。判断文案是否超出本年级，
或遗漏了课标要求必须讲清的要点。


{kb_context}


{script}
{grade}

输出 JSON：{"passed": true/false, "issues": [...]}
超纲内容标 severity=warning（可讲但要注明拓展），缺失要点标 severity=error。
```

## R3 · 术语与表述规范

```
你是教学语言规范审核员。检查：
1. 关键术语是否准确（{key_terms}），如"除"与"除以"、"数"与"数字"不可混用；
2. 数学表述是否严谨（"增大"vs"增加"、"至少"vs"至多"）；
3. 有无歧义句。

输出 JSON：{"passed": true/false, "issues": [{"quote":..., "problem":..., "fix":...}]}
```

## R4 · 年级认知适宜性

```
你是 {grade} 学情专家。判断文案的抽象程度、用词、例子是否适合该年级
学生的认知水平；新概念是否有铺垫，例子是否贴近生活。

输出 JSON：{"passed": true/false, "issues": [...]}
```
