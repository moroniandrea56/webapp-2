/*
 * Dashboard BrainArt — porta in JS della mappatura metriche -> visuale
 * definita in visual_engine.py / signal_processing.py.
 *
 * In produzione questi valori arriveranno dal backend Python (compute_metrics()),
 * salvati per sessione utente e recuperati qui via fetch(). Per il prototipo
 * usiamo una sessione mock con la stessa "forma" di dati.
 */

const session = {
  // le tre metriche standard prodotte da compute_metrics()
  asymmetry: 0.42,   // -1 (withdrawal) .. +1 (approach) -> colore del quadro
  activation: 0.58,  // 0 .. 1 -> movimento / complessità
  signature: 0.63,   // 0 .. 1 -> forma / numero di lobi

  // metriche derivate mostrate nella dashboard (fuori dallo scope di
  // signal_processing.py, calcolate lato prodotto per il racconto della sessione)
  readingLabel: "TENSIONE",
  quote: "«Mi prometto ogni tramonto che il desiderio di non lasciarsi sfuggire i " +
         "momenti preziosi della vita non deve dare per scontato lo scorrere del tempo.»",

  preReading: {
    label: "INTENSO",
    desc: "Il tuo cuore batte forte e resta pronto ad accogliere ciò che arriva. " +
          "I processi che portano la mente a immergersi in un pensiero richiedono spesso " +
          "un coinvolgimento intenso, e le tue reazioni fisiologiche lo confermano.",
    minutes: 10.4,
    bpm: 75,
    bpmDelta: 0.01,
  },

  postReading: {
    label: "EQUILIBRIO",
    flowPercent: 31,
    desc: "Con la lettura hai raggiunto uno stato di equilibrio: la mente si stabilizza " +
          "e resta comunque ricettiva.",
  },
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
/* Bootstrap                                                              */
/* ---------------------------------------------------------------------- */

function populateText() {
  document.getElementById("quoteText").textContent = session.quote;
  document.getElementById("readingLabel").textContent = session.readingLabel;

  document.getElementById("preLabel").textContent = session.preReading.label;
  document.getElementById("preDesc").textContent = session.preReading.desc;
  document.getElementById("statMinutes").textContent = session.preReading.minutes.toFixed(1);
  document.getElementById("statBpm").textContent = session.preReading.bpm;
  document.getElementById("statDelta").textContent =
    (session.preReading.bpmDelta >= 0 ? "+" : "") + session.preReading.bpmDelta.toFixed(2);

  document.getElementById("postLabel").textContent = session.postReading.label;
  document.getElementById("postDesc").textContent = session.postReading.desc;
  document.getElementById("flowPercent").innerHTML =
    `${session.postReading.flowPercent}<span>%</span>`;
}

function initCanvases() {
  makeBlobPainter(document.getElementById("artCanvas"), {
    asymmetry: session.asymmetry,
    activation: session.activation,
    signature: session.signature,
    speed: 1,
  });

  // pannello "prima del testo": stato pre-lettura, sempre caldo/intenso
  makeBlobPainter(document.getElementById("preCanvas"), {
    asymmetry: 0.8,
    activation: 0.85,
    signature: session.signature,
    hueOverride: 8,
    speed: 1.3,
  });

  // pannello "effetto della lettura": stato di equilibrio, verde/calmo
  makeBlobPainter(document.getElementById("postCanvas"), {
    asymmetry: 0.1,
    activation: 0.25,
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

document.addEventListener("DOMContentLoaded", () => {
  populateText();
  initCanvases();
  initInteractions();
});
