#!/usr/bin/env bash
set -euo pipefail

API_URL="http://localhost:8080/api/workflows/bootstrap-tenant"
TOKEN="devtoken"
REPO_URL="https://gitea.home.pogotech.net/jimgaspari/auto-cli-tenant-test-2.git"
NAMESPACE="auto-tenant-2"
BASE_BRANCH="main"
API_KEY=$GITEA_TOKEN

curl -k -X DELETE "https://gitea.home.pogotech.net/api/v1/repos/jimgaspari/auto-cli-tenant-test-2" \
  -H "Authorization: token $GITEA_TOKEN"

jq -n \
  --arg repo_url "$REPO_URL" \
  --arg git_user "$GIT_USERNAME" \
  --arg api_key "$API_KEY" \
  --arg ns "$NAMESPACE" \
  --arg base_branch "$BASE_BRANCH" \
  --arg author_name "Greymatter Automation" \
  --arg author_email "greymatter-bot@greymatter.io" \
  --rawfile tls_key /home/jim/Working/local/test_certs/server.key \
  --rawfile tls_crt /home/jim/Working/local/test_certs/server.crt \
  '{
    depth: 1,
    workspace: "test-1",
    namespace: $ns,
    git: {
      type: "https",
      repo_url: $repo_url,
      username: $git_user,
      token: $api_key,
      insecure_skip_tls_verify: true,
      base_branch: $base_branch,
      create_branch_if_missing: true,
      push_branch_to_remote: true,
      push_changes: true,
      author_name: $author_name,
      author_email: $author_email
    },
    kubernetes: { 
      create_repo_secret: true,
      edge_ingress_tls_secret: {
        enabled: true,
        tls_crt: $tls_crt,
        tls_key: $tls_key,
      },
    },
    prometheus_check: {enabled: true},
    create_project: {
      core_namespace: "greymatter",
      security: "spire",
      script: {
        enabled: true,
        configmap_name: "robot-shop-script",
      },
    }
  }' \
| curl -sS -X POST "$API_URL" \
    -H "Content-Type: application/json" \
    -H "X-API-Token: $TOKEN" \
    --data-binary @- \
| jq
