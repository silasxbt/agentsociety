#!/usr/bin/env zsh
# 一键构建论文 PDF（中英双语）。
# 流程：make_figures.py 刷新图表 → gen_paper_numbers.py 刷新数字宏 → 对每份主稿 xelatex → bibtex → xelatex ×2。
# 批次冻结后直接重跑本脚本，全文数字与草稿标记自动更新。
# 用法：tools/build_paper.sh [zh|en|all]（默认 all）
set -euo pipefail

EXP="$(cd "$(dirname "$0")/.." && pwd)"
PAPER="$EXP/paper"
TARGET="${1:-all}"

command -v xelatex >/dev/null || { echo "缺少 xelatex（需要 TeX Live）"; exit 1; }

echo "== 刷新图表 =="
# make_figures 需要仓库 venv 的 matplotlib；venv 缺失时警告但不中断（图表可能过期）
VENV_PY="$EXP/../../../.venv/bin/python"
if [[ -x "$VENV_PY" ]] && "$VENV_PY" -c 'import matplotlib' 2>/dev/null; then
  "$VENV_PY" "$EXP/tools/make_figures.py"
else
  echo "  ⚠ 未找到带 matplotlib 的 venv，跳过图表刷新（figures/ 可能与正文数字不同步）"
fi

echo "== 刷新 numbers.tex =="
python3 "$EXP/tools/gen_paper_numbers.py"

build_one() {
  local base="$1"
  [[ -f "$PAPER/$base.tex" ]] || { echo "跳过 $base（无 tex）"; return 0; }
  echo "== 编译 $base =="
  cd "$PAPER"
  xelatex -interaction=nonstopmode "$base.tex" >/dev/null || true
  bibtex "$base" >/dev/null || true
  xelatex -interaction=nonstopmode "$base.tex" >/dev/null || true
  # 最后一遍保留日志用于体检
  xelatex -interaction=nonstopmode "$base.tex" > "/tmp/$base.build.log" 2>&1 || true

  # 体检：硬错误 / 未定义引用 / 页数
  if grep -q "^!" "$base.log"; then
    echo "  ✗ $base 存在 LaTeX 错误："; grep "^!" "$base.log" | head -5; exit 1
  fi
  local undef
  undef=$(grep -c "Citation .* undefined" "$base.log" || true)
  [[ "$undef" == "0" ]] || { echo "  ✗ $base 有 $undef 个未定义引用"; exit 1; }
  local pages
  pages=$(grep -oE "\([0-9]+ pages" "$base.log" | grep -oE "[0-9]+" | tail -1)
  echo "  ✓ $base.pdf：${pages:-?} 页，引用完整"
}

case "$TARGET" in
  zh)  build_one main_zh ;;
  en)  build_one main_en ;;
  all) build_one main_zh; build_one main_en ;;
  *)   echo "用法：tools/build_paper.sh [zh|en|all]"; exit 1 ;;
esac

echo "== 完成 =="
ls -la "$PAPER"/main_*.pdf 2>/dev/null || true
