#!/usr/bin/env bun
/**
 * OpenDerisk CLI Launcher (Bun Edition)
 * 
 * Fast, TypeScript-native wrapper for OpenDerisk
 */

import { spawn } from "child_process";
import { join, dirname } from "path";
import { existsSync, mkdirSync } from "fs";
import { homedir } from "os";

const INSTALL_DIR = process.env.OPENDERISK_INSTALL_DIR || join(homedir(), ".openderisk");
const REPO_URL = "https://github.com/derisk-ai/OpenDerisk.git";

// Colors
const colors = {
  reset: "\x1b[0m",
  red: "\x1b[31m",
  green: "\x1b[32m",
  yellow: "\x1b[33m",
  blue: "\x1b[34m",
  cyan: "\x1b[36m"
};

const log = (msg: string) => console.log(`${colors.blue}[OpenDerisk]${colors.reset} ${msg}`);
const warn = (msg: string) => console.log(`${colors.yellow}[Warning]${colors.reset} ${msg}`);
const error = (msg: string) => {
  console.error(`${colors.red}[Error]${colors.reset} ${msg}`);
  process.exit(1);
};
const success = (msg: string) => console.log(`${colors.green}[Success]${colors.reset} ${msg}`);

const commandExists = (cmd: string): boolean => {
  try {
    Bun.spawnSync(["which", cmd], { stdout: "ignore" });
    return true;
  } catch {
    return false;
  }
};

const ensureUv = async (): Promise<void> => {
  if (commandExists("uv")) {
    log("uv is already installed");
    return;
  }

  log("Installing uv (Python package manager)...");
  const proc = Bun.spawn([
    "bash", "-c",
    "curl -LsSf https://astral.sh/uv/install.sh | sh"
  ], { stdio: ["inherit", "inherit", "inherit"] });

  await proc.exited;
  
  if (proc.exitCode !== 0) {
    error("Failed to install uv");
  }
  success("uv installed successfully");
};

const ensureRepo = async (): Promise<void> => {
  if (existsSync(join(INSTALL_DIR, ".git"))) {
    log("OpenDerisk already installed, updating...");
    const proc = Bun.spawn(
      ["git", "pull", "origin", "main"],
      { cwd: INSTALL_DIR, stdout: "pipe", stderr: "pipe" }
    );
    await proc.exited;
    return;
  }

  log("Installing OpenDerisk...");
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
    error("Failed to clone repository");
  }
  success("OpenDerisk repository cloned");
};

const installDeps = async (): Promise<void> => {
  log("Installing Python dependencies...");
  
  const extras = [
    "base", "proxy_openai", "rag", "storage_chromadb",
    "derisks", "storage_oss2", "client", "ext_base"
  ].map(e => `--extra "${e}"`).join(" ");

  const proc = Bun.spawn(
    ["bash", "-c", `uv sync --all-packages --frozen ${extras}`],
    { 
      cwd: INSTALL_DIR, 
      stdio: ["inherit", "inherit", "inherit"],
      env: {
        ...process.env,
        PATH: `${join(homedir(), ".local/bin")}:${process.env.PATH}`
      }
    }
  );
  
  await proc.exited;
  
  if (proc.exitCode !== 0) {
    error("Failed to install dependencies");
  }
  success("Dependencies installed");
};

const runOpenDerisk = (args: string[]): void => {
  const uvPath = join(homedir(), ".local/bin/uv");
  const uv = existsSync(uvPath) ? uvPath : "uv";
  
  const proc = spawn(uv, ["run", "derisk", ...args], {
    cwd: INSTALL_DIR,
    stdio: "inherit",
    env: process.env
  });

  proc.on("error", (err) => error(`Failed to start: ${err.message}`));
  proc.on("exit", (code) => process.exit(code || 0));
};

const main = async (): Promise<void> => {
  const args = process.argv.slice(2);

  // Help
  if (args.includes("--help") || args.includes("-h")) {
    console.log(`
${colors.cyan}OpenDerisk CLI${colors.reset}

Usage: openderisk [options] [command]

Options:
  -h, --help     Show this help message
  -v, --version  Show version information
  --update       Update to latest version

Commands:
  server         Start OpenDerisk server
  
For more information: https://github.com/derisk-ai/OpenDerisk
    `);
    return;
  }

  // Version
  if (args.includes("--version") || args.includes("-v")) {
    console.log("OpenDerisk v0.2.0 (Bun Edition)");
    return;
  }

  // Update
  if (args.includes("--update")) {
    await ensureUv();
    await ensureRepo();
    await installDeps();
    success("OpenDerisk updated successfully!");
    return;
  }

  // First run setup
  if (!existsSync(INSTALL_DIR)) {
    await ensureUv();
    await ensureRepo();
    await installDeps();
  }

  // Run
  runOpenDerisk(args);
};

main().catch(error);
