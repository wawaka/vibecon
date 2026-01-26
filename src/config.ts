import * as fs from "fs";
import * as os from "os";
import * as path from "path";
import type { MountSpec, VibeconConfig } from "./types.js";

export function loadConfig(configPath: string): Partial<VibeconConfig> {
  const expandedPath = configPath.replace(/^~/, os.homedir());
  if (!fs.existsSync(expandedPath)) {
    return {};
  }
  try {
    const content = fs.readFileSync(expandedPath, "utf-8");
    return JSON.parse(content);
  } catch (e) {
    if (e instanceof SyntaxError) {
      console.error(`Error: Invalid JSON in ${expandedPath}: ${e.message}`);
      process.exit(1);
    }
    return {};
  }
}

export function getMergedConfig(projectRoot: string): VibeconConfig {
  const globalCfg = loadConfig("~/.vibecon.json");
  const projectCfg = loadConfig(path.join(projectRoot, ".vibecon.json"));

  return {
    mounts: [...(globalCfg.mounts || []), ...(projectCfg.mounts || [])],
  };
}

export function parseMount(
  mountSpec: MountSpec | string,
  projectRoot: string,
  containerName: string
): string[] {
  if (typeof mountSpec === "string") {
    console.error(
      `Error: Mount must be an object with explicit 'type' field, got string: ${mountSpec}`
    );
    process.exit(1);
  }

  if (typeof mountSpec !== "object" || mountSpec === null) {
    console.error(`Error: Mount must be an object, got: ${typeof mountSpec}`);
    process.exit(1);
  }

  const mountType = mountSpec.type;
  if (!mountType) {
    console.error(
      `Error: Mount missing required 'type' field: ${JSON.stringify(mountSpec)}`
    );
    process.exit(1);
  }

  const target = mountSpec.target;
  if (!target) {
    console.error(
      `Error: Mount missing required 'target' field: ${JSON.stringify(mountSpec)}`
    );
    process.exit(1);
  }

  const readOnly = mountSpec.read_only || false;
  const selinux = mountSpec.selinux;

  if (mountType === "anonymous") {
    const uid = mountSpec.uid;
    const gid = mountSpec.gid;

    if (uid !== undefined || gid !== undefined) {
      const mountOpts: string[] = [];
      if (uid !== undefined) {
        mountOpts.push(`uid=${uid}`);
      }
      if (gid !== undefined) {
        mountOpts.push(`gid=${gid}`);
      }
      const driverOpts = `o=${mountOpts.join(",")}`;

      const mountParts = [
        "type=volume",
        `target=${target}`,
        "volume-opt=type=tmpfs",
        "volume-opt=device=tmpfs",
        `"volume-opt=${driverOpts}"`,
      ];
      if (readOnly) {
        mountParts.push("readonly");
      }
      return ["--mount", mountParts.join(",")];
    } else {
      return ["-v", target];
    }
  } else if (mountType === "bind") {
    const source = mountSpec.source;
    if (!source) {
      console.error(
        `Error: Bind mount missing required 'source' field: ${JSON.stringify(mountSpec)}`
      );
      process.exit(1);
    }

    let resolved = source.replace(/^~/, os.homedir());
    if (!path.isAbsolute(resolved)) {
      resolved = path.normalize(path.join(projectRoot, resolved));
    }
    if (!fs.existsSync(resolved)) {
      console.log(`Warning: bind mount source does not exist: ${resolved}`);
    }

    if (mountSpec.uid !== undefined || mountSpec.gid !== undefined) {
      console.log(
        `Warning: uid/gid options ignored for bind mount (not supported by Docker)`
      );
    }

    let mountArg = `${resolved}:${target}`;
    const suffixOpts: string[] = [];
    if (readOnly) {
      suffixOpts.push("ro");
    }
    if (selinux) {
      suffixOpts.push(selinux);
    }
    if (suffixOpts.length > 0) {
      mountArg += ":" + suffixOpts.join(",");
    }
    return ["-v", mountArg];
  } else if (mountType === "volume") {
    const source = mountSpec.source;
    if (!source) {
      console.error(
        `Error: Volume mount missing required 'source' field: ${JSON.stringify(mountSpec)}`
      );
      process.exit(1);
    }

    const volumeName = mountSpec.global ? source : `${containerName}_${source}`;
    const uid = mountSpec.uid;
    const gid = mountSpec.gid;

    if (uid !== undefined || gid !== undefined) {
      const mountOpts: string[] = [];
      if (uid !== undefined) {
        mountOpts.push(`uid=${uid}`);
      }
      if (gid !== undefined) {
        mountOpts.push(`gid=${gid}`);
      }
      const driverOpts = `o=${mountOpts.join(",")}`;

      const mountParts = [
        "type=volume",
        `source=${volumeName}`,
        `target=${target}`,
        "volume-opt=type=tmpfs",
        "volume-opt=device=tmpfs",
        `"volume-opt=${driverOpts}"`,
      ];
      if (readOnly) {
        mountParts.push("readonly");
      }
      return ["--mount", mountParts.join(",")];
    } else {
      let mountArg = `${volumeName}:${target}`;
      const suffixOpts: string[] = [];
      if (readOnly) {
        suffixOpts.push("ro");
      }
      if (selinux) {
        suffixOpts.push(selinux);
      }
      if (suffixOpts.length > 0) {
        mountArg += ":" + suffixOpts.join(",");
      }
      return ["-v", mountArg];
    }
  } else {
    console.error(
      `Error: Unknown mount type '${mountType}'. Must be 'bind', 'volume', or 'anonymous'`
    );
    process.exit(1);
  }
}
