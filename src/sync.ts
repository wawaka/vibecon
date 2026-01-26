import { spawnSync, spawn } from "child_process";
import * as fs from "fs";
import * as os from "os";
import * as path from "path";

export function syncClaudeConfig(containerName: string): void {
  const claudeDir = path.join(os.homedir(), ".claude");
  const containerClaudeDir = "/home/node/.claude";
  const settingsFile = path.join(claudeDir, "settings.json");
  const claudeMdFile = path.join(claudeDir, "CLAUDE.md");

  const filesToCopy: string[] = [];
  let containerSettings: Record<string, unknown> = {};

  if (fs.existsSync(settingsFile)) {
    try {
      const content = fs.readFileSync(settingsFile, "utf-8");
      const settings = JSON.parse(content);

      if (settings.statusLine) {
        containerSettings.statusLine = settings.statusLine;

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

  spawnSync(
    "docker",
    ["exec", containerName, "mkdir", "-p", containerClaudeDir],
    { stdio: ["pipe", "pipe", "pipe"] }
  );

  if (fs.existsSync(claudeMdFile)) {
    filesToCopy.push(claudeMdFile);
  } else {
    spawnSync(
      "docker",
      ["exec", containerName, "rm", "-f", `${containerClaudeDir}/CLAUDE.md`],
      { stdio: ["pipe", "pipe", "pipe"] }
    );
  }

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
    spawnSync(
      "docker",
      ["exec", containerName, "rm", "-rf", `${containerClaudeDir}/commands`],
      { stdio: ["pipe", "pipe", "pipe"] }
    );
    spawnSync(
      "docker",
      ["exec", containerName, "mkdir", "-p", `${containerClaudeDir}/commands`],
      { stdio: ["pipe", "pipe", "pipe"] }
    );

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

    tarCreate.on("close", () => {});
    tarExtract.on("close", (code) => {
      if (code !== 0) {
        console.log("Warning: Failed to copy commands directory");
      }
    });
  } else {
    spawnSync(
      "docker",
      ["exec", containerName, "rm", "-rf", `${containerClaudeDir}/commands`],
      { stdio: ["pipe", "pipe", "pipe"] }
    );
  }

  if (filesToCopy.length > 0) {
    const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "vibecon-"));
    try {
      for (const srcFile of filesToCopy) {
        const destPath = path.join(tmpDir, path.basename(srcFile));
        fs.copyFileSync(srcFile, destPath);
        try {
          const srcStats = fs.statSync(srcFile);
          if (srcStats.mode & 0o111) {
            fs.chmodSync(destPath, srcStats.mode | 0o111);
          }
        } catch {
          // Ignore permission errors
        }
      }

      const tarCreate = spawn("tar", ["-cf", "-", "."], {
        cwd: tmpDir,
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
          containerClaudeDir,
        ],
        { stdio: ["pipe", "pipe", "pipe"] }
      );
      tarCreate.stdout.pipe(tarExtract.stdin);
    } finally {
      setTimeout(() => {
        try {
          fs.rmSync(tmpDir, { recursive: true });
        } catch {
          // Ignore cleanup errors
        }
      }, 1000);
    }
  }

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

  spawnSync(
    "docker",
    [
      "exec",
      "-u",
      "root",
      containerName,
      "chown",
      "-R",
      "node:node",
      containerClaudeDir,
    ],
    { stdio: ["pipe", "pipe", "pipe"] }
  );
}
