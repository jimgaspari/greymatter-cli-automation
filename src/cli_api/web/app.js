function $(id) { return document.getElementById(id); }

function setResult(obj) {
    $("result").textContent = typeof obj === "string" ? obj : JSON.stringify(obj, null, 2);
}

function parseTenantNamespaces() {
    const raw = $("tenantNamespaces").value.trim();
    if (!raw) return null;
    return raw.split(",").map(s => s.trim()).filter(Boolean);
}

function buildCloneSpec() {
    const type = $("cloneType").value;
    const repoUrl = $("repoUrl").value.trim();
    if (!repoUrl) throw new Error("Repo URL is required");

    if (type === "ssh") {
        return {
            type: "ssh",
            repo_url: repoUrl,
            ssh_private_key_b64: $("sshKeyB64").value.trim(),
            known_hosts: $("knownHosts").value,
            strict_host_key_checking: $("strictHostKeyChecking").checked
        };
    }

    return {
        type: "https",
        repo_url: repoUrl,
        username: $("httpsUsername").value.trim() || null,
        token: $("httpsToken").value.trim() || null,
        password: $("httpsPassword").value.trim() || null
    };
}

function buildCreatePlatformOptions() {
    const openshift = $("openshift").value === "true";
    const security = $("security").value.trim() || null;

    return {
        display_name: $("displayName").value.trim() || null,
        namespace: $("namespace").value.trim() || null,
        security: security,
        openshift: openshift,

        image_repository: $("imageRepository").value.trim() || null,
        image_pull_secret: $("imagePullSecret").value.trim() || null,

        spire_namespace: $("spireNamespace").value.trim() || null,
        no_managed_spire: $("noManagedSpire").checked,

        prometheus_address: $("prometheusAddress").value.trim() || null,

        elasticsearch_address: $("elasticsearchAddress").value.trim() || null,
        no_elasticsearch_tls_verify: $("noElasticsearchTlsVerify").checked,

        tenant_namespace: parseTenantNamespaces(),
        pki_cert: $("pkiCert").value.trim() || null,

        no_gitops_fips: $("noGitopsFips").checked
    };
}

async function postJson(url, body) {
    const token = $("apiToken").value.trim();
    const headers = { "Content-Type": "application/json" };
    if (token) headers["X-API-Token"] = token;

    const res = await fetch(url, {
        method: "POST",
        headers,
        body: JSON.stringify(body)
    });

    const text = await res.text();
    let payload;
    try { payload = JSON.parse(text); } catch { payload = text; }

    if (!res.ok) {
        throw new Error(typeof payload === "string" ? payload : JSON.stringify(payload, null, 2));
    }
    return payload;
}

function toggleCloneFields() {
    const type = $("cloneType").value;
    $("sshFields").style.display = type === "ssh" ? "block" : "none";
    $("httpsFields").style.display = type === "https" ? "block" : "none";
}

$("cloneType").addEventListener("change", toggleCloneFields);
toggleCloneFields();

$("runCore").addEventListener("click", async () => {
    try {
        setResult("Running bootstrap-core...");
        const body = {
            clone: buildCloneSpec(),
            branch: $("branch").value.trim() || "main",
            depth: Number($("depth").value || 1),
            create_platform: buildCreatePlatformOptions()
        };
        const result = await postJson("/api/workflows/bootstrap-core", body);
        setResult(result);
    } catch (e) {
        setResult(String(e));
    }
});

$("runTenant").addEventListener("click", async () => {
    try {
        const tenantName = $("tenantName").value.trim();
        if (!tenantName) throw new Error("Tenant name is required");

        setResult("Running bootstrap-tenant...");
        const body = {
            clone: buildCloneSpec(),
            branch: $("branch").value.trim() || "main",
            depth: Number($("depth").value || 1),
            tenant_name: tenantName
        };
        const result = await postJson("/api/workflows/bootstrap-tenant", body);
        setResult(result);
    } catch (e) {
        setResult(String(e));
    }
});
