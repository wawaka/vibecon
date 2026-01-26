import { execSync } from "child_process";
import * as fs from "fs";
import * as path from "path";
import type { GitUserInfo } from "./types.js";

// ANSI color codes
export const colors = {
  RESET: "\x1b[0m",
  BOLD: "\x1b[1m",
  RED: "\x1b[91m",
  GREEN: "\x1b[92m",
  YELLOW: "\x1b[93m",
  BLUE: "\x1b[94m",
  MAGENTA: "\x1b[95m",
  CYAN: "\x1b[96m",
} as const;

export function getHostTimezone(): string {
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

export function getGitUserInfo(): GitUserInfo {
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

export function findVibeconRoot(): string | null {
  // Use import.meta.dir for Bun, fall back to dirname for compiled
  let scriptDir: string;

  if (typeof Bun !== "undefined") {
    // Running with Bun - use import.meta.dir
    scriptDir = import.meta.dir;
  } else {
    // Compiled binary or Node.js - resolve from argv
    const scriptPath = fs.realpathSync(process.argv[1]);
    scriptDir = path.dirname(scriptPath);
  }

  // Check for Dockerfile in script directory
  const dockerfilePath = path.join(scriptDir, "Dockerfile");
  if (fs.existsSync(dockerfilePath)) {
    return scriptDir;
  }

  // Try parent directory (for when running from src/ subdirectory)
  const parentDir = path.dirname(scriptDir);
  const parentDockerfile = path.join(parentDir, "Dockerfile");
  if (fs.existsSync(parentDockerfile)) {
    return parentDir;
  }

  return null;
}
