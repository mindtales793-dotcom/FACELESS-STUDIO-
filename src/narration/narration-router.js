"use strict";

const express = require("express");
const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");
const { NarrationEngine } = require("./narration-engine");

function createNarrationRouter(options = {}) {
  const router = express.Router();
  const engine = options.engine || new NarrationEngine(options);
  const jobs = new Map();

  // POST /generate — inicia job e retorna imediatamente o ID.
  router.post("/generate", (req, res) => {
    const { text, referenceId, model, format, concurrency } = req.body || {};
    if (!text || !referenceId) {
      return res.status(400).json({
        error: "Envie text e referenceId."
      });
    }

    const id = crypto.randomUUID();
    const controller = new AbortController();
    const job = {
      id,
      status: "queued",
      createdAt: new Date().toISOString(),
      events: [],
      listeners: new Set(),
      controller,
      result: null,
      error: null
    };

    const publish = event => {
      const payload = {
        jobId: id,
        timestamp: new Date().toISOString(),
        ...event
      };
      job.events.push(payload);
      if (job.events.length > 500) job.events.shift();
      for (const listener of job.listeners) listener(payload);
    };

    jobs.set(id, job);
    res.status(202).json({
      jobId: id,
      statusUrl: `/api/narration/${id}`,
      eventsUrl: `/api/narration/${id}/events`,
      cancelUrl: `/api/narration/${id}`
    });

    job.status = "running";
    publish({ type: "queued" });

    engine.generate({
      text,
      referenceId,
      model,
      format: format || "mp3",
      concurrency,
      signal: controller.signal,
      onEvent: publish
    }).then(result => {
      job.status = "completed";
      job.result = result;
      publish({ type: "job-completed", result: {
        fileName: result.fileName,
        totalBlocks: result.totalBlocks,
        cacheHits: result.cacheHits
      }});
    }).catch(error => {
      job.status = controller.signal.aborted ? "cancelled" : "failed";
      job.error = error.message;
      publish({ type: "job-error", status: job.status, error: error.message });
    });
  });

  // GET /:id — consulta estado.
  router.get("/:id", (req, res) => {
    const job = jobs.get(req.params.id);
    if (!job) return res.status(404).json({ error: "Trabalho não encontrado." });

    res.json({
      jobId: job.id,
      status: job.status,
      createdAt: job.createdAt,
      result: job.result ? {
        fileName: job.result.fileName,
        totalBlocks: job.result.totalBlocks,
        cacheHits: job.result.cacheHits
      } : null,
      error: job.error
    });
  });

  // GET /:id/events — atualizações em tempo real via Server-Sent Events.
  router.get("/:id/events", (req, res) => {
    const job = jobs.get(req.params.id);
    if (!job) return res.status(404).json({ error: "Trabalho não encontrado." });

    res.writeHead(200, {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      "Connection": "keep-alive",
      "X-Accel-Buffering": "no"
    });
    res.write("retry: 2000\n\n");

    const send = event => {
      res.write(`data: ${JSON.stringify(event)}\n\n`);
    };

    for (const event of job.events) send(event);
    job.listeners.add(send);

    const heartbeat = setInterval(() => res.write(": ping\n\n"), 15000);
    req.on("close", () => {
      clearInterval(heartbeat);
      job.listeners.delete(send);
    });
  });

  // DELETE /:id — cancela o trabalho.
  router.delete("/:id", (req, res) => {
    const job = jobs.get(req.params.id);
    if (!job) return res.status(404).json({ error: "Trabalho não encontrado." });
    if (["completed", "failed", "cancelled"].includes(job.status)) {
      return res.json({ jobId: job.id, status: job.status });
    }

    job.controller.abort();
    job.status = "cancelled";
    res.json({ jobId: job.id, status: "cancelling" });
  });

  // GET /:id/download — baixa a narração final.
  router.get("/:id/download", (req, res) => {
    const job = jobs.get(req.params.id);
    if (!job) return res.status(404).json({ error: "Trabalho não encontrado." });
    if (job.status !== "completed" || !job.result?.audioPath) {
      return res.status(409).json({ error: "A narração ainda não está pronta." });
    }

    const file = path.resolve(job.result.audioPath);
    if (!fs.existsSync(file)) {
      return res.status(404).json({ error: "Arquivo de áudio não encontrado." });
    }

    res.download(file, job.result.fileName);
  });

  return router;
}

module.exports = { createNarrationRouter };