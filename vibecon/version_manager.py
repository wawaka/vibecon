"""Version management and image building for Vibecon."""

import asyncio
import json
import subprocess
import sys
from typing import Dict, List, Any, Optional


class VersionManager:
    """Manages version checking and Docker image building for Vibecon."""
    
    def __init__(self):
        pass
    
    async def get_npm_package_version_async(self, package_name: str, short_name: str) -> Optional[str]:
        """Get the latest version of an npm package asynchronously."""
        proc = await asyncio.create_subprocess_exec(
            "npm", "view", package_name, "version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode == 0:
            return stdout.decode().strip()
        else:
            print(f"Warning: Failed to get {short_name} version from npm")
            return None

    async def get_go_version_async(self) -> Optional[str]:
        """Get the latest stable Go version from golang.org."""
        proc = await asyncio.create_subprocess_exec(
            "curl", "-s", "https://go.dev/dl/?mode=json",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode == 0:
            try:
                releases = json.loads(stdout.decode())
                # First stable release in the list
                for release in releases:
                    if release.get("stable", False):
                        # Version is like "go1.24.2", strip the "go" prefix
                        return release["version"].lstrip("go")
            except (json.JSONDecodeError, KeyError, IndexError):
                pass
        print("Warning: Failed to get Go version from golang.org")
        return None

    def get_all_versions(self) -> Dict[str, str]:
        """Get versions of all AI CLI tools from npm and Go from golang.org concurrently."""
        print("Checking latest versions...")

        packages = [
            ("@google/gemini-cli", "g", "Gemini CLI"),
            ("@openai/codex", "oac", "OpenAI Codex"),
        ]

        async def fetch_all():
            npm_tasks = [self.get_npm_package_version_async(pkg, short) for pkg, short, _ in packages]
            go_task = self.get_go_version_async()
            all_tasks = npm_tasks + [go_task]
            return await asyncio.gather(*all_tasks)

        results = asyncio.run(fetch_all())

        # npm package results
        npm_results = results[:-1]
        go_result = results[-1]

        versions = {}
        for (_, short_name, display_name), version in zip(packages, npm_results):
            if version:
                versions[short_name] = version
                print(f"  {display_name}: {version}")
            else:
                versions[short_name] = "latest"
                print(f"  {display_name}: latest (failed to fetch)")

        # Go version
        if go_result:
            versions["go"] = go_result
            print(f"  Go: {go_result}")
        else:
            versions["go"] = "1.24.2"  # fallback
            print(f"  Go: 1.24.2 (failed to fetch, using fallback)")

        return versions

    def make_composite_tag(self, versions: Dict[str, str]) -> str:
        """Create composite tag from versions: g{ver}_oac{ver}_go{ver}."""
        return f"g{versions['g']}_oac{versions['oac']}_go{versions['go']}"

    def build_image(self, vibecon_root: str, image_name: str, versions: Optional[Dict[str, str]] = None) -> str:
        """Build the Docker image with all AI CLI tools and Go."""
        if versions is None:
            versions = {"g": "latest", "oac": "latest", "go": "1.24.2"}

        composite_tag = self.make_composite_tag(versions)
        print(f"Building image with composite tag: {composite_tag}")

        # Build command with all version build args
        build_cmd = [
            "docker", "build",
            "--build-arg", f"GEMINI_CLI_VERSION={versions['g']}",
            "--build-arg", f"OPENAI_CODEX_VERSION={versions['oac']}",
            "--build-arg", f"GO_VERSION={versions['go']}",
            "-t", image_name,
            "-t", f"vibecon:{composite_tag}"
        ]

        print(f"Tagging as: {image_name} and vibecon:{composite_tag}")

        build_cmd.append(".")

        build_result = subprocess.run(build_cmd, cwd=vibecon_root)
        if build_result.returncode != 0:
            print("Failed to build image")
            sys.exit(1)

        return composite_tag