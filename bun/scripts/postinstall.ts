#!/usr/bin/env bun
/**
 * Post-install script for OpenDerisk (Bun Edition)
 */

import { spawn } from "child_process";
import { join, dirname } from "path";
import { existsSync, mkdirSync } from "fs";
import { homedir } from "os";

const INSTALL_DIR = process.env.OPENDERISK_INSTALL_DIR || join(homedir(), ".openderisk");
const REPO_URL = "https://github.com/derisk-ai/OpenDerisk.git";

const colors = {
  reset: "\x1b[0m",
  green: "\x1b[32m",
  yellow: "\x1b[33m",
  cyan: "\x1b[36m"
};

const log = (msg: string) => console.log(`${colors.cyan}[openderisk]${colors.reset} ${msg}`);
const success = (msg: string) => console.log(`${colors.green}[openderisk]${colors.reset} ${msg}`);
const warn = (msg: string) => console.log(`${colors.yellow}[openderisk]${colors.reset} ${msg}`);

const commandExists = (cmd: string): boolean => {
  try {
    Bun.spawnSync(["which", cmd], { stdout: "ignore" });
    return true;
  } catch {
    return false;
  }
};

const installUv = async (): Promise<void> => {
  if (commandExists("uv")) return;

  log("Installing uv package manager...");
  const proc = Bun.spawn(
    ["bash", "-c", "curl -LsSf https://astral.sh/uv/install.sh | sh"],
    { stdio: ["inherit", "inherit", "inherit"] }
  );
  await proc.exited;
  
  if (proc.exitCode !== 0) {
    warn("Failed to install uv automatically");
    warn("Please install manually: https://github.com/astral-sh/uv");
  } else {
    success("uv installed successfully");
  }
};

const cloneRepo = async (): Promise<void> => {
  if (existsSync(join(INSTALL_DIR, ".git"))) {
    log("OpenDerisk already exists, skipping clone");
    return;
  }

  log("Cloning OpenDerisk repository...");
  const parentDir = dirname(INSTALL_DIR);
  
  if (!existsSync(parentDir)) {
    mkdirSync(parentDir, { recursive: true });
  }

  const proc = Bun.spawn(
    ["git", "clone", "--depth", "1", REPO_URL, INSTALL_DIR],
    { stdio: ["inherit", "inherit", "inherit"] }
  );
  
  await proc.exited;
  
  if (proc.exitCode !== 0) {
    warn("Failed to clone repository automatically");
    warn(`You can manually clone: git clone ${REPO_URL} ${INSTALL_DIR}`);
  } else {
    success("Repository cloned successfully");
  }
};

const main = async (): Promise<void> => {
  console.log("");
  log("Setting up OpenDerisk with Bun... 🚀");
  console.log("");

  await installUv();
  await cloneRepo();

  console.log("");
  success("Setup complete! 🎉");
  console.log("");
  console.log("Next steps:");
  console.log("  1. Configure API keys in:");
  console.log(`     ${join(INSTALL_DIR, "configs/derisk-proxy-aliyun.toml")}`);
  console.log("  2. Run: openderisk --help");
  console.log("  3. Start server: openderisk-server");
  console.log("");
  console.log("Documentation: https://github.com/derisk-ai/OpenDerisk");
  console.log("");
};

main().catch(console.error);
