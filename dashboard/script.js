/*
 * Dashboard BrainArt — recupera la sessione da /api/session (server.py,
 * che calcola le metriche reali con eeg_source.py + signal_processing.py)
 * e porta in JS la stessa mappatura definita in visual_engine.py per
 * disegnare il quadro generativo su canvas.
 */

// Usata solo se /api/session non è raggiungibile (es. pagina aperta con un
// semplice static file server, senza python3 server.py in esecuzione).
const FALLBACK_SESSION = {
  asymmetry: 0.42,
  activation: 0.58,
  signature: 0.63,
  readingLabel: "TENSIONE",
  quote: "Mi prometto ogni tramonto che il desiderio di non lasciarsi sfuggire i " +
         "momenti preziosi della vita non deve dare per scontato lo scorrere del tempo.",
  preReading: { label: "INTENSO", minutes: 10.4, bpm: 75, bpmDelta: 0.01 },
  postReading: { label: "EQUILIBRIO", flowPercent: 31 },
};

const PRE_DESCRIPTIONS = {
  INTENSO: "Il tuo cuore batte forte e resta pronto ad accogliere ciò che arriva. " +
           "I processi che portano la mente a immergersi in un pensiero richiedono spesso " +
           "un coinvolgimento intenso, e le tue reazioni fisiologiche lo confermano.",
  VIGILE: "Il tuo corpo è attento e reattivo, pronto a cogliere ogni sfumatura del testo " +
          "che stai per leggere.",
  CALMO: "Arrivi alla lettura in uno stato di quiete: il battito è disteso e regolare.",
};

const POST_DESCRIPTIONS = {
  QUIETE: "La lettura ti ha portato verso una quiete profonda: il battito rallenta e " +
          "la mente si distende.",
  FLOW: "Sei entrato in uno stato di flow: la mente segue il testo senza sforzo, " +
        "immersa e fluida.",
  EQUILIBRIO: "Con la lettura hai raggiunto uno stato di equilibrio: la mente si " +
              "stabilizza e resta comunque ricettiva.",
};

/* ---------------------------------------------------------------------- */
/* Motore generativo: stesso principio di visual_engine.py               */
/* (lobi <- signature, densità/ampiezza <- activation, colore <- asymmetry) */
/* renderizzato come "blob" organico animato invece che scatter di punti. */
/* ---------------------------------------------------------------------- */

function hueFromAsymmetry(asymmetry) {
  // stessa regola di visual_engine.py: positivo = caldo, negativo = freddo
  let hue = asymmetry >= 0 ? 18 : 210; // gradi CSS (arancio vs blu/ciano)
  hue += (1 - Math.abs(asymmetry)) * 24;
  return hue;
}

function makeBlobPainter(canvas, { asymmetry, activation, signature, hueOverride, speed = 1 }) {
  const ctx = canvas.getContext("2d");
  const size = canvas.width;
  const cx = size / 2;
  const cy = size / 2;
  const baseRadius = size * 0.30;

  const lobes = 3 + Math.round(signature * 6);       // 3..9, come n_lobes in visual_engine.py
  const amplitude = 0.25 + 0.35 * activation;         // più attivazione = forma più mossa
  const layers = 3;
  const hue = hueOverride !== undefined ? hueOverride : hueFromAsymmetry(asymmetry);

  let t = 0;

  function drawLayer(radiusScale, alpha, phase, lightness) {
    const points = 180;
    ctx.beginPath();
    for (let i = 0; i <= points; i++) {
      const angle = (i / points) * Math.PI * 2;
      const r =
        baseRadius * radiusScale *
        (1 +
          amplitude * Math.sin(lobes * angle + phase + t) * 0.5 +
          amplitude * Math.sin(lobes * 1.7 * angle - phase * 1.3 + t * 1.3) * 0.28 +
          amplitude * Math.sin(3 * angle + t * 0.6) * 0.12);
      const x = cx + r * Math.cos(angle);
      const y = cy + r * Math.sin(angle);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.closePath();

    const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, baseRadius * radiusScale * 1.4);
    grad.addColorStop(0, `hsla(${hue}, 95%, ${lightness + 15}%, ${alpha})`);
    grad.addColorStop(0.55, `hsla(${hue}, 90%, ${lightness}%, ${alpha * 0.7})`);
    grad.addColorStop(1, `hsla(${hue}, 90%, ${lightness - 10}%, 0)`);
    ctx.fillStyle = grad;
    ctx.fill();
  }

  function frame() {
    ctx.clearRect(0, 0, size, size);
    ctx.fillStyle = "#000";
    ctx.fillRect(0, 0, size, size);

    ctx.globalCompositeOperation = "lighter";
    for (let l = 0; l < layers; l++) {
      const radiusScale = 1 - l * 0.16;
      const alpha = 0.55 - l * 0.12;
      const lightness = 55 - l * 8;
      drawLayer(radiusScale, alpha, l * 1.4, lightness);
    }
    ctx.globalCompositeOperation = "source-over";

    t += 0.006 * speed;
    requestAnimationFrame(frame);
  }

  frame();
}

/* ---------------------------------------------------------------------- */
/* Caricamento sessione                                                   */
/* ---------------------------------------------------------------------- */

function getSessionIdFromLocation() {
  const pathMatch = window.location.pathname.match(/^\/s\/([a-zA-Z0-9]+)\/?$/);
  if (pathMatch) return pathMatch[1];
  return new URLSearchParams(window.location.search).get("s");
}

async function loadSession() {
  const existingId = getSessionIdFromLocation();

  try {
    if (existingId) {
      // sessione già esistente (link personale riaperto): stessa identica pagina.
      const res = await fetch(`/api/session/${existingId}`);
      if (!res.ok) throw new Error(`sessione '${existingId}' non trovata (${res.status})`);
      return await res.json();
    }

    // prima visita: crea una sessione persistente e "fissa" l'URL su di essa,
    // così un reload o la condivisione del link non ne generano una nuova.
    const res = await fetch("/api/session", { method: "POST" });
    if (!res.ok) throw new Error(`creazione sessione fallita (${res.status})`);
    const data = await res.json();
    window.history.replaceState(null, "", `/s/${data.id}`);
    return data;
  } catch (err) {
    console.warn(
      "Impossibile contattare il backend (server.py non in esecuzione?): " +
      "uso i dati di esempio.",
      err
    );
    return FALLBACK_SESSION;
  }
}

/* ---------------------------------------------------------------------- */
/* Bootstrap                                                              */
/* ---------------------------------------------------------------------- */

function populateText(session) {
  document.getElementById("quoteText").textContent = `«${session.quote}»`;
  document.getElementById("readingLabel").textContent = session.readingLabel;

  const pre = session.preReading;
  document.getElementById("preLabel").textContent = pre.label;
  document.getElementById("preDesc").textContent =
    PRE_DESCRIPTIONS[pre.label] || PRE_DESCRIPTIONS.VIGILE;
  document.getElementById("statMinutes").textContent = pre.minutes.toFixed(1);
  document.getElementById("statBpm").textContent = pre.bpm;
  document.getElementById("statDelta").textContent =
    (pre.bpmDelta >= 0 ? "+" : "") + pre.bpmDelta.toFixed(2);

  const post = session.postReading;
  document.getElementById("postLabel").textContent = post.label;
  document.getElementById("postDesc").textContent =
    POST_DESCRIPTIONS[post.label] || POST_DESCRIPTIONS.EQUILIBRIO;
  document.getElementById("flowPercent").innerHTML = `${post.flowPercent}<span>%</span>`;
}

function initCanvases(session) {
  makeBlobPainter(document.getElementById("artCanvas"), {
    asymmetry: session.asymmetry,
    activation: session.activation,
    signature: session.signature,
    speed: 1,
  });

  // pannello "prima del testo": intensità pre-lettura, sempre in tonalità calde
  makeBlobPainter(document.getElementById("preCanvas"), {
    asymmetry: session.asymmetry,
    activation: Math.min(1, session.activation + 0.3),
    signature: session.signature,
    hueOverride: 8,
    speed: 1.3,
  });

  // pannello "effetto della lettura": stato di chiusura, tonalità fredde/verdi
  makeBlobPainter(document.getElementById("postCanvas"), {
    asymmetry: session.asymmetry,
    activation: session.activation * 0.5,
    signature: session.signature,
    hueOverride: 150,
    speed: 0.6,
  });
}

function initInteractions() {
  const howToRead = document.getElementById("howToRead");
  const howToReadPanel = document.getElementById("howToReadPanel");
  howToRead.addEventListener("click", () => {
    const open = howToReadPanel.getAttribute("data-open") === "true";
    howToReadPanel.setAttribute("data-open", String(!open));
    howToRead.setAttribute("aria-expanded", String(!open));
  });

  document.getElementById("howToReadDataBtn").addEventListener("click", () => {
    alert(
      "I dati fisiologici (battito e sua variabilità) vengono raccolti prima della " +
      "lettura per fotografare il tuo stato di partenza, e confrontati con quelli " +
      "rilevati durante la lettura per calcolare l'effetto del testo su di te."
    );
  });

  document.getElementById("downloadBtn").addEventListener("click", () => {
    const canvas = document.getElementById("artCanvas");
    const link = document.createElement("a");
    link.download = "il-tuo-quadro-brainart.png";
    link.href = canvas.toDataURL("image/png");
    link.click();
  });

  document.getElementById("shareBtn").addEventListener("click", async () => {
    const canvas = document.getElementById("artCanvas");
    canvas.toBlob(async (blob) => {
      const file = new File([blob], "il-tuo-quadro-brainart.png", { type: "image/png" });
      if (navigator.share && navigator.canShare && navigator.canShare({ files: [file] })) {
        try {
          await navigator.share({
            files: [file],
            title: "Il mio quadro BrainArt",
            text: "Mind Made Art — la mia sessione BrainArt",
          });
        } catch (err) {
          // utente ha annullato la condivisione: nessuna azione necessaria
        }
      } else {
        alert("Condivisione non supportata da questo browser: usa 'Scarica qui' e carica l'immagine manualmente.");
      }
    }, "image/png");
  });
}

function initPersonalLink(session) {
  if (!session.id) return; // dati di fallback: nessuna sessione persistente da linkare

  const wrap = document.getElementById("personalLink");
  const urlEl = document.getElementById("personalLinkUrl");
  const copyBtn = document.getElementById("copyLinkBtn");
  const url = `${window.location.origin}/s/${session.id}`;

  urlEl.textContent = url;
  wrap.hidden = false;

  copyBtn.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(url);
    } catch (err) {
      window.prompt("Copia questo link:", url);
      return;
    }
    const original = copyBtn.textContent;
    copyBtn.textContent = "Copiato!";
    setTimeout(() => { copyBtn.textContent = original; }, 1500);
  });
}

async function bootstrap() {
  const session = await loadSession();
  populateText(session);
  initCanvases(session);
  initInteractions();
  initPersonalLink(session);
}

document.addEventListener("DOMContentLoaded", bootstrap);
