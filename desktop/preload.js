"use strict";
const { contextBridge, ipcRenderer } = require("electron");
contextBridge.exposeInMainWorld("desktop", {
  getServer: () => ipcRenderer.invoke("get-server"),
  setServer: (u) => ipcRenderer.invoke("set-server", u),
  retry: () => ipcRenderer.invoke("retry"),
  openSettings: () => ipcRenderer.invoke("open-settings"),
});
