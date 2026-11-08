// render.js - Script chamado pelo Python para renderizar cena Remotion
// Uso: node render.js <props.json> <output.mp4> <ffmpeg_path>
//
// ESTRATÉGIA:
// 1. FFmpeg primeiro (rápido, confiável, funciona agora)
// 2. Remotion real está ESTRUTURADO e pronto para ativar
//    - Projeto oficial: C:\Users\Lucas\my-video
//    - Componente: HelloWorld (aceita titleText e titleColor)
//    - Para ativar Remotion real: descomentar a seção ABAIXO
//      e garantir que o Chromium esteja acessível

const { execFileSync } = require("child_process");
const fs = require("fs");
const path = require("path");

const PROPS_FILE = process.argv[2];
const OUTPUT_FILE = process.argv[3];
const FFMPEG_PATH = process.argv[4] || "ffmpeg";

if (!PROPS_FILE || !OUTPUT_FILE) {
  process.exit(1);
}

const props = JSON.parse(fs.readFileSync(PROPS_FILE, "utf-8"));
const OUT_DIR = path.dirname(OUTPUT_FILE);

if (!fs.existsSync(OUT_DIR)) {
  fs.mkdirSync(OUT_DIR, { recursive: true });
}

// =====================================================================
// FFmpeg render (funciona agora, sem dependências extras)
// =====================================================================
function ffmpegRender() {
  const largura = props.width || 1920;
  const altura = props.height || 1080;
  const hex = (props.cor_primaria || "#2F6FED").replace("#", "0x");
  const duracao = props.duration || 5;

  execFileSync(
    FFMPEG_PATH,
    [
      "-y", "-loglevel", "error", "-f", "lavfi", "-i",
      `color=c=${hex}:s=${largura}x${altura}:r=24:d=${duracao}`,
      "-c:v", "libx264", "-pix_fmt", "yuv420p", "-t", String(duracao),
      OUTPUT_FILE,
    ],
    { timeout: 120000, encoding: "utf-8", maxBuffer: 10 * 1024 * 1024 }
  );
}

// =====================================================================
// Remotion real (projeto oficial my-video - descomentar para ativar)
// =====================================================================
/*
const { renderMedia } = require("@remotion/renderer");

function tryRemotionRenderer() {
  return new Promise((resolve, reject) => {
    const timeoutId = setTimeout(() => {
      reject(new Error("Remotion timeout (180s)"));
    }, 180000);

    renderMedia({
      composition: "HelloWorld",
      entryPoint: "C:\\Users\\Lucas\\my-video\\src\\index.ts",
      inputProps: {
        titleText: props.text || "Faceless Cloud Studio",
        titleColor: props.cor_primaria || "#2F6FED",
      },
      outputLocation: OUTPUT_FILE,
      codec: "h264",
      fps: 30,
      durationInFrames: Math.ceil((props.duration || 5) * 30),
      imageFormat: "jpeg",
      jpegQuality: 90,
      browserExecutable: "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
      chromiumOptions: {
        args: [
          "--headless",
          "--no-sandbox",
          "--disable-gpu",
          "--disable-dev-shm-usage",
          "--disable-setuid-sandbox",
          "--disable-web-security",
        ],
      },
      envVariables: { REMOTION_CHROMIUM_EXECUTABLE_PATH: "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" },
    })
      .then(() => {
        clearTimeout(timeoutId);
        resolve();
      })
      .catch((err) => {
        clearTimeout(timeoutId);
        reject(err);
      });
  });
}
*/

(async () => {
  try {
    ffmpegRender();
    console.log(JSON.stringify({ ok: true, output: OUTPUT_FILE, method: "ffmpeg" }));
  } catch (err) {
    console.error(JSON.stringify({ ok: false, error: String(err) }));
    process.exit(1);
  }
})();
