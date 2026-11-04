"use strict";
const { app, BrowserWindow, shell, ipcMain, Menu } = require("electron");
const fs = require("node:fs");
const path = require("node:path");
const { normalizeServerUrl, isInternal } = require("./lib/url");

const DEFAULT_URL = "http://localhost:3000";
const cfgFile = () => path.join(app.getPath("userData"), "config.json");
function loadUrl() {
  try { return normalizeServerUrl(JSON.parse(fs.readFileSync(cfgFile(), "utf8")).serverUrl) || DEFAULT_URL; } catch { return DEFAULT_URL; }
}
function saveUrl(u) { fs.writeFileSync(cfgFile(), JSON.stringify({ serverUrl: u })); }

let win, serverUrl;
function create() {
  serverUrl = loadUrl();
  win = new BrowserWindow({
    width: 1280, height: 860, minWidth: 900, minHeight: 600, title: "AutoJobApply",
    webPreferences: { contextIsolation: true, nodeIntegration: false, sandbox: true, preload: path.join(__dirname, "preload.js") },
  });
  // Only the configured server is loaded in-app; everything else opens in the default browser.
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:/.test(url)) shell.openExternal(url);
    return { action: "deny" };
  });
  win.webContents.on("will-navigate", (e, url) => {
    if (!isInternal(url, serverUrl) && !url.startsWith("file:")) { e.preventDefault(); if (/^https?:/.test(url)) shell.openExternal(url); }
  });
  win.webContents.on("did-fail-load", (_e, code, _d, _u, isMain) => {
    if (isMain && code !== -3) win.loadFile(path.join(__dirname, "offline.html"), { query: { server: serverUrl } });
  });
  win.loadURL(serverUrl);
}
ipcMain.handle("get-server", () => serverUrl);
ipcMain.handle("set-server", (_e, raw) => {
  const u = normalizeServerUrl(raw);
  if (!u) return { ok: false, error: "Use an https:// address (or http://localhost)." };
  saveUrl(u); serverUrl = u; win.loadURL(u); return { ok: true };
});
ipcMain.handle("retry", () => { win.loadURL(serverUrl); });
ipcMain.handle("open-settings", () => win.loadFile(path.join(__dirname, "settings.html")));

if (!app.requestSingleInstanceLock()) app.quit();
else app.whenReady().then(() => {
  Menu.setApplicationMenu(Menu.buildFromTemplate([
    { label: "App", submenu: [{ label: "Server settings", click: () => win.loadFile(path.join(__dirname, "settings.html")) }, { role: "reload" }, { role: "quit" }] },
    { role: "editMenu" }, { role: "viewMenu" },
  ]));
  create();
});
app.on("window-all-closed", () => app.quit());
