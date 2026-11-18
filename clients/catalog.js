import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../", import.meta.url));
const readJson = (path) => JSON.parse(readFileSync(path, "utf8"));
const marketplace = readJson(resolve(root, ".agents/plugins/marketplace.json"));
const plugins = new Map(marketplace.plugins.map(({ name, source }) => [name, source.path]));

const rookeryBase = "hpc";
export const pluginNames = [...plugins.keys()].filter((name) => name !== rookeryBase).sort();

export function restoreSelection(names) {
  return [...new Set(names
    .filter((name) => typeof name === "string")
    .map((name) => pluginNames.includes(name) ? name : `hpc-${name}`)
    .filter((name) => pluginNames.includes(name)))];
}

export function loadPlugins(names) {
  if (!Array.isArray(names)) throw new Error("Expected an array of SDK plugin names.");

  for (const name of names) {
    if (!pluginNames.includes(name)) {
      throw new Error(`Unknown SDK plugin ${JSON.stringify(name)}. Available: ${pluginNames.join(", ")}`);
    }
  }

  return [rookeryBase, ...new Set(names)].map((name) => {
    const directory = resolve(root, plugins.get(name));
    const manifest = readJson(resolve(directory, ".codex-plugin/plugin.json"));
    const servers = manifest.mcpServers
      ? readJson(resolve(directory, manifest.mcpServers)).mcpServers
      : {};
    if (name === rookeryBase) {
      // The OpenCode and Pi package ships the Python project alongside its skills.
      // Marketplace plugin caches can contain only the plugin directory.
      for (const { args } of Object.values(servers)) {
        args[args.indexOf("--from") + 1] = resolve(root, "rookery");
      }
    }
    return {
      skillPath: manifest.skills && resolve(directory, manifest.skills),
      servers,
    };
  });
}
