import { exec } from "child_process";
import { spawnSync } from "child_process";
import type { Versions } from "./types.js";

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

export async function getAllVersions(): Promise<Versions> {
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

export function makeCompositeTag(versions: Versions): string {
  return `g${versions.g}_oac${versions.oac}_go${versions.go}`;
}

export function buildImage(
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
