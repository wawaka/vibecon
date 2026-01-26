#!/usr/bin/env bun

import { spawnSync } from "child_process";
import { getMergedConfig } from "./config.js";
import {
  generateContainerName,
  ensureContainerRunning,
  stopContainer,
  destroyContainer,
  imageExists,
} from "./docker.js";
import { getAllVersions, makeCompositeTag, buildImage } from "./versions.js";
import { syncClaudeConfig } from "./sync.js";
import { installSymlink, uninstallSymlink } from "./install.js";
import { findVibeconRoot, getHostTimezone } from "./utils.js";

const IMAGE_NAME = "vibecon:latest";
const DEFAULT_COMMAND = ["claude", "--dangerously-skip-permissions"];

interface Options {
  install?: boolean;
  I?: boolean;
  uninstall?: boolean;
  stop?: boolean;
  destroy?: boolean;
  build?: boolean;
  forceBuild?: boolean;
}

function parseArgs(): { options: Options; command: string[] } {
  const args = process.argv.slice(2);
  const options: Options = {};
  const command: string[] = [];

  for (let i = 0; i < args.length; i++) {
    const arg = args[i];
    if (arg === "-i" || arg === "--install") {
      options.install = true;
    } else if (arg === "-I") {
      options.I = true;
    } else if (arg === "-u" || arg === "--uninstall") {
      options.uninstall = true;
    } else if (arg === "-k" || arg === "--stop") {
      options.stop = true;
    } else if (arg === "-K" || arg === "--destroy") {
      options.destroy = true;
    } else if (arg === "-b" || arg === "--build") {
      options.build = true;
    } else if (arg === "-B" || arg === "--force-build") {
      options.forceBuild = true;
    } else if (arg === "-h" || arg === "--help") {
      printHelp();
      process.exit(0);
    } else if (!arg.startsWith("-")) {
      command.push(...args.slice(i));
      break;
    }
  }

  return { options, command };
}

function printHelp(): void {
  console.log(`Usage: vibecon [options] [command...]

Persistent Docker container environment for AI coding assistants

Arguments:
  command            command to execute in container

Options:
  -i, --install      install symlink to ~/.local/bin/vibecon
  -I                 install with PATH warning simulation (hidden)
  -u, --uninstall    uninstall symlink from ~/.local/bin/vibecon
  -k, --stop         stop the container for current workspace
  -K, --destroy      destroy and remove the container permanently
  -b, --build        rebuild the Docker image (skips if versions unchanged)
  -B, --force-build  force rebuild even if image exists
  -h, --help         display help for command

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
`);
}

async function main(): Promise<void> {
  const { options, command } = parseArgs();

  // Handle install flag
  if (options.install) {
    installSymlink();
    process.exit(0);
  }

  // Handle install test flag (hidden -I)
  if (options.I) {
    installSymlink(true);
    process.exit(0);
  }

  // Handle uninstall flag
  if (options.uninstall) {
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

  // Handle build flag
  if (options.build || options.forceBuild) {
    const versions = await getAllVersions();
    const compositeTag = makeCompositeTag(versions);
    const versionedImage = `vibecon:${compositeTag}`;

    if (imageExists(versionedImage) && !options.forceBuild) {
      console.log(`\nImage already exists: ${versionedImage}`);
      console.log("No rebuild needed - all versions are up to date.");
      console.log("Use -B/--force-build to rebuild anyway.");
    } else {
      if (options.forceBuild && imageExists(versionedImage)) {
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
  if (options.stop) {
    stopContainer(containerName);
    process.exit(0);
  }

  // Handle destroy flag
  if (options.destroy) {
    destroyContainer(containerName);
    process.exit(0);
  }

  // Get command to execute
  const execCommand = command.length > 0 ? command : DEFAULT_COMMAND;

  // Ensure container is running
  ensureContainerRunning(
    cwd,
    vibeconRoot,
    containerName,
    IMAGE_NAME,
    config,
    buildImage
  );

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
      ...execCommand,
    ],
    { stdio: "inherit" }
  );

  process.exit(execResult.status || 0);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
