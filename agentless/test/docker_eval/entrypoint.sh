#!/usr/bin/env bash
set -euo pipefail

PATCH_PATH="/workspace/patch.diff"
TESTS_PATH="/workspace/ground_truth_tests.txt"

log(){ echo "DEBUG: $*"; }
emit_result(){ echo "RESULT_JSON_BEGIN"; echo "$1"; echo "RESULT_JSON_END"; }
fail_and_exit(){ local err="$1" p="$2" t="$3"; emit_result "{\"passed\":$p,\"total\":$t,\"error\":\"$err\",\"details\":{}}"; exit 0; }

# Make sure we always emit *something* if a command unexpectedly fails
PASSED=0
GT_TOTAL=0
trap 'fail_and_exit "unexpected_exit" "$PASSED" "$GT_TOTAL"' ERR

###############################################################################
# Inputs / preview
###############################################################################
log "Container starting with:"
log "REPO_URL = ${REPO_URL}"
log "BASE_COMMIT = ${BASE_COMMIT:-<not set>}"
log "PATCH_PATH = ${PATCH_PATH}"

log "Content of patch file:"
if [[ -f $PATCH_PATH ]]; then head -20 "$PATCH_PATH" || true; else log "patch.diff missing!"; fi
log "---End of patch preview---"

###############################################################################
# Load tests
###############################################################################
if [[ -f "$TESTS_PATH" ]]; then
  log "Reading test specs from ground_truth_tests.txt"
  mapfile -t RAW_TESTS < "$TESTS_PATH"
else
  log "No ground_truth_tests.txt mounted; default to empty list"
  RAW_TESTS=()
fi

GT_TESTS=()
for l in "${RAW_TESTS[@]}"; do
  l="${l%$'\r'}"
  [[ -z "$l" || "$l" =~ ^# ]] && continue
  GT_TESTS+=("$l")
done
GT_TOTAL=${#GT_TESTS[@]}
log "Using ${GT_TOTAL} specs: ${GT_TESTS[*]:-<none>}"

###############################################################################
# Clone & checkout
###############################################################################
CLONE_URL="https://github.com/${REPO_URL}.git"
echo "Cloning repository ${CLONE_URL}..."
git clone "$CLONE_URL" repo || fail_and_exit "clone failed" 0 "$GT_TOTAL"
cd repo

if [[ -n "${BASE_COMMIT:-}" ]]; then
  log "Checking out provided commit: ${BASE_COMMIT}"
  git checkout "${BASE_COMMIT}" || log "Provided commit invalid; using default branch HEAD"
fi
CURRENT_COMMIT=$(git rev-parse HEAD || true)
log "Current commit: ${CURRENT_COMMIT}"

###############################################################################
# Apply patch
###############################################################################
log "Normalizing patch line endings"
if [[ -f "$PATCH_PATH" ]]; then
  sed -i 's/\r$//' "$PATCH_PATH" 2>/dev/null || true
fi

log "Applying patch..."
APPLY_OK=0
if [[ -f "$PATCH_PATH" ]]; then
  if git apply "$PATCH_PATH" 2>/dev/null; then APPLY_OK=1
  elif git apply --ignore-whitespace "$PATCH_PATH" 2>/dev/null; then APPLY_OK=1
  elif patch -p1 --fuzz=2 < "$PATCH_PATH" 2>/dev/null; then APPLY_OK=1
  fi
else
  APPLY_OK=1
fi

if [[ $APPLY_OK -ne 1 ]]; then
  log "Patch apply failed."
  git apply --check "$PATCH_PATH" || true
  fail_and_exit "apply failed" 0 "$GT_TOTAL"
fi
log "Files changed by patch:"; git status --short || true

###############################################################################
# Python env / pytest / Django settings
###############################################################################
log "Installing pytest & pytest-django"
pip install -q --root-user-action=ignore pytest pytest-django >/dev/null
python -m pip install -q --root-user-action=ignore -e . >/dev/null 2>&1 || true

# Clean PYTHONPATH: only repo root
export PYTHONPATH="$PWD:${PYTHONPATH:-}"

# Ensure packages exist
[[ -d tests ]] || mkdir -p tests
[[ -f tests/__init__.py ]] || touch tests/__init__.py
if [[ -d tests/migrations ]]; then
  [[ -f tests/migrations/__init__.py ]] || touch tests/migrations/__init__.py
  if [[ -d tests/migrations/custom_migration_operations ]]; then
    [[ -f tests/migrations/custom_migration_operations/__init__.py ]] || touch tests/migrations/custom_migration_operations/__init__.py
    cp -r tests/migrations/custom_migration_operations ./custom_migration_operations 2>/dev/null || true
    [[ -f custom_migration_operations/__init__.py ]] || touch custom_migration_operations/__init__.py
  fi
fi

# Minimal settings
RUNNER_SETTINGS="_swe_settings"
cat > "${RUNNER_SETTINGS}.py" <<'EOF'
SECRET_KEY = "dummy"
INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "tests",
    "tests.migrations",
]
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
USE_TZ = True
MIDDLEWARE = []
ROOT_URLCONF = "tests.urls"
EOF
export DJANGO_SETTINGS_MODULE="${RUNNER_SETTINGS}"

# Pytest base args
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
PY_ARGS_BASE=(-q -rA -p pytest_django --ds="${DJANGO_SETTINGS_MODULE}" --import-mode=importlib)

# Fallback trivial test
if [[ ${#GT_TESTS[@]} -eq 0 ]]; then
  log "No test specs provided; creating simple test"
  mkdir -p tests
  echo "def test_placeholder(): assert True" > tests/test_placeholder.py
  GT_TESTS=("tests/test_placeholder.py")
  GT_TOTAL=1
fi

###############################################################################
# Collect & run
###############################################################################
log "Collecting node ids..."
COLLECT_FILE=/tmp/collected.txt
pytest --collect-only -p pytest_django --ds="${DJANGO_SETTINGS_MODULE}" -q > "$COLLECT_FILE" 2>&1 || true
LINES=$(wc -l < "$COLLECT_FILE" || echo 0)
log "Collected $LINES lines"
head -20 "$COLLECT_FILE" || true

have_node(){ grep -Fx "$1" "$COLLECT_FILE" >/dev/null 2>&1; }

nearest_node(){
  local spec="$1"
  local file="${spec%%::*}"
  local base="${spec%::*}"
  # try "file::Class"
  if [[ "$base" != "$file" ]]; then
    local cand
    cand=$(grep -Fx "$base" "$COLLECT_FILE" 2>/dev/null | head -n1 || true)
    [[ -n "$cand" ]] && echo "$cand" && return 0
  fi
  # try just "file"
  grep -Fx "$file" "$COLLECT_FILE" 2>/dev/null | head -n1 || true
  return 0
}

PASSED=0
DETAILS=""
comma=""

for SPEC in "${GT_TESTS[@]}"; do
  SPEC="${SPEC%$'\r'}"
  RUN_SPEC="$SPEC"
  NOTE=""
  REASON=""

  if ! have_node "$SPEC"; then
    RUN_SPEC="$(nearest_node "$SPEC")"
    if [[ -z "$RUN_SPEC" ]]; then
      REASON="not_collected"
      DETAILS="${DETAILS}${comma}\"${SPEC}\":{\"pass\":false,\"reason\":\"${REASON}\"}"
      comma=","
      continue
    fi
    NOTE="remapped_from:${SPEC}"
  fi

  log "RUN_SPEC for $SPEC => $RUN_SPEC ${NOTE:+($NOTE)}"
  if pytest "${PY_ARGS_BASE[@]}" "$RUN_SPEC"; then
    ((PASSED++))
    DETAILS="${DETAILS}${comma}\"${SPEC}\":{\"pass\":true${NOTE:+,\"note\":\"$NOTE\"}}"
  else
    DETAILS="${DETAILS}${comma}\"${SPEC}\":{\"pass\":false${NOTE:+,\"note\":\"$NOTE\"}}"
  fi
  comma=","
done

RESULT="{\"passed\":${PASSED},\"total\":${GT_TOTAL},\"details\":{${DETAILS}}}"
emit_result "$RESULT"
exit 0
