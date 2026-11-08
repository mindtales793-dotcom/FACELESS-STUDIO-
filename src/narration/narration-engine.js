"use strict";

const fs = require("node:fs");
const path = require("node:path");
const os = require("node:os");
const crypto = require("node:crypto");
const { spawn } = require("node:child_process");

const FISH_TTS_URL = "https://api.fish.audio/v1/tts";

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true });
}

function hashKey({ text, referenceId, model, format }) {
  return crypto.createHash("sha256")
    .update(JSON.stringify({ text, referenceId, model, format }))
    .digest("hex");
}

/**
 * Divide por frases e parágrafos, sem cortar palavras.
 * maxChars é um alvo; uma frase maior que o alvo é dividida por palavras.
 */
function splitTextIntoBlocks(input, maxChars = 450) {
  const text = String(input || "").replace(/\r\n/g, "\n").trim();
  if (!text) return [];

  const paragraphs = text.split(/\n{2,}/);
  const blocks = [];
  let current = "";

  function flush() {
    if (current.trim()) blocks.push(current.trim());
    current = "";
  }

  function addSentence(sentence) {
    const s = sentence.trim();
    if (!s) return;

    if (s.length > maxChars) {
      flush();
      const words = s.split(/\s+/);
      let part = "";
      for (const word of words) {
        if (part && (part.length + 1 + word.length > maxChars)) {
          blocks.push(part);
          part = "";
        }
        part += (part ? " " : "") + word;
      }
      if (part) blocks.push(part);
      return;
    }

    if (current && current.length + 1 + s.length > maxChars) flush();
    current += (current ? " " : "") + s;
  }

  for (const paragraph of paragraphs) {
    // Mantém pontuação ao separar sentenças.
    const sentences = paragraph.match(/[^.!?…]+(?:[.!?…]+["'”’)]*)?|[^.!?…]+$/g) || [paragraph];
    for (const sentence of sentences) addSentence(sentence);
    flush(); // preserva a separação entre parágrafos
  }

  flush();
  return blocks;
}

function sleep(ms, signal) {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) return reject(new Error("Geração cancelada."));
    const timer = setTimeout(resolve, ms);
    signal?.addEventListener("abort", () => {
      clearTimeout(timer);
      reject(new Error("Geração cancelada."));
    }, { once: true });
  });
}

async function requestFishAudio({
  text, referenceId, apiKey, model, format = "mp3", signal
}) {
  const response = await fetch(FISH_TTS_URL, {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${apiKey}`,
      "Content-Type": "application/json",
      "model": model
    },
    body: JSON.stringify({
      text,
      reference_id: referenceId,
      format
    }),
    signal
  });

  if (!response.ok) {
    const body = await response.text().catch(() => "");
    const error = new Error(`Fish Audio respondeu HTTP ${response.status}: ${body.slice(0, 1200)}`);
    error.status = response.status;
    error.retryAfter = Number(response.headers.get("retry-after")) || null;
    throw error;
  }

  const buffer = Buffer.from(await response.arrayBuffer());
  if (!buffer.length) throw new Error("Fish Audio retornou um áudio vazio.");
  return buffer;
}

async function withRetry(operation, { attempts = 3, signal, onRetry = () => {} } = {}) {
  let lastError;
  for (let attempt = 1; attempt <= attempts; attempt++) {
    if (signal?.aborted) throw new Error("Geração cancelada.");
    try {
      return await operation();
    } catch (error) {
      lastError = error;
      const retryable = !error.status || error.status === 408 ||
        error.status === 429 || error.status >= 500;
      if (!retryable || attempt === attempts || signal?.aborted) break;

      const waitMs = error.retryAfter
        ? Math.min(error.retryAfter * 1000, 30000)
        : Math.min(1000 * (2 ** (attempt - 1)), 10000);

      onRetry({ attempt, nextAttempt: attempt + 1, waitMs, error: error.message });
      await sleep(waitMs, signal);
    }
  }
  throw lastError;
}

async function runPool(items, concurrency, worker) {
  const results = new Array(items.length);
  let cursor = 0;

  async function consume() {
    while (true) {
      const index = cursor++;
      if (index >= items.length) return;
      results[index] = await worker(items[index], index);
    }
  }

  const count = Math.max(1, Math.min(concurrency, items.length || 1));
  await Promise.all(Array.from({ length: count }, consume));
  return results;
}

function runFfmpegConcat(inputFiles, outputFile) {
  return new Promise((resolve, reject) => {
    const listFile = path.join(path.dirname(outputFile), `concat-${crypto.randomUUID()}.txt`);
    const quote = (p) => {
      // FFmpeg concat demuxer: escapa apóstrofos no caminho.
      return `file '${path.resolve(p).replace(/\\/g, "/").replace(/'/g, "'\\''")}'`;
    };

    fs.writeFileSync(listFile, inputFiles.map(quote).join("\n"), "utf8");

    const child = spawn("ffmpeg", [
      "-hide_banner", "-loglevel", "error", "-y",
      "-f", "concat", "-safe", "0",
      "-i", listFile,
      "-c", "copy",
      outputFile
    ], { windowsHide: true });

    let stderr = "";
    child.stderr.on("data", chunk => { stderr += chunk.toString(); });
    child.on("error", error => {
      try { fs.unlinkSync(listFile); } catch {}
      reject(new Error(`Não foi possível iniciar o FFmpeg. Verifique se está no PATH. ${error.message}`));
    });
    child.on("close", code => {
      try { fs.unlinkSync(listFile); } catch {}
      if (code === 0 && fs.existsSync(outputFile)) resolve(outputFile);
      else reject(new Error(`FFmpeg falhou (código ${code}): ${stderr.slice(-3000)}`));
    });
  });
}

class NarrationEngine {
  constructor(options = {}) {
    this.apiKey = options.apiKey || process.env.FISH_API_KEY;
    this.defaultModel = options.model || process.env.FISH_MODEL || "s2.1-pro-free";
    this.concurrency = Number(options.concurrency || process.env.NARRATION_CONCURRENCY || 3);
    this.chunkChars = Number(options.chunkChars || process.env.NARRATION_CHUNK_CHARS || 450);
    this.cacheDir = path.resolve(options.cacheDir || process.env.NARRATION_CACHE_DIR || "./data/narration-cache");
    this.outputDir = path.resolve(options.outputDir || process.env.NARRATION_OUTPUT_DIR || "./data/narrations");
    this.maxConcurrency = 5; // limite inicial conservador documentado pelo Fish Audio
    ensureDir(this.cacheDir);
    ensureDir(this.outputDir);
  }

  async generate({
    text, referenceId, model, format = "mp3", concurrency,
    signal, onEvent = () => {}
  }) {
    if (!this.apiKey) throw new Error("FISH_API_KEY não foi configurada no servidor.");
    if (!referenceId) throw new Error("Selecione o ID (reference_id) da voz Fish Audio.");
    if (!String(text || "").trim()) throw new Error("O roteiro está vazio.");
    if (!["mp3", "wav", "opus"].includes(format)) throw new Error("Formato inválido.");

    const selectedModel = model || this.defaultModel;
    const blocks = splitTextIntoBlocks(text, this.chunkChars);
    if (!blocks.length) throw new Error("Não foi possível dividir o roteiro.");

    const parallel = Math.max(1, Math.min(
      Number(concurrency || this.concurrency) || 1,
      this.maxConcurrency
    ));

    let completed = 0;
    let cacheHits = 0;

    onEvent({ type: "started", total: blocks.length, concurrency: parallel });

    const audioFiles = await runPool(blocks, parallel, async (block, index) => {
      if (signal?.aborted) throw new Error("Geração cancelada.");

      const key = hashKey({
        text: block, referenceId, model: selectedModel, format
      });
      const cachedFile = path.join(this.cacheDir, `${key}.${format}`);

      if (!fs.existsSync(cachedFile)) {
        await withRetry(async () => {
          const audio = await requestFishAudio({
            text: block,
            referenceId,
            apiKey: this.apiKey,
            model: selectedModel,
            format,
            signal
          });

          const temporary = `${cachedFile}.${crypto.randomUUID()}.tmp`;
          fs.writeFileSync(temporary, audio);
          fs.renameSync(temporary, cachedFile);
        }, {
          attempts: 3,
          signal,
          onRetry: info => onEvent({
            type: "retry",
            block: index + 1,
            ...info
          })
        });
      } else {
        cacheHits++;
      }

      completed++;
      onEvent({
        type: "progress",
        completed,
        total: blocks.length,
        percentage: Math.round(completed / blocks.length * 100),
        block: index + 1,
        cacheHits
      });

      return cachedFile;
    });

    if (signal?.aborted) throw new Error("Geração cancelada.");

    const outputFile = path.join(
      this.outputDir,
      `narration-${Date.now()}-${crypto.randomUUID().slice(0, 8)}.${format}`
    );

    await runFfmpegConcat(audioFiles, outputFile);

    const result = {
      success: true,
      audioPath: outputFile,
      fileName: path.basename(outputFile),
      totalBlocks: blocks.length,
      cacheHits,
      model: selectedModel,
      referenceId,
      format
    };

    onEvent({ type: "completed", ...result });
    return result;
  }
}

module.exports = {
  NarrationEngine,
  splitTextIntoBlocks
};