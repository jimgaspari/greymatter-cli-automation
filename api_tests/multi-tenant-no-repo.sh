#!/usr/bin/env bash
# set -euo pipefail

API_URL="http://localhost:8080/api/workflows/bootstrap-tenant"
FLASK_REPO="https://gitea.home.pogotech.net/jimgaspari/auto-cli-flask.git"
PSQL_REPO="https://gitea.home.pogotech.net/jimgaspari/auto-cli-psql.git"
TOKEN="devtoken"
BASE_BRANCH="main"
API_KEY=$GITEA_TOKEN

curl -k -X DELETE "https://gitea.home.pogotech.net/api/v1/repos/jimgaspari/auto-cli-flask" \
  -H "Authorization: token $GITEA_TOKEN"

curl -k -X DELETE "https://gitea.home.pogotech.net/api/v1/repos/jimgaspari/auto-cli-psql" \
  -H "Authorization: token $GITEA_TOKEN"

jq -n \
  --arg git_user "$GIT_USERNAME" \
  --arg flask_url "$FLASK_REPO" \
  --arg psql_url "$PSQL_REPO" \
  --arg api_key "$API_KEY" \
  --arg base_branch "$BASE_BRANCH" \
  --arg author_name "Greymatter Automation" \
  --arg author_email "greymatter-bot@greymatter.io" \
  --rawfile tls_key /home/jim/Working/local/test_certs/server.key \
  --rawfile tls_crt /home/jim/Working/local/test_certs/server.crt \
  '{
    "depth": 1,
    "core_namespace": "greymatter",
    "git": {
      "type": "https",
      "username": $git_user,
      "token": $api_key,
      "insecure_skip_tls_verify": true,
      "base_branch": $base_branch,
      "create_branch_if_missing": true,
      "push_branch_to_remote": true,
      "push_changes": true,
      "author_name": $author_name,
      "author_email": $author_email
    },
    "kubernetes": { 
      "create_repo_secret": true,
      "edge_ingress_tls_secret": {
        "enabled": true,
        "tls_crt": $tls_crt,
        "tls_key": $tls_key,
      },
    },
    "prometheus_check": {enabled: true},
    "tenants": [
      {
        "namespace": "flask",
        "project_settings": {
          "security": "spire"
        },
        "script": {
          "enabled": true,
          "configmap_name": "flask-script"
        },
        "git": {
          "repo_url": "https://gitea.home.pogotech.net/jimgaspari/auto-cli-flask.git",
          "base_branch": "main"
        },
        "env_vars": {
          "PSQL_NAMESPACE": "postgres"
        }
      },
      {
        "namespace": "postgres",
        "project_settings": {
          "security": "spire"
        },
        "script": {
          "enabled": true,
          "configmap_name": "postgres-script"
        },
        "git": {
          "repo_url": "https://gitea.home.pogotech.net/jimgaspari/auto-cli-psql.git",
          "base_branch": "main"
        },
        "env_vars": {
          "FLASK_NAMESPACE": "flask"
        }
      }
    ]
  }' \
| curl -sS -X POST "$API_URL" \
    -H "Content-Type: application/json" \
    -H "X-API-Token: $TOKEN" \
    --data-binary @- \
| jq
