import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../", import.meta.url));
const readJson = (path) => JSON.parse(readFileSync(path, "utf8"));
const marketplace = readJson(resolve(root, ".agents/plugins/marketplace.json"));
const plugins = new Map(marketplace.plugins.map(({ name, source }) => [name, source.path]));

export const pluginNames = [...plugins.keys()].sort();

export function loadPlugins(names) {
  if (!Array.isArray(names)) throw new Error("Expected an array of SDK plugin names.");

  return [...new Set(names)].map((name) => {
    if (!plugins.has(name)) {
      throw new Error(`Unknown SDK plugin ${JSON.stringify(name)}. Available: ${pluginNames.join(", ")}`);
    }

    const directory = resolve(root, plugins.get(name));
    const manifest = readJson(resolve(directory, ".codex-plugin/plugin.json"));
    return {
      skillPath: manifest.skills && resolve(directory, manifest.skills),
      servers: manifest.mcpServers
        ? readJson(resolve(directory, manifest.mcpServers)).mcpServers
        : {},
    };
  });
}
