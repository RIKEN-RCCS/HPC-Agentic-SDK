import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { parse } from "yaml";
import { loadPlugins, pluginNames, restoreSelection } from "./catalog.js";

function loadSelection(names) {
  const plugins = loadPlugins(names);
  return {
    names,
    skills: plugins.flatMap(({ skillPath }) => skillPath ? readSkills(skillPath) : []),
    servers: plugins.flatMap(({ servers }) => Object.entries(servers)),
  };
}

function readSkills(directory) {
  return readdirSync(directory, { withFileTypes: true })
    .filter((entry) => entry.isDirectory() && !entry.name.startsWith("."))
    .map(({ name: id }) => {
      const path = join(directory, id, "SKILL.md");
      const text = readFileSync(path, "utf8");
      const frontmatter = /^---\r?\n([\s\S]*?)\r?\n---(?:\r?\n|$)/.exec(text);
      if (!frontmatter) throw new Error(`Missing skill frontmatter in ${path}`);

      const metadata = parse(frontmatter[1]);
      return {
        id,
        name: metadata.name,
        description: metadata.description,
        autoinvoke: metadata.metadata?.["opencode/autoinvoke"] ?? !metadata["disable-model-invocation"],
        content: text.slice(frontmatter[0].length).trimStart(),
        path,
      };
    });
}

export default {
  id: "hpc-agentic-sdk",
  async setup(ctx) {
    const saved = await ctx.storage.get("plugins");
    let selection = loadSelection(Array.isArray(saved) ? restoreSelection(saved) : []);

    const registrations = [
      await ctx.skill.transform((editor) => {
        for (const skill of selection.skills) {
          if (!editor.get(skill.id)) editor.add(skill);
        }
      }),
      await ctx.mcp.transform((editor) => {
        for (const [name, { command, args = [], env }] of selection.servers) {
          if (!editor.get(name)) {
            editor.set(name, {
              type: "local",
              command: [command, ...args],
              environment: env,
              codemode: false,
              timeout: { startup: 120_000 },
            });
          }
        }
      }),
      await ctx.command.transform((editor) => {
        editor.add({
          name: "hpc-sdk",
          description: "List or select HPC Agentic SDK plugins",
          async execute({ sessionID, prompt }) {
            const reply = (text) => ctx.session.synthetic({ sessionID, text });
            const [action, ...names] = prompt.text.trim().split(/[\s,]+/);
            if (!action || action === "list") {
              await reply(`Selected: ${selection.names.join(", ") || "none"}\nAvailable: ${pluginNames.join(", ")}\nUse /hpc-sdk set <names> or /hpc-sdk clear.`);
              return;
            }

            const clear = action === "clear" && names.length === 0;
            if (!clear && (action !== "set" || names.length === 0)) {
              await reply("Use /hpc-sdk list, /hpc-sdk set <names>, or /hpc-sdk clear.");
              return;
            }

            try {
              const next = loadSelection(clear ? [] : [...new Set(names)]);
              await ctx.storage.set("plugins", next.names);
              selection = next;
              await Promise.all([ctx.skill.reload(), ctx.mcp.reload()]);
            } catch (error) {
              await reply(`Could not update SDK plugins. ${error.message}`);
              return;
            }
            await reply(`Selected SDK plugins: ${selection.names.join(", ") || "none"}.`);
          },
        });
      }),
    ];
    return async () => {
      for (const registration of registrations) await registration.dispose();
    };
  },
};
