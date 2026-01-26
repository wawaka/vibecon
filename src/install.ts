import * as fs from "fs";
import * as os from "os";
import * as path from "path";
import { colors } from "./utils.js";

const { RESET, BOLD, RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN } = colors;

export function installSymlink(simulatePathMissing = false): void {
  const scriptPath = fs.realpathSync(process.argv[1]);
  const installDir = path.join(os.homedir(), ".local", "bin");
  const symlinkPath = path.join(installDir, "vibecon");

  const homeStr = os.homedir();
  const installDirDisplay = installDir.startsWith(homeStr)
    ? "$HOME" + installDir.slice(homeStr.length)
    : installDir;

  fs.mkdirSync(installDir, { recursive: true });

  let alreadyInstalled = false;
  try {
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
    try {
      fs.unlinkSync(symlinkPath);
    } catch {
      // File doesn't exist, that's fine
    }

    fs.symlinkSync(scriptPath, symlinkPath);
    console.log(
      `${GREEN}Installed:${RESET} ${CYAN}${symlinkPath}${RESET} -> ${BLUE}${scriptPath}${RESET}`
    );
  }

  const pathEnv = process.env.PATH || "";
  if (
    simulatePathMissing ||
    !pathEnv.split(path.delimiter).includes(installDir)
  ) {
    const shellPath = process.env.SHELL || "";
    const shellName = shellPath ? path.basename(shellPath) : "unknown";

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
    console.log(
      `  ${MAGENTA}Detected shell:${RESET} ${BOLD}${shellName}${RESET}`
    );
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

export function uninstallSymlink(): void {
  const symlinkPath = path.join(os.homedir(), ".local", "bin", "vibecon");

  try {
    fs.unlinkSync(symlinkPath);
    console.log(`Uninstalled: ${symlinkPath}`);
  } catch {
    console.log(`Symlink not found: ${symlinkPath}`);
  }
}
