#!/usr/bin/env node

import { execSync, spawnSync, exec, spawn } from "child_process";
import { createHash } from "crypto";
import * as fs from "fs";
import * as os from "os";
import * as path from "path";
import { Command } from "commander";

// Global configuration
const IMAGE_NAME = "vibecon:latest";
const DEFAULT_COMMAND = ["claude", "--dangerously-skip-permissions"];

// ============================================================================
// Types
// ============================================================================

interface MountSpec {
  type: "bind" | "volume" | "anonymous";
  source?: string;
  target: string;
  read_only?: boolean;
  selinux?: "z" | "Z";
  uid?: number;
  gid?: number;
  global?: boolean;
}

interface VibeconConfig {
  mounts: MountSpec[];
}

interface Versions {
  g: string;
  oac: string;
  go: string;
}

// ============================================================================
// ANSI Colors
// ============================================================================

const RESET = "\x1b[0m";
const BOLD = "\x1b[1m";
const RED = "\x1b[91m";
const GREEN = "\x1b[92m";
const YELLOW = "\x1b[93m";
const BLUE = "\x1b[94m";
const MAGENTA = "\x1b[95m";
const CYAN = "\x1b[96m";

// ============================================================================
// Config file support
// ============================================================================

function loadConfig(configPath: string): Partial<VibeconConfig> {
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

function getMergedConfig(projectRoot: string): VibeconConfig {
  const globalCfg = loadConfig("~/.vibecon.json");
  const projectCfg = loadConfig(path.join(projectRoot, ".vibecon.json"));

  return {
    mounts: [...(globalCfg.mounts || []), ...(projectCfg.mounts || [])],
  };
}

function parseMount(
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
    console.error(
      `Error: Mount must be an object, got: ${typeof mountSpec}`
    );
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
      // Use --mount syntax with tmpfs-backed volume for uid/gid support
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

    // Resolve source path
    let resolved = source.replace(/^~/, os.homedir());
    if (!path.isAbsolute(resolved)) {
      resolved = path.normalize(path.join(projectRoot, resolved));
    }
    if (!fs.existsSync(resolved)) {
      console.log(`Warning: bind mount source does not exist: ${resolved}`);
    }

    // uid/gid not supported for bind mounts
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

    // Determine volume name based on global flag
    const volumeName = mountSpec.global ? source : `${containerName}_${source}`;

    const uid = mountSpec.uid;
    const gid = mountSpec.gid;

    // If uid/gid specified, use --mount syntax with tmpfs-backed volume
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
      // Simple -v syntax
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

// ============================================================================
// Symlink installation
// ============================================================================

function installSymlink(simulatePathMissing = false): void {
  const scriptPath = fs.realpathSync(process.argv[1]);
  const installDir = path.join(os.homedir(), ".local", "bin");
  const symlinkPath = path.join(installDir, "vibecon");

  // Create a display version with $HOME substitution
  const homeStr = os.homedir();
  const installDirDisplay = installDir.startsWith(homeStr)
    ? "$HOME" + installDir.slice(homeStr.length)
    : installDir;

  // Create install directory if it doesn't exist
  fs.mkdirSync(installDir, { recursive: true });

  // Check if symlink already exists and points to the correct target
  let alreadyInstalled = false;
  try {
    const existingTarget = fs.readlinkSync(symlinkPath);
    const resolvedExisting = fs.realpathSync(symlinkPath);
    if (resolvedExisting === scriptPath) {
      alreadyInstalled = true;
      console.log(
        `${GREEN}${BOLD}Already installed:${RESET} ${CYAN}${symlinkPath}${RESET} -> ${BLUE}${scriptPath}${RESET}`
      );
    }
  } catch {
    // Symlink doesn't exist or can't be read
  }

  if (!alreadyInstalled) {
    // Remove existing symlink if it exists but points elsewhere
    try {
      fs.unlinkSync(symlinkPath);
    } catch {
      // File doesn't exist, that's fine
    }

    // Create symlink
    fs.symlinkSync(scriptPath, symlinkPath);
    console.log(
      `${GREEN}Installed:${RESET} ${CYAN}${symlinkPath}${RESET} -> ${BLUE}${scriptPath}${RESET}`
    );
  }

  // Check if install directory is in PATH
  const pathEnv = process.env.PATH || "";
  if (simulatePathMissing || !pathEnv.split(path.delimiter).includes(installDir)) {
    // Detect user's shell
    const shellPath = process.env.SHELL || "";
    const shellName = shellPath ? path.basename(shellPath) : "unknown";

    // Determine config file and export syntax based on shell
    let configFile: string;
    let exportCmd: string;

    if (shellName === "zsh") {
      configFile = "~/.zshrc";
      exportCmd = `export PATH="${installDirDisplay}:$PATH"`;
    } else if (shellName === "bash") {
      configFile = "~/.bashrc";
      exportCmd = `export PATH="${installDirDisplay}:$PATH"`;
    } else if (shellName === "fish") {
      configFile = "~/.config/fish/config.fish";
      exportCmd = `set -gx PATH "${installDirDisplay}" $PATH`;
    } else if (shellName === "tcsh" || shellName === "csh") {
      configFile = "~/.cshrc";
      exportCmd = `setenv PATH "${installDirDisplay}:$PATH"`;
    } else {
      configFile = "~/.profile";
      exportCmd = `export PATH="${installDirDisplay}:$PATH"`;
    }

    // Print large banner warning with colors
    console.log(`\n${RED}${BOLD}${"=".repeat(70)}`);
    console.log(`  Warning: PATH CUSTOMIZATION REQUIRED`);
    console.log(`${"=".repeat(70)}${RESET}`);
    console.log(
      `\n  ${YELLOW}${BOLD}${installDirDisplay}${RESET} ${RED}${BOLD}is NOT in your PATH!${RESET}\n`
    );
    console.log(
      `  You must add it to your PATH to use ${CYAN}${BOLD}'vibecon'${RESET} by name.`
    );
    console.log(`\n${BLUE}${"-".repeat(70)}${RESET}`);
    console.log(`  ${MAGENTA}Detected shell:${RESET} ${BOLD}${shellName}${RESET}`);
    console.log(`${BLUE}${"-".repeat(70)}${RESET}`);
    console.log(`\n  Add to PATH ${GREEN}permanently${RESET}:`);
    console.log(`    ${GREEN}echo '${exportCmd}' >> ${configFile}${RESET}`);
    console.log(`    ${GREEN}source ${configFile}${RESET}`);
    console.log(`\n${RED}${BOLD}${"=".repeat(70)}${RESET}\n`);
  } else {
    console.log(
      `\n${GREEN}${BOLD}✓${RESET} ${GREEN}You can now use vibecon by its name:${RESET} ${CYAN}${BOLD}vibecon${RESET}`
    );
  }
}

function uninstallSymlink(): void {
  const symlinkPath = path.join(os.homedir(), ".local", "bin", "vibecon");

  try {
    fs.unlinkSync(symlinkPath);
    console.log(`Uninstalled: ${symlinkPath}`);
  } catch {
    console.log(`Symlink not found: ${symlinkPath}`);
  }
}

// ============================================================================
// Container operations
// ============================================================================

function isContainerRunning(containerName: string): boolean {
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

function containerExists(containerName: string): boolean {
  try {
    execSync(`docker inspect ${containerName}`, {
      stdio: ["pipe", "pipe", "pipe"],
    });
    return true;
  } catch {
    return false;
  }
}

function restartContainer(containerName: string): boolean {
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

function stopContainer(containerName: string): void {
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

function destroyContainer(containerName: string): void {
  console.log(`Destroying container '${containerName}'...`);
  spawnSync("docker", ["rm", "-f", containerName], {
    stdio: ["pipe", "pipe", "pipe"],
  });
  console.log("Container destroyed.");
}

// ============================================================================
// Vibecon root and container naming
// ============================================================================

function findVibeconRoot(): string | null {
  // Resolve symlink to find actual script location
  const scriptPath = fs.realpathSync(process.argv[1]);
  const scriptDir = path.dirname(scriptPath);
  const dockerfilePath = path.join(scriptDir, "Dockerfile");

  if (fs.existsSync(dockerfilePath)) {
    return scriptDir;
  }
  return null;
}

function generateContainerName(workspacePath: string): string {
  // Create full hash from the workspace path
  const pathHash = createHash("md5")
    .update(workspacePath)
    .digest("hex")
    .slice(0, 8);

  // Sanitize the path for use in container name
  const sanitizedPath = workspacePath
    .replace(/^\//, "")
    .replace(/\//g, "-")
    .replace(/_/g, "-")
    .toLowerCase();

  return `vibecon-${sanitizedPath}-${pathHash}`;
}

// ============================================================================
// Docker image management
// ============================================================================

function imageExists(imageName: string): boolean {
  const result = spawnSync("docker", ["image", "inspect", imageName], {
    encoding: "utf-8",
    stdio: ["pipe", "pipe", "pipe"],
  });

  if (result.status !== 0) {
    const stderr = result.stderr?.toString() || "";
    if (stderr.toLowerCase().includes("no such image")) {
      return false;
    }
    // Some other error occurred
    console.error(`Error checking image: ${stderr.trim()}`);
    process.exit(1);
  }
  return true;
}

async function getNpmPackageVersionAsync(
  packageName: string,
  shortName: string
): Promise<string | null> {
  return new Promise((resolve) => {
    exec(`npm view ${packageName} version`, (error, stdout) => {
      if (error) {
        console.log(`Warning: Failed to get ${shortName} version from npm`);
        resolve(null);
      } else {
        resolve(stdout.trim());
      }
    });
  });
}

async function getGoVersionAsync(): Promise<string | null> {
  return new Promise((resolve) => {
    exec("curl -s https://go.dev/dl/?mode=json", (error, stdout) => {
      if (error) {
        console.log("Warning: Failed to get Go version from golang.org");
        resolve(null);
        return;
      }
      try {
        const releases = JSON.parse(stdout);
        for (const release of releases) {
          if (release.stable) {
            // Version is like "go1.24.2", strip the "go" prefix
            resolve(release.version.replace(/^go/, ""));
            return;
          }
        }
      } catch {
        // JSON parse error
      }
      console.log("Warning: Failed to get Go version from golang.org");
      resolve(null);
    });
  });
}

async function getAllVersions(): Promise<Versions> {
  console.log("Checking latest versions...");

  const packages = [
    { name: "@google/gemini-cli", short: "g", display: "Gemini CLI" },
    { name: "@openai/codex", short: "oac", display: "OpenAI Codex" },
  ];

  const [geminiVersion, codexVersion, goVersion] = await Promise.all([
    getNpmPackageVersionAsync(packages[0].name, packages[0].display),
    getNpmPackageVersionAsync(packages[1].name, packages[1].display),
    getGoVersionAsync(),
  ]);

  const versions: Versions = {
    g: geminiVersion || "latest",
    oac: codexVersion || "latest",
    go: goVersion || "1.24.2",
  };

  // Print versions
  for (const pkg of packages) {
    const version = pkg.short === "g" ? versions.g : versions.oac;
    if (version === "latest") {
      console.log(`  ${pkg.display}: latest (failed to fetch)`);
    } else {
      console.log(`  ${pkg.display}: ${version}`);
    }
  }

  if (versions.go === "1.24.2" && !goVersion) {
    console.log(`  Go: 1.24.2 (failed to fetch, using fallback)`);
  } else {
    console.log(`  Go: ${versions.go}`);
  }

  return versions;
}

function makeCompositeTag(versions: Versions): string {
  return `g${versions.g}_oac${versions.oac}_go${versions.go}`;
}

// ============================================================================
// Environment detection
// ============================================================================

function getHostTimezone(): string {
  // First, try the TZ environment variable
  const tz = process.env.TZ;
  if (tz) {
    return tz;
  }

  // Try reading /etc/timezone (common on Debian/Ubuntu)
  try {
    const content = fs.readFileSync("/etc/timezone", "utf-8");
    const timezone = content.trim();
    if (timezone) {
      return timezone;
    }
  } catch {
    // File doesn't exist or can't be read
  }

  // Try to get timezone from timedatectl (systemd-based systems)
  try {
    const result = execSync("timedatectl show -p Timezone --value", {
      encoding: "utf-8",
      stdio: ["pipe", "pipe", "pipe"],
    });
    const timezone = result.trim();
    if (timezone) {
      return timezone;
    }
  } catch {
    // Command not available or failed
  }

  // Fallback: try to determine from /etc/localtime symlink
  try {
    const target = fs.readlinkSync("/etc/localtime");
    const parts = target.split("/");
    const zoneinfoIdx = parts.indexOf("zoneinfo");
    if (zoneinfoIdx !== -1 && parts.length > zoneinfoIdx + 1) {
      return parts.slice(zoneinfoIdx + 1).join("/");
    }
  } catch {
    // Symlink doesn't exist or can't be read
  }

  // If all else fails, return UTC as default
  return "UTC";
}

function getGitUserInfo(): { name: string; email: string } {
  let userName = "";
  let userEmail = "";

  try {
    userName = execSync("git config --global user.name", {
      encoding: "utf-8",
      stdio: ["pipe", "pipe", "pipe"],
    }).trim();
  } catch {
    // Git config not set
  }

  try {
    userEmail = execSync("git config --global user.email", {
      encoding: "utf-8",
      stdio: ["pipe", "pipe", "pipe"],
    }).trim();
  } catch {
    // Git config not set
  }

  return { name: userName, email: userEmail };
}

// ============================================================================
// Docker image building
// ============================================================================

function buildImage(
  vibeconRoot: string,
  imageName: string,
  versions?: Versions
): string {
  const vers = versions || { g: "latest", oac: "latest", go: "1.24.2" };
  const compositeTag = makeCompositeTag(vers);

  console.log(`Building image with composite tag: ${compositeTag}`);

  const buildCmd = [
    "docker",
    "build",
    "--build-arg",
    `GEMINI_CLI_VERSION=${vers.g}`,
    "--build-arg",
    `OPENAI_CODEX_VERSION=${vers.oac}`,
    "--build-arg",
    `GO_VERSION=${vers.go}`,
    "-t",
    imageName,
    "-t",
    `vibecon:${compositeTag}`,
    ".",
  ];

  console.log(`Tagging as: ${imageName} and vibecon:${compositeTag}`);

  const result = spawnSync(buildCmd[0], buildCmd.slice(1), {
    cwd: vibeconRoot,
    stdio: "inherit",
  });

  if (result.status !== 0) {
    console.error("Failed to build image");
    process.exit(1);
  }

  return compositeTag;
}

// ============================================================================
// Claude config syncing
// ============================================================================

function syncClaudeConfig(containerName: string): void {
  const claudeDir = path.join(os.homedir(), ".claude");
  const containerClaudeDir = "/home/node/.claude";
  const settingsFile = path.join(claudeDir, "settings.json");
  const claudeMdFile = path.join(claudeDir, "CLAUDE.md");

  // Track files to copy
  const filesToCopy: string[] = [];
  let containerSettings: Record<string, unknown> = {};

  // Parse settings.json if it exists
  if (fs.existsSync(settingsFile)) {
    try {
      const content = fs.readFileSync(settingsFile, "utf-8");
      const settings = JSON.parse(content);

      // Extract statusLine section if present
      if (settings.statusLine) {
        containerSettings.statusLine = settings.statusLine;

        // If statusLine has a command, add that file to copy list
        if (settings.statusLine.command) {
          let cmdPath = settings.statusLine.command;
          if (cmdPath.startsWith("~")) {
            cmdPath = os.homedir() + cmdPath.slice(1);
          }
          if (fs.existsSync(cmdPath)) {
            filesToCopy.push(cmdPath);
          }
        }
      }
    } catch (e) {
      console.log(`Warning: Failed to parse settings.json: ${e}`);
    }
  }

  // Ensure container directory exists
  spawnSync(
    "docker",
    ["exec", containerName, "mkdir", "-p", containerClaudeDir],
    { stdio: ["pipe", "pipe", "pipe"] }
  );

  // Handle CLAUDE.md sync: copy if exists locally, remove from container if not
  if (fs.existsSync(claudeMdFile)) {
    filesToCopy.push(claudeMdFile);
  } else {
    // Remove CLAUDE.md from container if it doesn't exist locally
    spawnSync(
      "docker",
      ["exec", containerName, "rm", "-f", `${containerClaudeDir}/CLAUDE.md`],
      { stdio: ["pipe", "pipe", "pipe"] }
    );
  }

  // Handle commands directory sync (may be a symlink)
  const commandsDir = path.join(claudeDir, "commands");
  let commandsSource: string | null = null;
  if (fs.existsSync(commandsDir)) {
    try {
      commandsSource = fs.realpathSync(commandsDir);
      if (!fs.statSync(commandsSource).isDirectory()) {
        commandsSource = null;
      }
    } catch {
      commandsSource = null;
    }
  }

  if (commandsSource) {
    // Remove existing commands directory to ensure clean sync
    spawnSync(
      "docker",
      ["exec", containerName, "rm", "-rf", `${containerClaudeDir}/commands`],
      { stdio: ["pipe", "pipe", "pipe"] }
    );
    // Create fresh commands directory
    spawnSync(
      "docker",
      ["exec", containerName, "mkdir", "-p", `${containerClaudeDir}/commands`],
      { stdio: ["pipe", "pipe", "pipe"] }
    );
    // Copy commands directory using tar
    const tarCreate = spawn("tar", ["-cf", "-", "."], {
      cwd: commandsSource,
      stdio: ["pipe", "pipe", "pipe"],
    });
    const tarExtract = spawn(
      "docker",
      [
        "exec",
        "-i",
        containerName,
        "tar",
        "-xf",
        "-",
        "-C",
        `${containerClaudeDir}/commands`,
      ],
      { stdio: ["pipe", "pipe", "pipe"] }
    );
    tarCreate.stdout.pipe(tarExtract.stdin);

    // Wait for completion
    tarCreate.on("close", () => {});
    tarExtract.on("close", (code) => {
      if (code !== 0) {
        console.log("Warning: Failed to copy commands directory");
      }
    });
  } else {
    // Remove commands directory from container if it doesn't exist locally
    spawnSync(
      "docker",
      ["exec", containerName, "rm", "-rf", `${containerClaudeDir}/commands`],
      { stdio: ["pipe", "pipe", "pipe"] }
    );
  }

  // Copy files using tar if we have any
  if (filesToCopy.length > 0) {
    const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "vibecon-"));
    try {
      for (const srcFile of filesToCopy) {
        const destPath = path.join(tmpDir, path.basename(srcFile));
        fs.copyFileSync(srcFile, destPath);
        // Preserve executable bit
        try {
          const srcStats = fs.statSync(srcFile);
          if (srcStats.mode & 0o111) {
            fs.chmodSync(destPath, srcStats.mode | 0o111);
          }
        } catch {
          // Ignore permission errors
        }
      }

      // Tar and copy all files at once
      const tarCreate = spawn("tar", ["-cf", "-", "."], {
        cwd: tmpDir,
        stdio: ["pipe", "pipe", "pipe"],
      });
      const tarExtract = spawn(
        "docker",
        ["exec", "-i", containerName, "tar", "-xf", "-", "-C", containerClaudeDir],
        { stdio: ["pipe", "pipe", "pipe"] }
      );
      tarCreate.stdout.pipe(tarExtract.stdin);
    } finally {
      // Cleanup temp directory
      setTimeout(() => {
        try {
          fs.rmSync(tmpDir, { recursive: true });
        } catch {
          // Ignore cleanup errors
        }
      }, 1000);
    }
  }

  // Write container settings.json if we have any settings to write
  if (Object.keys(containerSettings).length > 0) {
    const settingsJson = JSON.stringify(containerSettings, null, 2);
    spawnSync(
      "docker",
      [
        "exec",
        containerName,
        "sh",
        "-c",
        `cat > ${containerClaudeDir}/settings.json << 'EOFCONFIG'\n${settingsJson}\nEOFCONFIG`,
      ],
      { stdio: ["pipe", "pipe", "pipe"] }
    );
  }

  // Fix ownership for node user
  spawnSync(
    "docker",
    ["exec", "-u", "root", containerName, "chown", "-R", "node:node", containerClaudeDir],
    { stdio: ["pipe", "pipe", "pipe"] }
  );
}

// ============================================================================
// Container startup
// ============================================================================

function startContainer(
  cwd: string,
  containerName: string,
  imageName: string,
  config?: VibeconConfig
): void {
  const cfg = config || { mounts: [] };
  const hostTerm = process.env.TERM || "xterm-256color";
  const containerHostname = "vibecon";

  // Get git user info from host
  const { name: gitUserName, email: gitUserEmail } = getGitUserInfo();
  if (gitUserName) {
    console.log(`Configuring git user: ${gitUserName} <${gitUserEmail}>`);
  }

  // Get host timezone
  const hostTimezone = getHostTimezone();
  console.log(`Configuring timezone: ${hostTimezone}`);

  console.log(
    `Starting container '${containerName}' with ${cwd} mounted at /workspace...`
  );

  // Build docker run command
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

  // Add git user environment variables if available
  if (gitUserName) {
    dockerCmd.push("-e", `GIT_USER_NAME=${gitUserName}`);
    dockerCmd.push("-e", `GIT_USER_EMAIL=${gitUserEmail}`);
  }

  // Add main workspace volume mount
  dockerCmd.push("-v", `${cwd}:/workspace`);

  // Add extra mounts from config
  for (const mountSpec of cfg.mounts) {
    const mountArgs = parseMount(mountSpec, cwd, containerName);
    dockerCmd.push(...mountArgs);
  }

  // Add image name
  dockerCmd.push(imageName);

  // Start container
  const result = spawnSync(dockerCmd[0], dockerCmd.slice(1), {
    stdio: ["pipe", "pipe", "pipe"],
  });

  if (result.status !== 0) {
    console.error(`Failed to start container: ${result.stderr?.toString()}`);
    process.exit(1);
  }
}

function ensureContainerRunning(
  cwd: string,
  vibeconRoot: string,
  containerName: string,
  imageName: string,
  config?: VibeconConfig
): void {
  if (isContainerRunning(containerName)) {
    return; // Already running, nothing to do
  }

  // Container is not running - check if it exists (stopped/dead)
  if (containerExists(containerName)) {
    // Try to restart the stopped container
    if (restartContainer(containerName)) {
      return; // Successfully restarted
    }
    // Restart failed, remove and recreate
    console.log("Restart failed, removing container and creating a new one...");
    spawnSync("docker", ["rm", "-f", containerName], {
      stdio: ["pipe", "pipe", "pipe"],
    });
  }

  // Build image only if it doesn't exist
  if (!imageExists(imageName)) {
    console.log(`Image '${imageName}' not found, building...`);
    buildImage(vibeconRoot, imageName);
  }
  startContainer(cwd, containerName, imageName, config);
}

// ============================================================================
// Main CLI
// ============================================================================

async function main(): Promise<void> {
  const program = new Command();

  program
    .name("vibecon")
    .description("Persistent Docker container environment for AI coding assistants")
    .argument("[command...]", "command to execute in container")
    .option("-i, --install", "install symlink to ~/.local/bin/vibecon")
    .option("-I", "install with PATH warning simulation (hidden)", undefined)
    .option("-u, --uninstall", "uninstall symlink from ~/.local/bin/vibecon")
    .option("-k, --stop", "stop the container for current workspace")
    .option("-K, --destroy", "destroy and remove the container permanently")
    .option("-b, --build", "rebuild the Docker image (skips if versions unchanged)")
    .option("-B, --force-build", "force rebuild even if image exists")
    .addHelpText(
      "after",
      `
Examples:
  vibecon                    # Start "${DEFAULT_COMMAND.join(" ")}" in container
  vibecon zsh                # Run zsh in container
  vibecon claude             # Run Claude Code in container
  vibecon gemini             # Run Gemini CLI in container
  vibecon codex              # Run OpenAI Codex in container
  vibecon -b                 # Check versions and rebuild if updated
  vibecon -B                 # Force rebuild regardless of versions
  vibecon -k                 # Stop container (can be restarted)
  vibecon -K                 # Destroy container permanently
`
    );

  program.parse();

  const opts = program.opts();
  const args = program.args;

  // Handle install flag
  if (opts.install) {
    installSymlink();
    process.exit(0);
  }

  // Handle install test flag (hidden -I)
  if (opts.I) {
    installSymlink(true);
    process.exit(0);
  }

  // Handle uninstall flag
  if (opts.uninstall) {
    uninstallSymlink();
    process.exit(0);
  }

  const cwd = process.cwd();
  const vibeconRoot = findVibeconRoot();

  if (!vibeconRoot) {
    console.error("Error: Could not find Dockerfile in vibecon directory");
    process.exit(1);
  }

  const containerName = generateContainerName(cwd);

  // Load config files
  const config = getMergedConfig(cwd);

  // Handle build flag - check versions and build only if needed
  if (opts.build || opts.forceBuild) {
    const versions = await getAllVersions();
    const compositeTag = makeCompositeTag(versions);
    const versionedImage = `vibecon:${compositeTag}`;

    if (imageExists(versionedImage) && !opts.forceBuild) {
      console.log(`\nImage already exists: ${versionedImage}`);
      console.log("No rebuild needed - all versions are up to date.");
      console.log("Use -B/--force-build to rebuild anyway.");
    } else {
      if (opts.forceBuild && imageExists(versionedImage)) {
        console.log(`\nForce rebuild requested...`);
      } else {
        console.log(`\nNew versions detected, building image...`);
      }
      buildImage(vibeconRoot, IMAGE_NAME, versions);
      console.log(`\nBuild complete! Image tagged as:`);
      console.log(`  - ${IMAGE_NAME}`);
      console.log(`  - ${versionedImage}`);
    }
    process.exit(0);
  }

  // Handle stop flag
  if (opts.stop) {
    stopContainer(containerName);
    process.exit(0);
  }

  // Handle destroy flag
  if (opts.destroy) {
    destroyContainer(containerName);
    process.exit(0);
  }

  // Get command to execute
  const command = args.length > 0 ? args : DEFAULT_COMMAND;

  // Ensure container is running
  ensureContainerRunning(cwd, vibeconRoot, containerName, IMAGE_NAME, config);

  // Sync claude config before exec
  syncClaudeConfig(containerName);

  // Execute command in container
  const hostTerm = process.env.TERM || "xterm-256color";
  const hostTimezone = getHostTimezone();

  const execResult = spawnSync(
    "docker",
    [
      "exec",
      "-it",
      "-e",
      `TERM=${hostTerm}`,
      "-e",
      "COLORTERM=truecolor",
      "-e",
      `TZ=${hostTimezone}`,
      containerName,
      ...command,
    ],
    { stdio: "inherit" }
  );

  process.exit(execResult.status || 0);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
