import { randomUUID } from "node:crypto";
import { mkdirSync, readFileSync, renameSync, rmSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { loadPlugins, pluginNames } from "./catalog.js";

const agentDir = process.env.PI_CODING_AGENT_DIR || join(homedir(), ".pi", "agent");
const selectionFile = join(agentDir, "hpc-agentic-sdk.json");

function readSelection() {
  try {
    return JSON.parse(readFileSync(selectionFile, "utf8"));
  } catch (error) {
    if (error.code === "ENOENT") return [];
    throw error;
  }
}

function saveSelection(names) {
  mkdirSync(agentDir, { recursive: true });
  const temporaryFile = `${selectionFile}.${randomUUID()}.tmp`;
  try {
    writeFileSync(temporaryFile, `${JSON.stringify(names, null, 2)}\n`);
    renameSync(temporaryFile, selectionFile);
  } finally {
    rmSync(temporaryFile, { force: true });
  }
}

export default function (pi) {
  let selection = [];
  let plugins = [];
  let selectionError;
  try {
    const saved = readSelection();
    if (!Array.isArray(saved)) throw new Error("Expected an array of SDK plugin names.");
    // An update can remove plugins that were present when the selection was saved.
    selection = saved.filter((name) => pluginNames.includes(name));
    plugins = loadPlugins(selection);
  } catch (error) {
    selectionError = error.message;
  }

  pi.on("resources_discover", () => ({
    skillPaths: plugins.map(({ skillPath }) => skillPath).filter(Boolean),
  }));

  for (const { servers } of plugins) {
    for (const [name, config] of Object.entries(servers)) {
      pi.registerMcpServer(name, { ...config, exposure: "direct", timeout: 300 });
    }
  }

  pi.registerCommand("hpc-sdk", {
    description: "List or select HPC Agentic SDK plugins",
    async handler(args, ctx) {
      const [action, ...names] = args.trim().split(/[\s,]+/);
      if (!action || action === "list") {
        if (selectionError) ctx.ui.notify(`Could not load SDK plugins. ${selectionError}`, "warning");
        ctx.ui.notify(`Selected: ${selection.join(", ") || "none"}\nAvailable: ${pluginNames.join(", ")}\nUse /hpc-sdk set <names> or /hpc-sdk clear.`, "info");
        return;
      }

      const clear = action === "clear" && names.length === 0;
      if (!clear && (action !== "set" || names.length === 0)) {
        ctx.ui.notify("Use /hpc-sdk list, /hpc-sdk set <names>, or /hpc-sdk clear.", "error");
        return;
      }

      const next = clear ? [] : [...new Set(names)];
      try {
        loadPlugins(next);
        saveSelection(next);
      } catch (error) {
        ctx.ui.notify(error.message, "error");
        return;
      }
      await ctx.reload();
    },
  });
}
