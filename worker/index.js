/**
 * Cloudflare Worker: farmermage-cron
 *
 * 使用 2 條 Cloudflare Cron Triggers，依 UTC 分鐘數分流，讓兩個專案各自每天執行 50 次
 * 且完全錯開（間隔 7～15 分鐘），不額外消耗 Cloudflare 免費方案的 Cron 名額：
 *
 * - Cron 1: `7,22,37,52 * * * *`（每小時 4 次）
 *   - :07、:37 -> nufantex/farmermage（48 次/天）
 *   - :22、:52 -> chingfonlee/Katharine-s-monitor（48 次/天）
 * - Cron 2: `14,44 4,16 * * *`（台灣時間 00:14、00:44、12:14、12:44）
 *   - :14 -> nufantex/farmermage（+2 = 50 次/天）
 *   - :44 -> chingfonlee/Katharine-s-monitor（+2 = 50 次/天）
 *
 * 所需 Secrets：
 * - GITHUB_TOKEN              （nufantex/farmermage 的 Actions: Read and write）
 * - GITHUB_TOKEN_CHINGFONLEE  （chingfonlee/Katharine-s-monitor 的 Actions: Read and write）
 */

const NUFANTEX_MINUTES = new Set([7, 14, 37]);
const CHINGFONLEE_MINUTES = new Set([22, 44, 52]);

async function triggerWorkflow(target, token, cron, minute) {
  if (!token) {
    console.warn(
      JSON.stringify({
        event: "workflow_dispatch_skipped",
        reason: "missing_token",
        repo: `${target.owner}/${target.repo}`,
        cron,
        minute,
      })
    );
    return;
  }

  const url = `https://api.github.com/repos/${target.owner}/${target.repo}/actions/workflows/${target.workflow}/dispatches`;
  const res = await fetch(url, {
    method: "POST",
    headers: {
      Accept: "application/vnd.github+json",
      Authorization: `Bearer ${token}`,
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "farmermage-cron-worker",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ ref: target.ref }),
  });

  if (!res.ok) {
    const body = (await res.text()).slice(0, 500);
    console.error(
      JSON.stringify({
        event: "workflow_dispatch_failed",
        repo: `${target.owner}/${target.repo}`,
        cron,
        minute,
        status: res.status,
        body,
      })
    );
    throw new Error(`GitHub API error (${target.owner}/${target.repo}) ${res.status}: ${body}`);
  }

  console.log(
    JSON.stringify({
      event: "workflow_dispatch_ok",
      repo: `${target.owner}/${target.repo}`,
      workflow: target.workflow,
      ref: target.ref,
      cron,
      minute,
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
    const minute = new Date(controller.scheduledTime).getUTCMinutes();
    const nufantex = {
      owner: env.GITHUB_OWNER || "nufantex",
      repo: env.GITHUB_REPO || "farmermage",
      workflow: env.GITHUB_WORKFLOW || "check.yml",
      ref: env.GITHUB_REF || "main",
    };
    const chingfonlee = {
      owner: env.GITHUB_OWNER_CHINGFONLEE || "chingfonlee",
      repo: env.GITHUB_REPO_CHINGFONLEE || "Katharine-s-monitor",
      workflow: env.GITHUB_WORKFLOW_CHINGFONLEE || "check.yml",
      ref: env.GITHUB_REF_CHINGFONLEE || "main",
    };

    if (NUFANTEX_MINUTES.has(minute)) {
      await triggerWorkflow(nufantex, env.GITHUB_TOKEN, controller.cron, minute);
    } else if (CHINGFONLEE_MINUTES.has(minute)) {
      await triggerWorkflow(
        chingfonlee,
        env.GITHUB_TOKEN_CHINGFONLEE,
        controller.cron,
        minute
      );
    } else {
      // 手動於 Dashboard 測試任意分鐘時，分別嘗試觸發已設定 token 的目標
      await Promise.allSettled([
        triggerWorkflow(nufantex, env.GITHUB_TOKEN, controller.cron, minute),
        triggerWorkflow(chingfonlee, env.GITHUB_TOKEN_CHINGFONLEE, controller.cron, minute),
      ]);
    }
  },
};
