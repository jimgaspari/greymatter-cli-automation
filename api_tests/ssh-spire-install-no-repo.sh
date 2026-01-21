#!/usr/bin/env bash
set -euo pipefail

API_URL="http://localhost:8080/api/workflows/bootstrap-core"
TOKEN="devtoken"
REPO_URL="git@gitea-ssh.home.pogotech.net:jimgaspari/auto-cli-core-test.git"
NAMESPACE="greymatter"
BASE_BRANCH="main"
TARGET_BRANCH="bootstrap-test"

jq -n \
  --arg repo_url "$REPO_URL" \
  --rawfile ssh_key /home/jim/.ssh/id_ed25519 \
  --rawfile known_hosts /home/jim/.ssh/known_hosts \
  --arg ns "$NAMESPACE" \
  --arg base_branch "$BASE_BRANCH" \
  --arg target_branch "$TARGET_BRANCH" \
  --arg docker_server "staging-oci.download.greymatter.io" \
  --arg docker_user "jgaspari" \
  --arg docker_pass "etu4ckf7HFB3bqm-rjq" \
  --arg author_name "Greymatter Automation" \
  --arg author_email "greymatter-bot@greymatter.io" \
  '{
    clone: {
      type: "ssh",
      repo_url: $repo_url,
      ssh_private_key: $ssh_key,
      known_hosts: $known_hosts,
      strict_host_key_checking: true
    },
    depth: 1,
    workspace: "test-1",
    git: {
      base_branch: $base_branch,
      target_branch: $target_branch,
      create_branch_if_missing: true,
      push_branch_to_remote: true,
      push_changes: true,
      author_name: $author_name,
      author_email: $author_email
    },
    kubectl: { 
      namespace: $ns,
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
      namespace: $ns,
      security: "spire",
      image_repository: "staging-oci.download.greymatter.io"
    }
  }' \
| curl -sS -X POST "$API_URL" \
    -H "Content-Type: application/json" \
    -H "X-API-Token: $TOKEN" \
    --data-binary @- \
| jq

sleep 5
NAMESPACE="spire-greymatter"
BASE_BRANCH="main"
TARGET_BRANCH="bootstrap-test-2"

jq -n \
  --arg repo_url "$REPO_URL" \
  --rawfile ssh_key /home/jim/.ssh/id_ed25519 \
  --rawfile known_hosts /home/jim/.ssh/known_hosts \
  --arg ns "$NAMESPACE" \
  --arg base_branch "$BASE_BRANCH" \
  --arg target_branch "$TARGET_BRANCH" \
  --arg docker_server "staging-oci.download.greymatter.io" \
  --arg docker_user "jgaspari" \
  --arg docker_pass "etu4ckf7HFB3bqm-rjq" \
  --arg author_name "Greymatter Automation" \
  --arg author_email "greymatter-bot@greymatter.io" \
  '{
    clone: {
      type: "ssh",
      repo_url: $repo_url,
      ssh_private_key: $ssh_key,
      known_hosts: $known_hosts,
      strict_host_key_checking: true
    },
    depth: 1,
    workspace: "test-2",
    git: {
      base_branch: $base_branch,
      target_branch: $target_branch,
      create_branch_if_missing: true,
      push_branch_to_remote: true,
      push_changes: true,
      author_name: $author_name,
      author_email: $author_email
    },
    kubectl: { 
      namespace: $ns,
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
      namespace: $ns,
      security: "spire",
      no_managed_spire: true,
      image_repository: "staging-oci.download.greymatter.io"
    }
  }' \
| curl -sS -X POST "$API_URL" \
    -H "Content-Type: application/json" \
    -H "X-API-Token: $TOKEN" \
    --data-binary @- \
| jq

