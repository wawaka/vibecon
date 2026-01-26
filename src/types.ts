export interface MountSpec {
  type: "bind" | "volume" | "anonymous";
  source?: string;
  target: string;
  read_only?: boolean;
  selinux?: "z" | "Z";
  uid?: number;
  gid?: number;
  global?: boolean;
}

export interface VibeconConfig {
  mounts: MountSpec[];
}

export interface Versions {
  g: string;
  oac: string;
  go: string;
}

export interface GitUserInfo {
  name: string;
  email: string;
}
