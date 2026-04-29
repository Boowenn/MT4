#!/usr/bin/env node
import { mkdir, rm, writeFile } from "node:fs/promises";
import { createServer } from "node:net";
import { spawn } from "node:child_process";
import { join } from "node:path";

const ROOT_URL = process.env.QUANTGOD_RESPONSIVE_URL || "http://127.0.0.1:8080/vue/";
const CHROME = process.env.CHROME_BIN || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const OUT_DIR = process.env.QUANTGOD_RESPONSIVE_OUT || "runtime/responsive-check";
const ROUTES = [
  "",
  "#mt5",
  "#mt5-strategy",
  "#mt5-trades",
  "#polymarket",
  "#polymarket-market-browser",
  "#polymarket-radar",
  "#polymarket-analysis",
  "#polymarket-execution",
  "#polymarket-ledger",
  "#paramlab",
  "#charts",
  "#reports",
];
const SCROLL_STEPS = [
  { name: "top", ratio: 0 },
  { name: "middle", ratio: 0.5 },
  { name: "bottom", ratio: 1 },
];
const VIEWPORTS = [
  { name: "narrow-320", width: 320, height: 720, mobile: true },
  { name: "phone-360", width: 360, height: 780, mobile: true },
  { name: "phone-390", width: 390, height: 844, mobile: true },
  { name: "iab-612", width: 612, height: 677, mobile: false },
  { name: "tablet-900", width: 900, height: 900, mobile: false },
  { name: "macbook-1280", width: 1280, height: 800, mobile: false },
  { name: "desktop-1512", width: 1512, height: 900, mobile: false },
];

const CHECK_EXPR = String.raw`
(() => {
  const overflowValues = new Set(["auto", "scroll", "overlay"]);
  const viewportWidth = window.innerWidth;
  const viewportHeight = window.innerHeight;
  const doc = document.documentElement;
  const body = document.body;

  const describe = (el) => {
    const tag = el.tagName.toLowerCase();
    const id = el.id ? "#" + el.id : "";
    const classes = [...el.classList].slice(0, 4).map((c) => "." + c).join("");
    const text = (el.innerText || el.textContent || "").replace(/\s+/g, " ").trim().slice(0, 90);
    return tag + id + classes + (text ? " :: " + text : "");
  };

  const visible = (el) => {
    const rect = el.getBoundingClientRect();
    const style = getComputedStyle(el);
    return rect.width > 1 && rect.height > 1 && style.display !== "none" && style.visibility !== "hidden";
  };

  const canScroll = (style, axis) => {
    const direct = axis === "x" ? style.overflowX : style.overflowY;
    return overflowValues.has(direct) || overflowValues.has(style.overflow);
  };

  const allowedClip = (el) => el.closest([
    ".table-panel",
    ".qd-radar-track",
    ".sidebar",
    ".nav-structured",
    ".qd-left-list",
    ".qd-right-rail",
    ".ai-watch-rail",
    ".history-list",
    ".poly-real-trade-ledger",
    ".data-table-card",
    "pre"
  ].join(","));

  const offscreen = [];
  const oversized = [];
  for (const el of document.querySelectorAll("body *")) {
    if (!visible(el) || allowedClip(el)) continue;
    const rect = el.getBoundingClientRect();
    if (rect.left < -1 || rect.right > viewportWidth + 1) {
      offscreen.push({
        selector: describe(el),
        left: Math.round(rect.left),
        right: Math.round(rect.right),
        width: Math.round(rect.width),
      });
    }
    if (rect.width > viewportWidth + 1) {
      oversized.push({
        selector: describe(el),
        width: Math.round(rect.width),
      });
    }
  }

  const scrollTargets = [
    ".table-panel",
    ".data-table-card .table-panel",
    ".poly-real-trade-ledger .table-panel",
    ".qd-left-list",
    ".qd-right-rail",
    ".ai-watch-rail",
    ".history-list",
    ".nav-structured",
    ".sidebar",
  ];
  const scrollIssues = [];
  const scrollables = [];
  for (const el of document.querySelectorAll(scrollTargets.join(","))) {
    if (!visible(el)) continue;
    const style = getComputedStyle(el);
    const xOverflow = el.scrollWidth > el.clientWidth + 2;
    const yOverflow = el.scrollHeight > el.clientHeight + 2;
    if (xOverflow || yOverflow) {
      const item = {
        selector: describe(el),
        clientWidth: el.clientWidth,
        scrollWidth: el.scrollWidth,
        clientHeight: el.clientHeight,
        scrollHeight: el.scrollHeight,
        overflowX: style.overflowX,
        overflowY: style.overflowY,
      };
      scrollables.push(item);
      if ((xOverflow && !canScroll(style, "x")) || (yOverflow && !canScroll(style, "y"))) {
        scrollIssues.push(item);
      }
    }
  }

  const textClipSelectors = [
    ".qd-card-head strong",
    ".qd-card-head span",
    ".qd-card-metrics b",
    ".qd-card-metrics small",
    ".strategy-focus-head h2",
    ".strategy-focus-head small",
    ".strategy-performance-grid b",
    ".strategy-performance-grid small",
    ".bar-label strong",
    ".bar-label small",
    ".bar-row b",
    ".viz-head h3",
    ".viz-stat strong",
    ".viz-stat span",
  ];
  const textClipIssues = [];
  for (const el of document.querySelectorAll(textClipSelectors.join(","))) {
    if (!visible(el)) continue;
    const style = getComputedStyle(el);
    const clipsX = el.scrollWidth > el.clientWidth + 2 && !canScroll(style, "x");
    const clipsY = el.scrollHeight > el.clientHeight + 2 && !canScroll(style, "y");
    if (clipsX || clipsY) {
      textClipIssues.push({
        selector: describe(el),
        clientWidth: el.clientWidth,
        scrollWidth: el.scrollWidth,
        clientHeight: el.clientHeight,
        scrollHeight: el.scrollHeight,
        overflowX: style.overflowX,
        overflowY: style.overflowY,
        whiteSpace: style.whiteSpace,
      });
    }
  }

  const blankAreaIssues = [];
  for (const el of document.querySelectorAll(".data-table-card, .viz-card")) {
    if (!visible(el)) continue;
    const rect = el.getBoundingClientRect();
    const table = el.querySelector(".table-panel");
    const bars = el.querySelectorAll(".bar-row");
    if (table) {
      const title = el.querySelector(".panel-title");
      const used = (title?.getBoundingClientRect().height || 0) + table.getBoundingClientRect().height + 36;
      if (rect.height - used > 180) {
        blankAreaIssues.push({ selector: describe(el), height: Math.round(rect.height), used: Math.round(used), blank: Math.round(rect.height - used) });
      }
    } else if (bars.length) {
      const head = el.querySelector(".viz-head");
      const used = (head?.getBoundingClientRect().height || 0) + [...bars].reduce((sum, row) => sum + row.getBoundingClientRect().height, 0) + Math.max(0, bars.length - 1) * 10 + 38;
      if (rect.height - used > 150) {
        blankAreaIssues.push({ selector: describe(el), rows: bars.length, height: Math.round(rect.height), used: Math.round(used), blank: Math.round(rect.height - used) });
      }
    }
  }

  const topbar = document.querySelector(".topbar");
  const sidebar = document.querySelector(".sidebar");
  const workspace = document.querySelector(".workspace");
  const appShell = document.querySelector(".app-shell");
  const route = location.hash || "#home";
  return {
    route,
    title: document.title,
    viewportWidth,
    viewportHeight,
    pageScrollWidth: Math.max(doc.scrollWidth, body.scrollWidth),
    bodyClientWidth: body.clientWidth,
    hasPageHorizontalOverflow: Math.max(doc.scrollWidth, body.scrollWidth) > viewportWidth + 1,
    offscreenCount: offscreen.length,
    oversizedCount: oversized.length,
    scrollIssueCount: scrollIssues.length,
    textClipCount: textClipIssues.length,
    blankAreaCount: blankAreaIssues.length,
    offscreen: offscreen.slice(0, 12),
    oversized: oversized.slice(0, 12),
    scrollIssues: scrollIssues.slice(0, 12),
    textClipIssues: textClipIssues.slice(0, 12),
    blankAreaIssues: blankAreaIssues.slice(0, 12),
    scrollables: scrollables.slice(0, 12),
    layout: {
      appShell: appShell ? getComputedStyle(appShell).gridTemplateColumns : null,
      sidebar: sidebar ? {
        width: Math.round(sidebar.getBoundingClientRect().width),
        height: Math.round(sidebar.getBoundingClientRect().height),
        overflowX: getComputedStyle(sidebar).overflowX,
        overflowY: getComputedStyle(sidebar).overflowY,
      } : null,
      topbar: topbar ? {
        height: Math.round(topbar.getBoundingClientRect().height),
        width: Math.round(topbar.getBoundingClientRect().width),
      } : null,
      workspace: workspace ? {
        left: Math.round(workspace.getBoundingClientRect().left),
        width: Math.round(workspace.getBoundingClientRect().width),
      } : null,
    },
  };
})()
`;

async function getFreePort() {
  const server = createServer();
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const { port } = server.address();
  await new Promise((resolve) => server.close(resolve));
  return port;
}

async function waitForJson(url, timeoutMs = 8000) {
  const deadline = Date.now() + timeoutMs;
  let lastError;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url);
      if (response.ok) return await response.json();
      lastError = new Error(`${response.status} ${response.statusText}`);
    } catch (error) {
      lastError = error;
    }
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw lastError || new Error(`Timed out waiting for ${url}`);
}

function createCdpSocket(wsUrl) {
  const ws = new WebSocket(wsUrl);
  let id = 0;
  const pending = new Map();
  const events = [];
  const waiters = [];

  ws.addEventListener("message", (event) => {
    const message = JSON.parse(event.data);
    if (message.id && pending.has(message.id)) {
      const { resolve, reject } = pending.get(message.id);
      pending.delete(message.id);
      if (message.error) reject(new Error(message.error.message));
      else resolve(message.result);
      return;
    }
    if (message.method) {
      events.push(message);
      for (let i = waiters.length - 1; i >= 0; i -= 1) {
        const waiter = waiters[i];
        if (waiter.method === message.method) {
          waiters.splice(i, 1);
          waiter.resolve(message);
        }
      }
    }
  });

  const open = new Promise((resolve, reject) => {
    ws.addEventListener("open", resolve, { once: true });
    ws.addEventListener("error", reject, { once: true });
  });

  return {
    open,
    send(method, params = {}) {
      const messageId = ++id;
      ws.send(JSON.stringify({ id: messageId, method, params }));
      return new Promise((resolve, reject) => pending.set(messageId, { resolve, reject }));
    },
    waitFor(method, timeoutMs = 8000) {
      const existingIndex = events.findIndex((event) => event.method === method);
      if (existingIndex >= 0) return Promise.resolve(events.splice(existingIndex, 1)[0]);
      return new Promise((resolve, reject) => {
        const waiter = { method, resolve };
        waiters.push(waiter);
        setTimeout(() => {
          const index = waiters.indexOf(waiter);
          if (index >= 0) waiters.splice(index, 1);
          reject(new Error(`Timed out waiting for ${method}`));
        }, timeoutMs);
      });
    },
    close() {
      ws.close();
    },
  };
}

async function main() {
  await rm(OUT_DIR, { recursive: true, force: true });
  await mkdir(OUT_DIR, { recursive: true });

  const port = await getFreePort();
  const profile = join("/tmp", `quantgod-responsive-${Date.now()}`);
  const chrome = spawn(CHROME, [
    "--headless=new",
    "--disable-gpu",
    "--hide-scrollbars=false",
    "--no-first-run",
    "--no-default-browser-check",
    `--user-data-dir=${profile}`,
    `--remote-debugging-port=${port}`,
    "about:blank",
  ], { stdio: ["ignore", "pipe", "pipe"] });

  try {
    await waitForJson(`http://127.0.0.1:${port}/json/version`);
    const results = [];

    for (const viewport of VIEWPORTS) {
      for (const route of ROUTES) {
        const label = `${viewport.name}-${route ? route.slice(1) : "home"}`;
        const target = await fetch(`http://127.0.0.1:${port}/json/new?${encodeURIComponent(ROOT_URL + route)}`, { method: "PUT" }).then((r) => r.json());
        const cdp = createCdpSocket(target.webSocketDebuggerUrl);
        await cdp.open;
        await cdp.send("Page.enable");
        await cdp.send("Runtime.enable");
        await cdp.send("Emulation.setDeviceMetricsOverride", {
          width: viewport.width,
          height: viewport.height,
          deviceScaleFactor: 1,
          mobile: viewport.mobile,
        });
        const load = cdp.waitFor("Page.loadEventFired", 10000).catch(() => null);
        await cdp.send("Page.navigate", { url: ROOT_URL + route });
        await load;
        await new Promise((resolve) => setTimeout(resolve, 350));

        for (const step of SCROLL_STEPS) {
          await cdp.send("Runtime.evaluate", {
            expression: `(() => { const root = document.scrollingElement || document.documentElement; window.scrollTo(0, Math.max(0, (root.scrollHeight - innerHeight) * ${step.ratio})); })()`,
          });
          await new Promise((resolve) => setTimeout(resolve, 80));
          const evaluated = await cdp.send("Runtime.evaluate", {
            expression: CHECK_EXPR,
            returnByValue: true,
            awaitPromise: true,
          });
          const metrics = evaluated.result.value;
          const shot = await cdp.send("Page.captureScreenshot", {
            format: "png",
            captureBeyondViewport: false,
          });
          const stepLabel = `${label}-${step.name}`;
          await writeFile(join(OUT_DIR, `${stepLabel}.png`), Buffer.from(shot.data, "base64"));
          const failed = metrics.hasPageHorizontalOverflow
            || metrics.offscreenCount > 0
            || metrics.oversizedCount > 0
            || metrics.scrollIssueCount > 0
            || metrics.textClipCount > 0
            || metrics.blankAreaCount > 0;
          results.push({ label: stepLabel, viewport, route: route || "#home", scrollStep: step.name, failed, metrics });
        }
        cdp.close();
        await fetch(`http://127.0.0.1:${port}/json/close/${target.id}`).catch(() => null);
      }
    }

    const reportPath = join(OUT_DIR, "report.json");
    await writeFile(reportPath, JSON.stringify({ generatedAt: new Date().toISOString(), rootUrl: ROOT_URL, results }, null, 2));

    const failures = results.filter((result) => result.failed);
    for (const result of results) {
      const status = result.failed ? "FAIL" : "PASS";
      const { metrics } = result;
      console.log(`${status} ${result.label} pageW=${metrics.pageScrollWidth}/${metrics.viewportWidth} off=${metrics.offscreenCount} wide=${metrics.oversizedCount} scroll=${metrics.scrollIssueCount} text=${metrics.textClipCount} blank=${metrics.blankAreaCount} columns=${metrics.layout.appShell}`);
    }
    console.log(`\nReport: ${reportPath}`);
    console.log(`Screenshots: ${OUT_DIR}`);
    if (failures.length > 0) {
      process.exitCode = 1;
    }
  } finally {
    chrome.kill("SIGTERM");
    await rm(profile, { recursive: true, force: true }).catch(() => {});
  }
}

main().catch((error) => {
  console.error(error.stack || error.message || String(error));
  process.exit(1);
});
