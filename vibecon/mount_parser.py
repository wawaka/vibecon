"""Mount parsing functionality for Vibecon."""

import os
import sys
from typing import Dict, List, Any, Tuple, Optional


class MountParser:
    """Parses mount specifications into Docker mount arguments."""
    
    @staticmethod
    def parse_mount(mount_spec: Dict[str, Any], project_root: str, container_name: str) -> List[str]:
        """Parse mount spec into docker mount arguments.

        Returns a list of docker arguments, e.g., ["-v", "..."] or ["--mount", "..."]

        All mounts must be objects with explicit type. Supported types:

        1. type="bind" - Bind mount from host to container
           Required: type, source, target
           Optional: read_only (bool), selinux ("z" or "Z")

        2. type="volume" - Named Docker volume
           Required: type, source (volume name), target
           Optional: read_only (bool), uid (int), gid (int), selinux ("z" or "Z"), global (bool)

        3. type="anonymous" - Anonymous Docker volume
           Required: type, target
           Optional: read_only (bool), uid (int), gid (int)
        """
        if isinstance(mount_spec, str):
            print(f"Error: Mount must be an object with explicit 'type' field, got string: {mount_spec}")
            sys.exit(1)

        if not isinstance(mount_spec, dict):
            print(f"Error: Mount must be an object, got: {type(mount_spec).__name__}")
            sys.exit(1)

        mount_type = mount_spec.get("type")
        if not mount_type:
            print(f"Error: Mount missing required 'type' field: {mount_spec}")
            sys.exit(1)

        target = mount_spec.get("target")
        if not target:
            print(f"Error: Mount missing required 'target' field: {mount_spec}")
            sys.exit(1)

        read_only = mount_spec.get("read_only", False)
        selinux = mount_spec.get("selinux")  # "z" or "Z"

        if mount_type == "anonymous":
            return MountParser._parse_anonymous_mount(mount_spec, target, read_only)
        elif mount_type == "bind":
            return MountParser._parse_bind_mount(mount_spec, target, project_root, read_only, selinux)
        elif mount_type == "volume":
            return MountParser._parse_volume_mount(mount_spec, target, container_name, read_only, selinux)
        else:
            print(f"Error: Unknown mount type '{mount_type}'. Must be 'bind', 'volume', or 'anonymous'")
            sys.exit(1)

    @staticmethod
    def _parse_anonymous_mount(mount_spec: Dict[str, Any], target: str, read_only: bool) -> List[str]:
        """Parse anonymous volume mount."""
        uid = mount_spec.get("uid")
        gid = mount_spec.get("gid")

        if uid is not None or gid is not None:
            # Use --mount syntax with tmpfs-backed volume for uid/gid support
            mount_opts = []
            if uid is not None:
                mount_opts.append(f"uid={uid}")
            if gid is not None:
                mount_opts.append(f"gid={gid}")
            driver_opts = f"o={','.join(mount_opts)}"

            mount_parts = [
                "type=volume",
                f"target={target}",
                "volume-opt=type=tmpfs",
                "volume-opt=device=tmpfs",
                f'"volume-opt={driver_opts}"',
            ]
            if read_only:
                mount_parts.append("readonly")
            return ["--mount", ",".join(mount_parts)]
        else:
            return ["-v", target]

    @staticmethod
    def _parse_bind_mount(mount_spec: Dict[str, Any], target: str, project_root: str, 
                         read_only: bool, selinux: Optional[str]) -> List[str]:
        """Parse bind mount."""
        source = mount_spec.get("source")
        if not source:
            print(f"Error: Bind mount missing required 'source' field: {mount_spec}")
            sys.exit(1)

        # Resolve source path
        resolved = os.path.expanduser(source)
        if not os.path.isabs(resolved):
            resolved = os.path.normpath(os.path.join(project_root, resolved))
        if not os.path.exists(resolved):
            print(f"Warning: bind mount source does not exist: {resolved}")

        # uid/gid not supported for bind mounts
        if mount_spec.get("uid") or mount_spec.get("gid"):
            print(f"Warning: uid/gid options ignored for bind mount (not supported by Docker)")

        mount_arg = f"{resolved}:{target}"
        suffix_opts = []
        if read_only:
            suffix_opts.append("ro")
        if selinux:
            suffix_opts.append(selinux)
        if suffix_opts:
            mount_arg += ":" + ",".join(suffix_opts)
        return ["-v", mount_arg]

    @staticmethod
    def _parse_volume_mount(mount_spec: Dict[str, Any], target: str, container_name: str,
                           read_only: bool, selinux: Optional[str]) -> List[str]:
        """Parse named volume mount."""
        source = mount_spec.get("source")
        if not source:
            print(f"Error: Volume mount missing required 'source' field: {mount_spec}")
            sys.exit(1)

        # Determine volume name based on global flag
        if mount_spec.get("global", False):
            volume_name = source
        else:
            # Local volume - prefix with container name
            volume_name = f"{container_name}_{source}"

        uid = mount_spec.get("uid")
        gid = mount_spec.get("gid")

        # If uid/gid specified, use --mount syntax with tmpfs-backed volume
        if uid is not None or gid is not None:
            mount_opts = []
            if uid is not None:
                mount_opts.append(f"uid={uid}")
            if gid is not None:
                mount_opts.append(f"gid={gid}")
            driver_opts = f"o={','.join(mount_opts)}"

            mount_parts = [
                "type=volume",
                f"source={volume_name}",
                f"target={target}",
                "volume-opt=type=tmpfs",
                "volume-opt=device=tmpfs",
                f'"volume-opt={driver_opts}"',
            ]
            if read_only:
                mount_parts.append("readonly")
            return ["--mount", ",".join(mount_parts)]
        else:
            # Simple -v syntax
            mount_arg = f"{volume_name}:{target}"
            suffix_opts = []
            if read_only:
                suffix_opts.append("ro")
            if selinux:
                suffix_opts.append(selinux)
            if suffix_opts:
                mount_arg += ":" + ",".join(suffix_opts)
            return ["-v", mount_arg]