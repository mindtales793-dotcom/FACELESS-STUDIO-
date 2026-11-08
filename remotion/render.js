"use strict";

const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { bundle } = require("@remotion/bundler");
const { renderMedia, selectComposition } = require("@remotion/renderer");

const propsFile = process.argv[2];
const outputFile = process.argv[3];

async function main() {
  if (!propsFile || !outputFile) {
    throw new Error("Uso: node render.js <props.json> <saida.mp4>");
  }
  if (!fs.existsSync(propsFile)) {
    throw new Error(`Arquivo de propriedades não encontrado: ${propsFile}`);
  }

  const props = JSON.parse(fs.readFileSync(propsFile, "utf8"));
  const duration = Number(props.duration || 5);
  const width = Number(props.width || 1280);
  const height = Number(props.height || 720);

  if (!String(props.text || "").trim()) throw new Error("O texto da cena está vazio.");
  if (!Number.isFinite(duration) || duration < 1 || duration > 30) {
    throw new Error("A duração deve estar entre 1 e 30 segundos.");
  }
  if (!Number.isInteger(width) || !Number.isInteger(height) ||
      width < 240 || height < 240 || width > 1920 || height > 1920 ||
      width * height > 2073600) {
    throw new Error("Resolução inválida ou acima do limite Full HD.");
  }

  const entryPoint = path.join(__dirname, "src", "index.ts");
  const serveUrl = await bundle({
    entryPoint,
    onProgress: (progress) => {
      if (process.env.REMOTION_VERBOSE === "1") {
        process.stderr.write(`Bundle Remotion: ${Math.round(progress * 100)}%\n`);
      }
    },
  });

  const composition = await selectComposition({
    serveUrl,
    id: "FacelessScene",
    inputProps: props,
  });

  const options = {
    composition,
    serveUrl,
    codec: "h264",
    outputLocation: path.resolve(outputFile),
    inputProps: props,
    concurrency: Math.max(1, Math.min(4, os.cpus().length - 1)),
    chromiumOptions: {
      gl: "angle",
      disableWebSecurity: false,
    },
  };

  if (process.env.REMOTION_CHROMIUM_EXECUTABLE_PATH) {
    options.browserExecutable = process.env.REMOTION_CHROMIUM_EXECUTABLE_PATH;
  }

  await renderMedia(options);
  const stat = fs.statSync(options.outputLocation);
  if (!stat.size) throw new Error("O Remotion gerou um arquivo vazio.");

  process.stdout.write(JSON.stringify({
    ok: true,
    output: options.outputLocation,
    method: "remotion",
    duration,
    width,
    height,
    bytes: stat.size,
  }) + "\n");
}

main().catch((error) => {
  process.stderr.write(JSON.stringify({
    ok: false,
    error: error && error.stack ? error.stack : String(error),
  }) + "\n");
  process.exitCode = 1;
});
