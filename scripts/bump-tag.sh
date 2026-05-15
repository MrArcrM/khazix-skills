#!/usr/bin/env bash
# bump-tag.sh — 按 scope 自动算下一个 semver tag 并打 + 推
#
# 用法：
#   ./scripts/bump-tag.sh <scope> <patch|minor|major> [-m "message"]
#
# 例：
#   ./scripts/bump-tag.sh aihot patch                 # aihot-v0.2.3 → aihot-v0.2.4
#   ./scripts/bump-tag.sh aihot minor                 # aihot-v0.2.3 → aihot-v0.3.0
#   ./scripts/bump-tag.sh neat-freak major -m "..."   # neat-freak-v1.0.2 → neat-freak-v2.0.0
#
# 规则：
# - tag 命名约定：<scope>-v<MAJOR>.<MINOR>.<PATCH>
# - patch：bug fix / 文档调整 / 行为无变化
# - minor：新功能 / 新子命令 / 新主题（向后兼容）
# - major：breaking change（改 chat_id 到 prod 群、API 契约改、删功能等）
# - 打在当前 HEAD（main）；不在 main 上时退出
# - 同 tag 已存在则退出，不覆盖

set -euo pipefail

SCOPE="${1:-}"
BUMP="${2:-}"
MSG=""

# 解析 -m "..."
if [[ "${3:-}" == "-m" && -n "${4:-}" ]]; then
  MSG="$4"
fi

if [[ -z "$SCOPE" || -z "$BUMP" ]]; then
  echo "用法: $0 <scope> <patch|minor|major> [-m \"message\"]" >&2
  echo "现有 scope:" >&2
  git tag -l | sed 's/-v[0-9.]*$//' | sort -u | sed 's/^/  /' >&2
  exit 1
fi

case "$BUMP" in
  patch|minor|major) ;;
  *) echo "❌ bump 必须是 patch / minor / major，不是 '$BUMP'" >&2; exit 1 ;;
esac

# 必须在 main 上
BRANCH=$(git symbolic-ref --short HEAD)
if [[ "$BRANCH" != "main" ]]; then
  echo "❌ 当前分支 $BRANCH，tag 只在 main 上打。先 git checkout main 再试" >&2
  exit 1
fi

# 工作区必须干净
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "❌ 工作区有未提交改动，先 commit / stash 再打 tag" >&2
  exit 1
fi

# 找最新 tag
LATEST=$(git tag -l "${SCOPE}-v*" | sort -V | tail -n1)
if [[ -z "$LATEST" ]]; then
  echo "ℹ️  ${SCOPE} 还没有 tag，从 v0.1.0 开始" >&2
  NEW="${SCOPE}-v0.1.0"
else
  # 解析 x.y.z
  VER=${LATEST#${SCOPE}-v}
  IFS='.' read -r MAJOR MINOR PATCH <<< "$VER"

  case "$BUMP" in
    patch) PATCH=$((PATCH+1)) ;;
    minor) MINOR=$((MINOR+1)); PATCH=0 ;;
    major) MAJOR=$((MAJOR+1)); MINOR=0; PATCH=0 ;;
  esac

  NEW="${SCOPE}-v${MAJOR}.${MINOR}.${PATCH}"
fi

# 同名 tag 已存在则退出
if git rev-parse "$NEW" >/dev/null 2>&1; then
  echo "❌ tag $NEW 已存在" >&2
  exit 1
fi

# 默认 message：用最近一次跟该 scope 相关的 commit subject
if [[ -z "$MSG" ]]; then
  MSG=$(git log -1 --pretty=format:"%s" -- "${SCOPE}/" 2>/dev/null || true)
  if [[ -z "$MSG" ]]; then
    MSG="${SCOPE} ${BUMP} release"
  fi
fi

HEAD=$(git rev-parse --short HEAD)
echo "→ 在 $HEAD 上打 tag $NEW"
echo "  bump:  ${LATEST:-<none>} → $NEW ($BUMP)"
echo "  msg:   $MSG"
echo

read -r -p "确认? [y/N] " ans
if [[ "$ans" != "y" && "$ans" != "Y" ]]; then
  echo "取消" >&2
  exit 1
fi

git tag -a "$NEW" -m "$MSG"
git push origin "$NEW"

echo
echo "✅ $NEW 已打并推到 origin"
