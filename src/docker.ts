import { execSync, spawnSync } from "child_process";
import { createHash } from "crypto";
import type { VibeconConfig } from "./types.js";
import { parseMount } from "./config.js";
import { getHostTimezone, getGitUserInfo } from "./utils.js";

export function isContainerRunning(containerName: string): boolean {
  try {
    const result = execSync(
      `docker inspect -f "{{.State.Running}}" ${containerName}`,
      { encoding: "utf-8", stdio: ["pipe", "pipe", "pipe"] }
    );
    return result.trim() === "true";
  } catch {
    return false;
  }
}

export function containerExists(containerName: string): boolean {
  try {
    execSync(`docker inspect ${containerName}`, {
      stdio: ["pipe", "pipe", "pipe"],
    });
    return true;
  } catch {
    return false;
  }
}

export function restartContainer(containerName: string): boolean {
  console.log(
    `Found stopped container '${containerName}', attempting to restart...`
  );
  const result = spawnSync("docker", ["start", containerName], {
    stdio: ["pipe", "pipe", "pipe"],
  });
  if (result.status === 0) {
    console.log(`Container '${containerName}' restarted successfully.`);
    return true;
  } else {
    console.log(
      `Failed to restart container: ${result.stderr?.toString().trim()}`
    );
    return false;
  }
}

export function stopContainer(containerName: string): void {
  console.log(`Stopping container '${containerName}'...`);
  const result = spawnSync("docker", ["stop", containerName], {
    stdio: ["pipe", "pipe", "pipe"],
  });
  if (result.status === 0) {
    console.log("Container stopped.");
  } else {
    console.log("Container was not running.");
  }
}

export function destroyContainer(containerName: string): void {
  console.log(`Destroying container '${containerName}'...`);
  spawnSync("docker", ["rm", "-f", containerName], {
    stdio: ["pipe", "pipe", "pipe"],
  });
  console.log("Container destroyed.");
}

export function generateContainerName(workspacePath: string): string {
  const pathHash = createHash("md5")
    .update(workspacePath)
    .digest("hex")
    .slice(0, 8);

  const sanitizedPath = workspacePath
    .replace(/^\//, "")
    .replace(/\//g, "-")
    .replace(/_/g, "-")
    .toLowerCase();

  return `vibecon-${sanitizedPath}-${pathHash}`;
}

export function imageExists(imageName: string): boolean {
  const result = spawnSync("docker", ["image", "inspect", imageName], {
    encoding: "utf-8",
    stdio: ["pipe", "pipe", "pipe"],
  });

  if (result.status !== 0) {
    const stderr = result.stderr?.toString() || "";
    if (stderr.toLowerCase().includes("no such image")) {
      return false;
    }
    console.error(`Error checking image: ${stderr.trim()}`);
    process.exit(1);
  }
  return true;
}

export function startContainer(
  cwd: string,
  containerName: string,
  imageName: string,
  config?: VibeconConfig
): void {
  const cfg = config || { mounts: [] };
  const hostTerm = process.env.TERM || "xterm-256color";
  const containerHostname = "vibecon";

  const { name: gitUserName, email: gitUserEmail } = getGitUserInfo();
  if (gitUserName) {
    console.log(`Configuring git user: ${gitUserName} <${gitUserEmail}>`);
  }

  const hostTimezone = getHostTimezone();
  console.log(`Configuring timezone: ${hostTimezone}`);

  console.log(
    `Starting container '${containerName}' with ${cwd} mounted at /workspace...`
  );

  const dockerCmd: string[] = [
    "docker",
    "run",
    "-d",
    "--name",
    containerName,
    "--hostname",
    containerHostname,
    "-e",
    `TERM=${hostTerm}`,
    "-e",
    "COLORTERM=truecolor",
    "-e",
    `TZ=${hostTimezone}`,
  ];

  if (gitUserName) {
    dockerCmd.push("-e", `GIT_USER_NAME=${gitUserName}`);
    dockerCmd.push("-e", `GIT_USER_EMAIL=${gitUserEmail}`);
  }

  dockerCmd.push("-v", `${cwd}:/workspace`);

  for (const mountSpec of cfg.mounts) {
    const mountArgs = parseMount(mountSpec, cwd, containerName);
    dockerCmd.push(...mountArgs);
  }

  dockerCmd.push(imageName);

  const result = spawnSync(dockerCmd[0], dockerCmd.slice(1), {
    stdio: ["pipe", "pipe", "pipe"],
  });

  if (result.status !== 0) {
    console.error(`Failed to start container: ${result.stderr?.toString()}`);
    process.exit(1);
  }
}

export function ensureContainerRunning(
  cwd: string,
  vibeconRoot: string,
  containerName: string,
  imageName: string,
  config?: VibeconConfig,
  buildImage?: (root: string, name: string) => string
): void {
  if (isContainerRunning(containerName)) {
    return;
  }

  if (containerExists(containerName)) {
    if (restartContainer(containerName)) {
      return;
    }
    console.log("Restart failed, removing container and creating a new one...");
    spawnSync("docker", ["rm", "-f", containerName], {
      stdio: ["pipe", "pipe", "pipe"],
    });
  }

  if (!imageExists(imageName)) {
    console.log(`Image '${imageName}' not found, building...`);
    if (buildImage) {
      buildImage(vibeconRoot, imageName);
    }
  }
  startContainer(cwd, containerName, imageName, config);
}
