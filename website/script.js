/* =============================================================
   Smriti landing page — interactions (v2.1)
   No dependencies. Five responsibilities:
     1. Reveal-on-scroll for .reveal sections.
     2. Drift canvas — toggles .is-drifted on scroll-in (CSS handles the rest).
     3. Terminal panel — toggles .is-revealed for the highlight underline.
     4. Markdown surface — types the conflict line, strikes it through,
        types the resolution. On scroll-in. Replayable.
     5. Protocol theatre — 3-column live coordination demo. Tasks fly from
        the central pool into the side agent panels as packets, settle into
        work-stacks. Replay button. Click-to-fire bonus interaction.
   Honors prefers-reduced-motion: skips animations and lands every element
   in its terminal state.
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
      { threshold: 0.1, rootMargin: "0px 0px -8% 0px" }
    );
    revealEls.forEach((el) => revealObs.observe(el));
  }

  // ── 2. Drift canvas toggle ────────────────────────────────────
  const drift = document.querySelector("[data-drift]");
  if (drift) {
    if (reduced || !("IntersectionObserver" in window)) {
      drift.classList.add("is-drifted");
    } else {
      const driftObs = new IntersectionObserver(
        (entries) => {
          entries.forEach((entry) => {
            if (entry.isIntersecting) {
              setTimeout(() => drift.classList.add("is-drifted"), 400);
              driftObs.unobserve(entry.target);
            }
          });
        },
        { threshold: 0.18 }
      );
      driftObs.observe(drift);
    }
  }

  // ── 3. Terminal reveal toggle ──────────────────────────────────
  const terminal = document.querySelector("[data-terminal]");
  if (terminal) {
    if (reduced || !("IntersectionObserver" in window)) {
      terminal.classList.add("is-revealed");
    } else {
      const termObs = new IntersectionObserver(
        (entries) => {
          entries.forEach((entry) => {
            if (entry.isIntersecting) {
              terminal.classList.add("is-revealed");
              termObs.unobserve(entry.target);
            }
          });
        },
        { threshold: 0.18 }
      );
      termObs.observe(terminal);
    }
  }

  // ── 4. Markdown surface — type the collision, strike, resolve ───
  const mdSurface = document.querySelector("[data-md-surface]");
  if (mdSurface) {
    const conflict = mdSurface.querySelector("[data-md-conflict]");
    const resolution = mdSurface.querySelector("[data-md-resolution]");
    const conflictText = conflict ? conflict.textContent : "";
    const resolutionText = resolution
      ? resolution.textContent.replace(/\s*$/, "")
      : "";

    function resetMd() {
      if (conflict) {
        conflict.textContent = conflictText;
        conflict.classList.remove("struck");
        conflict.style.opacity = "0";
      }
      if (resolution) {
        resolution.innerHTML = '<span class="typing-caret"></span>';
        resolution.style.opacity = "1";
      }
    }

    function playMd() {
      if (reduced) {
        // Land in resolved state directly.
        if (conflict) {
          conflict.textContent = conflictText;
          conflict.classList.add("struck");
          conflict.style.opacity = "0.5";
        }
        if (resolution) {
          resolution.innerHTML =
            resolutionText + '<span class="typing-caret"></span>';
        }
        return;
      }

      resetMd();
      // Phase 1: fade conflict in.
      setTimeout(() => {
        if (conflict) {
          conflict.style.transition = "opacity 350ms";
          conflict.style.opacity = "1";
        }
      }, 250);

      // Phase 2: strike it.
      setTimeout(() => {
        if (conflict) conflict.classList.add("struck");
      }, 1400);

      // Phase 3: type the resolution.
      setTimeout(() => {
        if (!resolution) return;
        let i = 0;
        const caretHtml = '<span class="typing-caret"></span>';
        const tick = () => {
          if (i <= resolutionText.length) {
            resolution.innerHTML = resolutionText.slice(0, i) + caretHtml;
            i++;
            setTimeout(tick, 28);
          }
        };
        tick();
      }, 2050);
    }

    if (reduced || !("IntersectionObserver" in window)) {
      playMd();
    } else {
      const mdObs = new IntersectionObserver(
        (entries) => {
          entries.forEach((entry) => {
            if (entry.isIntersecting) {
              playMd();
              mdObs.unobserve(entry.target);
            }
          });
        },
        { threshold: 0.18 }
      );
      mdObs.observe(mdSurface);
    }
  }

  // ── 5. Protocol theatre ────────────────────────────────────────
  const theatre = document.querySelector("[data-theatre]");
  if (!theatre) return;

  const pool        = theatre.querySelector("[data-pool]");
  const claudePanel = theatre.querySelector('[data-agent="claude"]');
  const codexPanel  = theatre.querySelector('[data-agent="codex"]');
  const claudeStack = theatre.querySelector('[data-work-stack="claude"]');
  const codexStack  = theatre.querySelector('[data-work-stack="codex"]');
  const claudeStatus = claudePanel.querySelector("[data-agent-status]");
  const codexStatus  = codexPanel.querySelector("[data-agent-status]");
  const stepText    = theatre.querySelector("[data-step-text]");
  const stepCounter = theatre.querySelector("[data-step-counter]");
  const replayBtn   = theatre.querySelector("[data-theatre-replay]");

  function getPackets() {
    return Array.from(pool.querySelectorAll(".packet"));
  }

  function setStatus(agent, text) {
    const el = agent === "claude" ? claudeStatus : codexStatus;
    if (el) el.textContent = text;
  }

  function clearStacks() {
    claudeStack.innerHTML = "";
    codexStack.innerHTML = "";
  }

  function resetTheatre() {
    [claudePanel, codexPanel].forEach((p) => p.classList.remove("is-active"));
    setStatus("claude", "idle");
    setStatus("codex",  "idle");
    clearStacks();
    getPackets().forEach((p) =>
      p.classList.remove("claimed-claude", "claimed-codex", "dimmed")
    );
    if (stepCounter) stepCounter.textContent = "0 / 5";
  }

  function makeWorkItem(intent, name, pid, agent) {
    const li = document.createElement("li");
    li.className = "packet claimed-" + agent;
    li.innerHTML =
      '<span class="intent ' + intent + '">' + intent + "</span>" +
      '<span class="name">' + name + "</span>" +
      '<span class="pid">' + pid + "</span>";
    li.style.opacity = "0";
    li.style.transform = "translateY(6px)";
    li.style.transition = "opacity 300ms, transform 300ms";
    return li;
  }

  // Animate a packet flying from the pool into an agent's work-stack.
  // Returns a Promise that resolves when the packet has settled.
  function flyPacket(packet, agent) {
    return new Promise((resolve) => {
      const targetStack = agent === "claude" ? claudeStack : codexStack;
      const intent = packet.dataset.intent;
      const name   = packet.querySelector(".name").textContent;
      const pid    = packet.querySelector(".pid").textContent;

      // Mark the pool packet as claimed (color tint + still in pool).
      const claimClass = "claimed-" + agent;
      packet.classList.add(claimClass);

      if (reduced) {
        const li = makeWorkItem(intent, name, pid, agent);
        targetStack.appendChild(li);
        requestAnimationFrame(() => {
          li.style.opacity = "1";
          li.style.transform = "translateY(0)";
        });
        resolve();
        return;
      }

      const theatreRect = theatre.getBoundingClientRect();
      const srcRect = packet.getBoundingClientRect();

      // Compute destination: top of the target stack, offset by current
      // child count to stack vertically.
      const stackRect = targetStack.getBoundingClientRect();
      const dstX = stackRect.left - theatreRect.left;
      const dstY = stackRect.top  - theatreRect.top
                   + targetStack.childElementCount * 40;

      // Build the flying packet — a clone of the original styled identically.
      const fly = document.createElement("div");
      fly.className = "packet-flying packet " + claimClass;
      fly.style.left  = (srcRect.left - theatreRect.left) + "px";
      fly.style.top   = (srcRect.top  - theatreRect.top)  + "px";
      fly.style.width = srcRect.width + "px";
      fly.innerHTML =
        '<span class="intent ' + intent + '">' + intent + "</span>" +
        '<span class="name">' + name + "</span>" +
        '<span class="pid">' + pid + "</span>";
      theatre.appendChild(fly);

      // Force layout flush, then transition to destination.
      // eslint-disable-next-line no-unused-expressions
      fly.offsetWidth;

      const deltaX = dstX - (srcRect.left - theatreRect.left);
      const deltaY = dstY - (srcRect.top  - theatreRect.top);

      requestAnimationFrame(() => {
        fly.style.transform =
          "translate(" + deltaX + "px, " + deltaY + "px) scale(0.98)";
      });

      let resolved = false;
      const finalize = () => {
        if (resolved) return;
        resolved = true;
        const li = makeWorkItem(intent, name, pid, agent);
        targetStack.appendChild(li);
        requestAnimationFrame(() => {
          li.style.opacity = "1";
          li.style.transform = "translateY(0)";
        });
        fly.remove();
        resolve();
      };

      fly.addEventListener("transitionend", finalize, { once: true });
      // Fallback in case transitionend doesn't fire (e.g. tab hidden).
      setTimeout(finalize, 1700);
    });
  }

  function setCaption(html, n) {
    if (stepText) stepText.innerHTML = html;
    if (stepCounter) stepCounter.textContent = n + " / 5";
  }

  // ── Scripted 5-step play ───────────────────────────────────────
  let playing = false;
  let playToken = 0;

  function wait(ms) {
    return new Promise((r) => setTimeout(r, ms));
  }

  async function play() {
    if (playing) return;
    playing = true;
    const myToken = ++playToken;
    resetTheatre();

    const stepDelay = reduced ? 0 : 1400;
    const aborted = () => myToken !== playToken;

    // Step 1
    setCaption('<span class="muted">claude-code reads the pool.</span>', 1);
    claudePanel.classList.add("is-active");
    setStatus("claude", "reading");
    await wait(stepDelay);
    if (aborted()) { playing = false; return; }

    // Step 2 — fly t-2 to claude
    const t2 = pool.querySelector('[data-task="t-2"]');
    setCaption(
      'claude-code claims <strong>[implement] deletion-safety-guard</strong>.',
      2
    );
    if (t2) await flyPacket(t2, "claude");
    setStatus("claude", "working");
    await wait(reduced ? 0 : 600);
    if (aborted()) { playing = false; return; }

    // Step 3
    setCaption(
      '<span class="muted">codex reads the pool — sees claude-code\'s claim.</span>',
      3
    );
    claudePanel.classList.remove("is-active");
    codexPanel.classList.add("is-active");
    setStatus("codex", "reading");
    await wait(stepDelay);
    if (aborted()) { playing = false; return; }

    // Step 4 — fly t-1 to codex
    const t1 = pool.querySelector('[data-task="t-1"]');
    setCaption(
      'codex picks complementary work — <strong>[test] deletion-safety-tests</strong>.',
      4
    );
    if (t1) await flyPacket(t1, "codex");
    setStatus("codex", "working");
    await wait(reduced ? 0 : 600);
    if (aborted()) { playing = false; return; }

    // Step 5 — settle, dim remaining
    setCaption(
      'Different agents. Different work. <span class="muted">Coordination through shared state.</span>',
      5
    );
    codexPanel.classList.remove("is-active");
    const t3 = pool.querySelector('[data-task="t-3"]');
    const t4 = pool.querySelector('[data-task="t-4"]');
    if (t3) t3.classList.add("dimmed");
    if (t4) t4.classList.add("dimmed");

    playing = false;
  }

  // ── Click-to-fire bonus interaction ────────────────────────────
  // Dimmed (passed-over) packets stay interactive — clicking re-activates
  // them. Already-claimed packets are inert. Mid-play clicks are ignored.
  pool.addEventListener("click", (e) => {
    const packet = e.target.closest(".packet");
    if (!packet) return;
    if (
      packet.classList.contains("claimed-claude") ||
      packet.classList.contains("claimed-codex")
    ) {
      return;
    }
    if (playing) return;

    // Re-activate if dimmed.
    packet.classList.remove("dimmed");

    const claudeCount = claudeStack.childElementCount;
    const codexCount  = codexStack.childElementCount;
    const agent = codexCount < claudeCount ? "codex" : "claude";
    flyPacket(packet, agent);
  });

  // ── Replay button ──────────────────────────────────────────────
  if (replayBtn) {
    replayBtn.addEventListener("click", () => {
      playing = false;
      playToken++;
      requestAnimationFrame(() => play());
    });
  }

  // ── Auto-play once on scroll-into-view ─────────────────────────
  if (reduced || !("IntersectionObserver" in window)) {
    play();
  } else {
    let hasPlayed = false;
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
      { threshold: 0.18 }
    );
    playObs.observe(theatre);
  }
})();
