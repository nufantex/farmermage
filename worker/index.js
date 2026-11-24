/**
 * Cloudflare Worker: farmermage-cron
 *
 * 透過 Cloudflare Cron Triggers 每天 50 次穩定觸發 GitHub Actions workflow_dispatch，
 * 避開 GitHub Actions 內建 schedule 的延遲與漏跑問題。
 *
 * 所需環境變數：
 * - Vars:   GITHUB_OWNER, GITHUB_REPO, GITHUB_WORKFLOW, GITHUB_REF
 * - Secret: GITHUB_TOKEN（僅需 nufantex/farmermage 的 Actions: Read and write 權限）
 */

async function triggerWorkflow(env, cron) {
  if (!env.GITHUB_TOKEN) {
    throw new Error("Missing GITHUB_TOKEN secret in Cloudflare Worker");
  }

  const owner = env.GITHUB_OWNER || "nufantex";
  const repo = env.GITHUB_REPO || "farmermage";
  const workflow = env.GITHUB_WORKFLOW || "check.yml";
  const ref = env.GITHUB_REF || "main";

  const url = `https://api.github.com/repos/${owner}/${repo}/actions/workflows/${workflow}/dispatches`;
  const res = await fetch(url, {
    method: "POST",
    headers: {
      Accept: "application/vnd.github+json",
      Authorization: `Bearer ${env.GITHUB_TOKEN}`,
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "farmermage-cron-worker",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ ref }),
  });

  if (!res.ok) {
    const body = (await res.text()).slice(0, 500);
    console.error(
      JSON.stringify({
        event: "workflow_dispatch_failed",
        cron,
        status: res.status,
        body,
      })
    );
    throw new Error(`GitHub API error ${res.status}: ${body}`);
  }

  console.log(
    JSON.stringify({
      event: "workflow_dispatch_ok",
      cron,
      repo: `${owner}/${repo}`,
      workflow,
      ref,
      status: res.status,
    })
  );
}

export default {
  async fetch() {
    return new Response(
      JSON.stringify({ service: "farmermage-cron", status: "ok" }),
      {
        status: 200,
        headers: { "Content-Type": "application/json; charset=utf-8" },
      }
    );
  },

  async scheduled(controller, env) {
    await triggerWorkflow(env, controller.cron);
  },
};
