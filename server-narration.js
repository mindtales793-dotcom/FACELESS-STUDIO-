"use strict";

const path = require("node:path");

// Lê .env.narration primeiro e depois .env (dotenv não sobrescreve o que já foi definido).
// Assim não é preciso copiar .env.narration por cima do .env do Python.
require("dotenv").config({ path: path.join(__dirname, ".env.narration") });
require("dotenv").config();

const express = require("express");
const { createNarrationRouter } = require("./src/narration/narration-router");

const app = express();

// Middleware de autenticação opcional - adapte ao seu app
// Exemplo: app.use("/api/narration", verificarToken);
app.use(express.json({ limit: "10mb" }));

// Health check do serviço de narração (DEVE vir antes do router para não conflitar com /:id)
app.get("/api/narration/health", (req, res) => {
  res.json({
    ok: true,
    service: "darkcut-narration",
    version: "1.0.0",
    fishAudio: !!process.env.FISH_API_KEY,
    concurrency: Number(process.env.NARRATION_CONCURRENCY || 3),
    timestamp: new Date().toISOString()
  });
});

// Rotas de narração (Fish Audio)
app.use("/api/narration", createNarrationRouter());

const port = Number(process.env.PORT || 3115);
app.listen(port, () => {
  console.log(`🎙️ Servidor de narração (DarkCut) rodando em http://127.0.0.1:${port}`);
  console.log(`📋 Endpoints:`);
  console.log(`   POST  /api/narration/generate`);
  console.log(`   GET   /api/narration/:id`);
  console.log(`   GET   /api/narration/:id/events (SSE)`);
  console.log(`   DELETE /api/narration/:id`);
  console.log(`   GET   /api/narration/:id/download`);
  console.log(`   GET   /api/narration/health`);
});
