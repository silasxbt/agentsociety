#!/bin/zsh
# AISS 2026 提交打包（SUBMISSION.md 第三节步骤 5 的固化）
# 用法：tools/make_submission.sh  →  tmp/submission_aiss2026_<日期>.zip
# 前置：冻结四命令已跑完（compare_conditions / cost_report / build_paper / collect_evidence）
set -euo pipefail
cd "$(dirname "$0")/.."

STAMP=$(date +%Y%m%d)
OUT="tmp/submission_aiss2026_${STAMP}.zip"
STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT

# 1) 冻结状态检查：numbers.tex 不得仍是"未冻结"
if grep -q "未冻结" paper/numbers.tex 2>/dev/null; then
  echo "✗ paper/numbers.tex 仍为未冻结状态——先跑完 12 有效 run 并执行冻结四命令" >&2
  exit 1
fi

# 2) 组装
mkdir -p "$STAGE/paper" "$STAGE/figures" "$STAGE/tools" "$STAGE/tests" "$STAGE/data_pipeline/out"
cp paper/main_zh.pdf paper/main_en.pdf paper/main_zh.tex paper/main_en.tex \
   paper/refs.bib paper/numbers.tex paper/SUBMISSION.md "$STAGE/paper/"
cp figures/*.png figures/*.csv "$STAGE/figures/" 2>/dev/null || true
cp EVIDENCE.md README.md run_batch.sh "$STAGE/"
cp tools/compare_conditions.py tools/make_figures.py tools/gen_paper_numbers.py \
   tools/collect_evidence.py tools/cost_report.py tools/harness_loop.py \
   tools/extract_cases.py "$STAGE/tools/" 2>/dev/null || true
cp tests/scan_timing.py tests/scan_timing_result.json tests/harness_loop_log.jsonl \
   tests/cost_report.json tests/silence_diagnosis.json "$STAGE/tests/" 2>/dev/null || true
cp data_pipeline/out/calibration_targets.md data_pipeline/out/references_verified.md \
   "$STAGE/data_pipeline/out/" 2>/dev/null || true
cp tmp/batch/comparison.json "$STAGE/" 2>/dev/null || true

# 3) 密钥红线：打包内容 grep 扫描（sk- 密钥 / .env / token）
# 排除用法注释里的占位符（dummy / ... / sk-xxx / \$VAR），只拦真实密钥形态
if grep -rEl "sk-[A-Za-z0-9_-]{16,}|AGENTSOCIETY_LLM_API_KEY=[^ \"'\$]{12,}" "$STAGE" 2>/dev/null | grep -v SUBMISSION.md; then
  echo "✗ 发现疑似密钥,终止打包（见上方文件列表）" >&2
  exit 1
fi
if find "$STAGE" -name ".env*" | grep -q .; then
  echo "✗ 发现 .env 文件,终止打包" >&2
  exit 1
fi

# 4) 压缩
rm -f "$OUT"
(cd "$STAGE" && zip -rq - .) > "$OUT"
echo "✓ 已生成 ${OUT}（$(du -h "$OUT" | cut -f1)）"
unzip -l "$OUT" | tail -3
