#!/usr/bin/env bash
set -euo pipefail

API_URL="http://localhost:8080/api/workflows/bootstrap-core"
TOKEN="devtoken"
REPO_URL="https://gitea.home.pogotech.net/jimgaspari/auto-cli-core-test.git"
NAMESPACE="greymatter"
BASE_BRANCH="main"
API_KEY=$GITEA_TOKEN


jq -n \
  --arg repo_url "$REPO_URL" \
  --arg git_user "$GIT_USERNAME" \
  --arg api_key "$API_KEY" \
  --arg ns "$NAMESPACE" \
  --arg base_branch "$BASE_BRANCH" \
  --arg docker_server "staging-oci.download.greymatter.io" \
  --arg docker_user "$DOCKER_USERNAME" \
  --arg docker_pass "$DOCKER_PASSWORD" \
  --arg author_name "Greymatter Automation" \
  --arg author_email "greymatter-bot@greymatter.io" \
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
    kubectl: { 
      image_pull: {
        docker_server: $docker_server,
        docker_username: $docker_user,
        docker_password: $docker_pass,
        secret_name: "greymatter-image-pull"
      },
      create_repo_secret: true
    },
    create_platform: {
      display_name: "Jims Mesh",
      mesh_name: "spire-mesh",
      security: "spire",
      image_repository: "staging-oci.download.greymatter.io"
    }
  }' \
| curl -sS -X POST "$API_URL" \
    -H "Content-Type: application/json" \
    -H "X-API-Token: $TOKEN" \
    --data-binary @- \
| jq
