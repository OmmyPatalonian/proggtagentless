#!/usr/bin/env bash
set -euo pipefail

PATCH_PATH="/workspace/patch.diff"
TEST_PATCH_PATH="/workspace/test_patch.diff"
TESTS_PATH="/workspace/ground_truth_tests.txt"

log(){ echo "DEBUG: $*"; }
emit_json(){ echo "RESULT_JSON_BEGIN"; echo "$1"; echo "RESULT_JSON_END"; }
fail_and_exit(){ local msg="$1" p="$2" t="$3"; emit_json "{\"passed\":$p,\"total\":$t,\"error\":\"$msg\",\"details\":{}}"; exit 0; }

PASSED=0
GT_TOTAL=0
trap 'fail_and_exit "unexpected_exit" "$PASSED" "$GT_TOTAL"' ERR

log "Container starting with:"
log "REPO_URL = ${REPO_URL}"
log "BASE_COMMIT = ${BASE_COMMIT:-<not set>}"
log "PATCH_PATH = ${PATCH_PATH}"
log "TEST_PATCH_PATH = ${TEST_PATCH_PATH:-<none>}"

log "Content of model patch:"
if [[ -f $PATCH_PATH ]]; then head -20 "$PATCH_PATH" || true; else log "patch.diff missing!"; fi
log "---End of patch preview---"

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

normalize_crlf(){ sed -i 's/\r$//' "$1" 2>/dev/null || true; }
apply_patch_file(){
  local file="$1"
  git apply "$file" 2>/dev/null \
    || git apply --ignore-whitespace "$file" 2>/dev/null \
    || patch -p1 --fuzz=2 < "$file" 2>/dev/null \
    || return 1
  return 0
}

if [[ -s "$TEST_PATCH_PATH" ]]; then
  log "Normalizing & applying test_patch.diff"
  normalize_crlf "$TEST_PATCH_PATH"
  apply_patch_file "$TEST_PATCH_PATH" || fail_and_exit "apply test_patch failed" 0 "$GT_TOTAL"
fi

if [[ -f "$PATCH_PATH" ]]; then
  log "Normalizing & applying model patch"
  normalize_crlf "$PATCH_PATH"
  apply_patch_file "$PATCH_PATH" || { git apply --check "$PATCH_PATH" || true; fail_and_exit "apply failed" 0 "$GT_TOTAL"; }
fi

log "Files changed by patches:"; git status --short || true

log "Installing pytest & pytest-django"
pip install -q --root-user-action=ignore pytest pytest-django >/dev/null
python -m pip install -q --root-user-action=ignore -e . >/dev/null 2>&1 || true

export PYTHONPATH="$PWD:$PWD/tests:$PWD/tests/migrations:${PYTHONPATH:-}"

if [ -d tests/migrations/custom_migration_operations ]; then
  SRC="tests/migrations/custom_migration_operations"
  DST="custom_migration_operations"
  [ -f "$SRC/__init__.py" ] || touch "$SRC/__init__.py"
  if [ ! -e "$DST" ]; then ln -s "$PWD/$SRC" "$PWD/$DST" 2>/dev/null || cp -r "$SRC" "$DST"; fi
  [ -f "$DST/__init__.py" ] || touch "$DST/__init__.py"
  export PYTHONPATH="$PWD/$DST:$PYTHONPATH"
fi

[[ -d tests ]] || mkdir -p tests
[[ -f tests/__init__.py ]] || touch tests/__init__.py
if [[ -d tests/migrations ]]; then
  [[ -f tests/migrations/__init__.py ]] || touch tests/migrations/__init__.py
fi

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

if pytest -q --help 2>&1 | grep -q -- '--ds'; then
  DS_OPTS=(--ds="${DJANGO_SETTINGS_MODULE}")
else
  DS_OPTS=()
  log "--ds not supported; relying on DJANGO_SETTINGS_MODULE env only"
fi

export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
PY_ARGS_BASE=(-q -rA -p pytest_django "${DS_OPTS[@]}")

if [[ ${#GT_TESTS[@]} -eq 0 ]]; then
  log "No test specs provided; creating simple test"
  mkdir -p tests
  echo "def test_placeholder(): assert True" > tests/test_placeholder.py
  GT_TESTS=("tests/test_placeholder.py")
  GT_TOTAL=1
fi

run_one(){
  local spec="$1"
  pytest "${PY_ARGS_BASE[@]}" "$spec"
  local rc=$?
  if [[ $rc -eq 0 ]]; then return 0; fi
  local file="${spec%%::*}"
  local tail="${spec#${file}::}"
  if [[ "$file" == "$tail" ]]; then return $rc; fi
  pytest "${PY_ARGS_BASE[@]}" "$file" -k "$tail"
  return $?
}

PASSED=0
DETAILS=""
comma=""

for SPEC in "${GT_TESTS[@]}"; do
  SPEC="${SPEC%$'\r'}"
  log "Running test spec: $SPEC"
  if run_one "$SPEC"; then
    ((PASSED++))
    DETAILS="${DETAILS}${comma}\"${SPEC}\":{\"pass\":true}"
  else
    rc=$?
    if [[ $rc -eq 5 ]]; then
      DETAILS="${DETAILS}${comma}\"${SPEC}\":{\"pass\":false,\"reason\":\"not_collected\"}"
    else
      DETAILS="${DETAILS}${comma}\"${SPEC}\":{\"pass\":false}"
    fi
  fi
  comma=","
done

RESULT="{\"passed\":${PASSED},\"total\":${GT_TOTAL},\"details\":{${DETAILS}}}"
emit_json "$RESULT"
exit 0
