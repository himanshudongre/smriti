/* =============================================================
   Smriti landing page — interactions (v2)
   No dependencies. Two responsibilities:
     1. Reveal-on-scroll for .reveal sections.
     2. The multi-agent coordination "protocol theatre" — a 5-step
        scripted animation that runs once on scroll-into-view and
        can be replayed.
   Honors prefers-reduced-motion: skips animation and leaves
   everything in its terminal state.
   ============================================================= */

(function () {
  "use strict";

  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // ── 1. Reveal-on-scroll ────────────────────────────────────────
  const revealEls = document.querySelectorAll(".reveal");
  if (reduced || !("IntersectionObserver" in window)) {
    revealEls.forEach((el) => el.classList.add("in"));
  } else {
    const revealObs = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("in");
            revealObs.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.12, rootMargin: "0px 0px -8% 0px" }
    );
    revealEls.forEach((el) => revealObs.observe(el));
  }

  // ── 2. Protocol theatre ────────────────────────────────────────
  const theatre = document.querySelector("[data-theatre]");
  if (!theatre) return;

  const claudeLane   = theatre.querySelector('[data-lane="claude"]');
  const codexLane    = theatre.querySelector('[data-lane="codex"]');
  const chipT1       = theatre.querySelector('[data-task="t-1"]');
  const chipT2       = theatre.querySelector('[data-task="t-2"]');
  const chipT3       = theatre.querySelector('[data-task="t-3"]');
  const chipT4       = theatre.querySelector('[data-task="t-4"]');
  const stepText     = theatre.querySelector("[data-step-text]");
  const stepCounter  = theatre.querySelector("[data-step-counter]");
  const replayBtn    = theatre.querySelector("[data-theatre-replay]");

  const STEPS = [
    {
      caption:
        'Same task pool. No orchestrator. <span class="muted">Watch each agent read the pool, claim something, and route around the other\'s claim.</span>',
      apply() {
        [claudeLane, codexLane].forEach((l) => l.classList.remove("active", "has-claim"));
        [chipT1, chipT2, chipT3, chipT4].forEach((c) =>
          c.classList.remove("claimed-claude", "claimed-codex", "dimmed")
        );
      },
    },
    {
      caption: '<span class="muted">claude-code reads the pool.</span>',
      apply() {
        claudeLane.classList.add("active");
        codexLane.classList.remove("active", "has-claim");
      },
    },
    {
      caption:
        'claude-code claims <strong>[implement] deletion-safety-guard</strong>.',
      apply() {
        claudeLane.classList.add("active", "has-claim");
        chipT2.classList.add("claimed-claude");
      },
    },
    {
      caption:
        '<span class="muted">codex reads the pool — sees claude-code\'s claim.</span>',
      apply() {
        claudeLane.classList.remove("active");
        claudeLane.classList.add("has-claim");
        codexLane.classList.add("active");
      },
    },
    {
      caption:
        'codex picks complementary work — <strong>[test] deletion-safety-tests</strong>.',
      apply() {
        codexLane.classList.add("active", "has-claim");
        chipT1.classList.add("claimed-codex");
      },
    },
    {
      caption:
        'Different agents. Different work. <span class="muted">Coordination through shared state.</span>',
      apply() {
        [claudeLane, codexLane].forEach((l) => l.classList.remove("active"));
        [claudeLane, codexLane].forEach((l) => l.classList.add("has-claim"));
        chipT3.classList.add("dimmed");
        chipT4.classList.add("dimmed");
      },
    },
  ];

  const TOTAL = STEPS.length - 1; // 0..5, display "n / 5"
  let stepTimer = null;
  let currentStep = 0;
  let hasPlayed = false;

  function renderStep(i) {
    currentStep = i;
    STEPS[i].apply();
    if (stepText)    stepText.innerHTML    = STEPS[i].caption;
    if (stepCounter) stepCounter.textContent = i + " / " + TOTAL;
  }

  function clearTimer() {
    if (stepTimer) {
      clearTimeout(stepTimer);
      stepTimer = null;
    }
  }

  function playFrom(i) {
    clearTimer();
    renderStep(i);
    if (i >= TOTAL) return;
    stepTimer = setTimeout(() => playFrom(i + 1), 1700);
  }

  function play() {
    if (reduced) {
      // Land on the final frame; skip the animation.
      renderStep(TOTAL);
      return;
    }
    playFrom(0);
  }

  function reset() {
    clearTimer();
    renderStep(0);
  }

  // Initial render (step 0 — pristine state).
  renderStep(0);

  // Replay button.
  if (replayBtn) {
    replayBtn.addEventListener("click", () => {
      reset();
      // Give the DOM one frame to settle before re-playing.
      requestAnimationFrame(() => play());
    });
  }

  // Auto-play once on scroll-into-view (or immediately if reduced motion).
  if (reduced || !("IntersectionObserver" in window)) {
    play();
    hasPlayed = true;
  } else {
    const playObs = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting && !hasPlayed) {
            hasPlayed = true;
            play();
            playObs.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.4 }
    );
    playObs.observe(theatre);
  }
})();
