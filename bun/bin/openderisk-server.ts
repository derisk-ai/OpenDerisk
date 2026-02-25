#!/usr/bin/env bun
/**
 * OpenDerisk Server Launcher (Bun Edition)
 */

import { spawn } from "child_process";
import { join } from "path";
import { existsSync } from "fs";
import { homedir } from "os";

const INSTALL_DIR = process.env.OPENDERISK_INSTALL_DIR || join(homedir(), ".openderisk");

const colors = {
  reset: "\x1b[0m",
  red: "\x1b[31m",
  blue: "\x1b[34m"
};

const log = (msg: string) => console.log(`${colors.blue}[OpenDerisk Server]${colors.reset} ${msg}`);
const error = (msg: string) => {
  console.error(`${colors.red}[Error]${colors.reset} ${msg}`);
  process.exit(1);
};

if (!existsSync(INSTALL_DIR)) {
  error("OpenDerisk not installed. Please run: bun install -g openderisk");
}

log("Starting OpenDerisk Server...");

const uvPath = join(homedir(), ".local/bin/uv");
const uv = existsSync(uvPath) ? uvPath : "uv";

const proc = spawn(uv, ["run", "derisk", "start", "webserver", ...process.argv.slice(2)], {
  cwd: INSTALL_DIR,
  stdio: "inherit",
  env: process.env
});

proc.on("error", (err) => error(`Failed to start server: ${err.message}`));
proc.on("exit", (code) => process.exit(code || 0));
