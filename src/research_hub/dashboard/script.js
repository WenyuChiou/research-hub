(function () {
  "use strict";

  const doc = document;
  const LIVE_MODE = { active: false, eventSource: null };
  let csrfToken = "";
  let activePopup = null;
  let activeLibraryLabelFilter = null;
  let activeLibraryArchivedFilter = null;
  let activeLibraryClusterFilter = null;
  let searchQuery = "";

  function activateTab(target) {
    const radio = doc.getElementById("dash-tab-" + target);
    if (radio) {
      radio.checked = true;
      radio.dispatchEvent(new Event("change", { bubbles: true }));
    }
    return radio;
  }

  function syncClusterChipState() {
    doc.querySelectorAll(".cluster-label").forEach(function (chip) {
      const isArchived = chip.dataset.archived === "1";
      const matchesCluster = (chip.dataset.cluster || "") === (activeLibraryClusterFilter || "");
      const matches = isArchived
        ? !!activeLibraryArchivedFilter && matchesCluster
        : !!activeLibraryLabelFilter && matchesCluster && (chip.dataset.label || "") === activeLibraryLabelFilter;
      chip.classList.toggle("cluster-label--active", matches);
    });
  }

  function applyLibraryFilters() {
    const normalizedSearch = (searchQuery || "").trim().toLowerCase();
    doc.querySelectorAll(".paper-row").forEach(function (row) {
      const title = row.dataset.title || "";
      const tags = row.dataset.tags || "";
      const cluster = row.closest(".cluster-card")?.querySelector("summary")?.textContent?.toLowerCase() || "";
      const labels = (row.dataset.labels || "")
        .split(",")
        .map(function (item) { return item.trim(); })
        .filter(Boolean);
      const matchesSearch = !normalizedSearch || title.includes(normalizedSearch) || tags.includes(normalizedSearch) || cluster.includes(normalizedSearch);
      const matchesCluster = !activeLibraryClusterFilter || (row.dataset.clusterRow || "") === activeLibraryClusterFilter;
      const matchesLabel = !activeLibraryLabelFilter || labels.includes(activeLibraryLabelFilter);
      const matchesArchived = !activeLibraryArchivedFilter;
      const visible = matchesSearch && matchesCluster && matchesLabel && matchesArchived;
      row.hidden = !visible;
      row.style.display = visible ? "" : "none";
    });
    doc.querySelectorAll(".cluster-card").forEach(function (card) {
      const anyVisible = !!card.querySelector(".paper-row:not([hidden])");
      if (normalizedSearch || activeLibraryLabelFilter || activeLibraryArchivedFilter) {
        card.open = anyVisible || (activeLibraryArchivedFilter && (card.dataset.cluster || "") === activeLibraryClusterFilter);
      }
    });
    doc.querySelectorAll(".cluster-archive").forEach(function (section) {
      const cluster = section.dataset.clusterArchive || "";
      const show = !activeLibraryArchivedFilter || cluster === activeLibraryClusterFilter;
      section.style.display = show ? "" : "none";
      if (activeLibraryArchivedFilter && cluster === activeLibraryClusterFilter) {
        section.open = true;
      } else if (!activeLibraryArchivedFilter && !section.open) {
        section.style.display = "";
      }
    });
    syncClusterChipState();
  }

  function closePopup() {
    if (activePopup) {
      activePopup.remove();
      activePopup = null;
      doc.removeEventListener("mousedown", onOutsideClick, true);
    }
  }

  function onOutsideClick(event) {
    if (activePopup && !activePopup.contains(event.target)) {
      closePopup();
    }
  }

  function placePopup(anchor, popup) {
    const rect = anchor.getBoundingClientRect();
    popup.classList.add("popup");
    popup.style.top = `${window.scrollY + rect.bottom + 8}px`;
    popup.style.left = `${Math.max(12, window.scrollX + rect.left)}px`;
    doc.body.appendChild(popup);
    activePopup = popup;
    setTimeout(function () {
      doc.addEventListener("mousedown", onOutsideClick, true);
    }, 0);
  }

  function fallbackCopy(text) {
    const ta = doc.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.style.position = "absolute";
    ta.style.left = "-9999px";
    doc.body.appendChild(ta);
    ta.select();
    try {
      doc.execCommand("copy");
    } catch (_) {
      // ignore
    }
    ta.remove();
  }

  function copyText(text, onDone) {
    const done = onDone || function () {};
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done, function () {
        fallbackCopy(text);
        done();
      });
      return;
    }
    fallbackCopy(text);
    done();
  }

  function downloadText(text, filename, type) {
    const blob = new Blob([text], { type: type });
    const url = URL.createObjectURL(blob);
    const a = doc.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  }

  function shellQuote(value) {
    if (value === undefined || value === null) {
      return "\"\"";
    }
    const text = String(value);
    if (/^[A-Za-z0-9_./-]+$/.test(text)) {
      return text;
    }
    return "\"" + text.replace(/\\/g, "\\\\").replace(/"/g, "\\\"") + "\"";
  }

  function updateLivePill(isLive) {
    const pill = doc.getElementById("live-pill");
    if (!pill) {
      return;
    }
    pill.textContent = isLive ? "Live" : "Static";
    pill.className = "live-pill " + (isLive ? "live-pill--on" : "live-pill--off");
  }

  function refreshFromState() {
    window.location.reload();
  }

  function openEventStream() {
    if (LIVE_MODE.eventSource || !window.EventSource) {
      return;
    }
    const es = new EventSource("/api/events");
    LIVE_MODE.eventSource = es;
    es.addEventListener("hello", function (ev) {
      try {
        const payload = JSON.parse(ev.data);
        if (payload.csrf_token) {
          csrfToken = String(payload.csrf_token);
        }
      } catch (_) {
        // ignore malformed hello payloads
      }
    });
    es.onmessage = function (ev) {
      try {
        const payload = JSON.parse(ev.data);
        if (payload.type === "vault_changed") {
          refreshFromState();
        }
      } catch (_) {
        // ignore malformed events
      }
    };
    es.onerror = function () {
      if (LIVE_MODE.eventSource) {
        LIVE_MODE.eventSource.close();
        LIVE_MODE.eventSource = null;
      }
      LIVE_MODE.active = false;
      updateLivePill(false);
    };
  }

  function detectLiveMode() {
    const options = {};
    if (typeof AbortSignal !== "undefined" && AbortSignal.timeout) {
      options.signal = AbortSignal.timeout(500);
    }
    return fetch("/healthz", options)
      .then(function (response) {
        return response.ok ? response.json() : null;
      })
      .then(function (data) {
        if (data && data.ok && data.mode === "live") {
          LIVE_MODE.active = true;
          doc.body.classList.add("live-mode");
          updateLivePill(true);
          openEventStream();
        } else {
          LIVE_MODE.active = false;
          updateLivePill(false);
        }
      })
      .catch(function () {
        LIVE_MODE.active = false;
        updateLivePill(false);
      });
  }

  function withTemporaryButtonState(button, interimText, fn) {
    const original = button ? button.textContent : "";
    if (button) {
      button.textContent = interimText;
      button.disabled = true;
    }
    return Promise.resolve(fn()).finally(function () {
      if (button) {
        setTimeout(function () {
          button.textContent = original;
          button.disabled = false;
        }, 2000);
      }
    });
  }

  function ensureConfirmDialog() {
    let dialog = doc.getElementById("confirm-action-dialog");
    if (dialog) {
      return dialog;
    }
    dialog = doc.createElement("dialog");
    dialog.id = "confirm-action-dialog";
    dialog.className = "confirm-dialog";
    dialog.innerHTML = `
      <form method="dialog" class="confirm-dialog-panel">
        <h3 class="confirm-dialog-title"></h3>
        <p class="confirm-dialog-message"></p>
        <div class="confirm-dialog-actions">
          <button type="button" class="confirm-dialog-cancel">Cancel</button>
          <button type="submit" class="confirm-dialog-confirm">Confirm</button>
        </div>
      </form>
    `;
    doc.body.appendChild(dialog);
    return dialog;
  }

  function confirmAction(options) {
    const dialog = ensureConfirmDialog();
    const title = dialog.querySelector(".confirm-dialog-title");
    const message = dialog.querySelector(".confirm-dialog-message");
    const confirmBtn = dialog.querySelector(".confirm-dialog-confirm");
    const cancelBtn = dialog.querySelector(".confirm-dialog-cancel");
    const focusableSelector = "button, [href], input, select, textarea, [tabindex]:not([tabindex='-1'])";

    title.textContent = options.title || "Confirm action";
    message.textContent = options.message || "Continue?";
    confirmBtn.textContent = options.confirmLabel || "Confirm";
    confirmBtn.classList.toggle("confirm-dialog-confirm--danger", !!options.danger);
    cancelBtn.onclick = function () {
      dialog.close("cancel");
    };
    dialog.onkeydown = function (event) {
      if (event.key !== "Tab") {
        return;
      }
      const focusable = Array.from(dialog.querySelectorAll(focusableSelector)).filter(function (el) {
        return !el.disabled && el.offsetParent !== null;
      });
      if (!focusable.length) {
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && doc.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && doc.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    dialog.onsubmit = async function (event) {
      event.preventDefault();
      confirmBtn.disabled = true;
      try {
        await Promise.resolve((options.onConfirm || function () {})());
        dialog.close("confirm");
      } finally {
        confirmBtn.disabled = false;
      }
    };
    dialog.showModal();
    confirmBtn.focus();
  }

  function renderExecResult(anchor, data) {
    const target = anchor ? (anchor.closest("form") || anchor.parentElement) : null;
    if (!target || !data) {
      return;
    }
    let drawer = target.querySelector(":scope > .exec-result-drawer");
    if (!drawer) {
      drawer = doc.createElement("div");
      drawer.className = "exec-result-drawer";
      target.appendChild(drawer);
    }
    drawer.replaceChildren();
    const summary = doc.createElement("div");
    summary.className = "exec-result-summary";
    const command = Array.isArray(data.command) ? data.command.join(" ") : "";
    const duration = typeof data.duration_ms === "number" ? (data.duration_ms / 1000).toFixed(2) : "0.00";
    summary.textContent = `${command || data.action || "command"} | ${duration}s | rc ${data.returncode ?? "?"}`;
    drawer.appendChild(summary);
    if (data.error === "timeout") {
      const timeout = doc.createElement("p");
      timeout.className = "exec-result-timeout";
      timeout.textContent = "Timed out.";
      drawer.appendChild(timeout);
    }
    const stdout = String(data.stdout || "");
    if (stdout) {
      const details = doc.createElement("details");
      details.className = "stdout-drawer";
      const detailsSummary = doc.createElement("summary");
      detailsSummary.textContent = "Full output";
      const pre = doc.createElement("pre");
      pre.className = "exec-result-stdout";
      pre.textContent = stdout;
      details.append(detailsSummary, pre);
      drawer.appendChild(details);
    }
    if (data.stderr) {
      const pre = doc.createElement("pre");
      pre.className = "exec-result-stderr";
      pre.textContent = String(data.stderr);
      drawer.appendChild(pre);
    }
  }

  async function execAction(action, slug, fields, button) {
    if (!LIVE_MODE.active) {
      return false;
    }
    const original = button ? button.textContent : "";
    if (button) {
      button.textContent = "Running...";
      button.disabled = true;
    }
    try {
      const response = await fetch("/api/exec", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": csrfToken,
        },
        body: JSON.stringify({ action: action, slug: slug, fields: fields }),
      });
      const data = await response.json();
      renderExecResult(button, data);
      if (button) {
        button.textContent = data.ok ? "Done" : "Error";
        setTimeout(function () {
          button.textContent = original;
          button.disabled = false;
        }, 2000);
      }
      return !!data.ok;
    } catch (_) {
      if (button) {
        button.textContent = "Error";
        setTimeout(function () {
          button.textContent = original;
          button.disabled = false;
        }, 2000);
      }
      return false;
    }
  }

  function showCopiedState(button, originalText) {
    button.textContent = "Copied!";
    button.classList.add("copied");
    setTimeout(function () {
      button.textContent = originalText;
      button.classList.remove("copied");
    }, 1500);
  }

  function showCitePopup(bibtex, slug, anchor) {
    closePopup();
    const popup = doc.createElement("div");
    const pre = doc.createElement("pre");
    const actions = doc.createElement("div");
    const copyBtn = doc.createElement("button");
    const downloadBtn = doc.createElement("button");
    const closeBtn = doc.createElement("button");

    pre.textContent = bibtex;
    actions.className = "paper-actions";
    copyBtn.className = "popup-btn";
    downloadBtn.className = "popup-btn";
    closeBtn.className = "popup-btn";
    copyBtn.textContent = "Copy";
    downloadBtn.textContent = "Download";
    closeBtn.textContent = "Close";

    copyBtn.addEventListener("click", function () {
      copyText(bibtex, function () {
        copyBtn.textContent = "Copied!";
        setTimeout(function () {
          copyBtn.textContent = "Copy";
        }, 1500);
      });
    });
    downloadBtn.addEventListener("click", function () {
      downloadText(bibtex, `${slug}.bib`, "application/x-bibtex");
    });
    closeBtn.addEventListener("click", closePopup);

    actions.append(copyBtn, downloadBtn, closeBtn);
    popup.append(pre, actions);
    placePopup(anchor, popup);
  }

  function showQuotePopup(btn) {
    closePopup();
    const popup = doc.createElement("div");
    popup.className = "popup popup-quote";
    popup.innerHTML = `
      <h4>Capture quote</h4>
      <label>Page <input type="text" name="page" placeholder="12"></label>
      <label>Quote text
        <textarea name="text" rows="4" placeholder="Paste the quoted passage here"></textarea>
      </label>
      <label>Context (optional)
        <input type="text" name="context" placeholder="Section 3.2 on escalation dynamics">
      </label>
      <div class="popup-actions">
        <button type="button" class="popup-btn" data-action="build">Copy capture command</button>
        <button type="button" class="popup-btn" data-action="close">Close</button>
      </div>
      <pre class="quote-cmd-preview" style="display:none"></pre>
    `;
    const pageInput = popup.querySelector('input[name="page"]');
    const textInput = popup.querySelector('textarea[name="text"]');
    const contextInput = popup.querySelector('input[name="context"]');
    const preview = popup.querySelector(".quote-cmd-preview");
    popup.querySelector('[data-action="build"]').addEventListener("click", function () {
      const page = (pageInput.value || "").trim();
      const text = (textInput.value || "").trim();
      const context = (contextInput.value || "").trim();
      if (!page || !text) {
        preview.style.display = "block";
        preview.textContent = "Fill page and quote text first.";
        return;
      }
      let command = `research-hub quote ${shellQuote(btn.dataset.slug || "")} --page ${shellQuote(page)} --text ${shellQuote(text)}`;
      if (context) {
        command += ` --context ${shellQuote(context)}`;
      }
      preview.style.display = "block";
      preview.textContent = command;
      copyText(command);
    });
    popup.querySelector('[data-action="close"]').addEventListener("click", closePopup);
    placePopup(btn, popup);
  }

  function showOpenMenu(btn) {
    closePopup();
    const popup = doc.createElement("div");
    const list = doc.createElement("ul");
    list.className = "popup-menu";
    popup.appendChild(list);

    const doi = btn.dataset.doi || "";
    const zoteroKey = btn.dataset.zoteroKey || "";
    const obsidianPath = btn.dataset.obsidianPath || "";
    const nlmUrl = btn.dataset.nlmUrl || "";

    [
      {
        label: "Open in Zotero",
        enabled: !!zoteroKey,
        action: function () {
          window.open(`zotero://select/items/0_${zoteroKey}`);
        }
      },
      {
        label: "Open in Obsidian",
        enabled: !!obsidianPath,
        action: function () {
          window.open(`obsidian://open?path=${encodeURIComponent(obsidianPath)}`);
        }
      },
      {
        label: "Open in NotebookLM",
        enabled: !!nlmUrl,
        action: function () {
          window.open(nlmUrl, "_blank", "noopener,noreferrer");
        }
      },
      {
        label: "Copy DOI",
        enabled: !!doi,
        action: function (button) {
          copyText(doi, function () {
            button.textContent = "Copied!";
            setTimeout(function () {
              button.textContent = "Copy DOI";
            }, 1500);
          });
        }
      }
    ].forEach(function (item) {
      const li = doc.createElement("li");
      const button = doc.createElement("button");
      button.type = "button";
      button.textContent = item.label;
      button.disabled = !item.enabled;
      button.addEventListener("click", function () {
        item.action(button);
        if (item.label !== "Copy DOI") {
          closePopup();
        }
      });
      li.appendChild(button);
      list.appendChild(li);
    });

    placePopup(btn, popup);
  }

  function buildManageCommand(form) {
    const action = form.dataset.action;
    const slug = form.dataset.slug || "";
    const data = new FormData(form);
    switch (action) {
      case "rename": {
        const newName = (data.get("new_name") || "").trim();
        if (!newName) {
          return null;
        }
        return `research-hub clusters rename ${shellQuote(slug)} --name ${shellQuote(newName)}`;
      }
      case "merge": {
        const target = (data.get("target") || "").trim();
        if (!target || target === slug) {
          return null;
        }
        return `research-hub clusters merge ${shellQuote(slug)} --into ${shellQuote(target)}`;
      }
      case "split": {
        const query = (data.get("query") || "").trim();
        const newName = (data.get("new_name") || "").trim();
        if (!query || !newName) {
          return null;
        }
        return `research-hub clusters split ${shellQuote(slug)} --query ${shellQuote(query)} --new-name ${shellQuote(newName)}`;
      }
      case "bind-zotero": {
        const zk = (data.get("zotero") || "").trim();
        if (!zk) {
          return null;
        }
        return `research-hub clusters bind ${shellQuote(slug)} --zotero ${shellQuote(zk)}`;
      }
      case "bind-nlm": {
        const nb = (data.get("notebooklm") || "").trim();
        if (!nb) {
          return null;
        }
        return `research-hub clusters bind ${shellQuote(slug)} --notebooklm ${shellQuote(nb)}`;
      }
      case "notebooklm-bundle":
        return `research-hub notebooklm bundle --cluster ${shellQuote(slug)}`;
      case "notebooklm-upload":
        return `research-hub notebooklm upload --cluster ${shellQuote(slug)} ${(data.get("visible") ? "--visible" : "--headless")}`;
      case "notebooklm-generate": {
        const kind = (data.get("kind") || "brief").trim();
        if (!["brief", "audio", "mind_map", "video"].includes(kind)) {
          return null;
        }
        const cliKind = kind === "mind_map" ? "mind-map" : kind;
        return `research-hub notebooklm generate --cluster ${shellQuote(slug)} --type ${cliKind}`;
      }
      case "notebooklm-download": {
        const kind = (data.get("kind") || "brief").trim();
        if (kind !== "brief") {
          return null;
        }
        return `research-hub notebooklm download --cluster ${shellQuote(slug)} --type ${kind}`;
      }
      case "notebooklm-ask": {
        const question = (data.get("question") || "").trim();
        const timeout = (data.get("timeout") || "").trim();
        if (!question) {
          return null;
        }
        let command = `research-hub notebooklm ask --cluster ${shellQuote(slug)} --question ${shellQuote(question)}`;
        if (/^\d+$/.test(timeout)) {
          command += ` --timeout ${timeout}`;
        }
        return command;
      }
      case "vault-polish-markdown":
        return `research-hub vault polish-markdown --cluster ${shellQuote(slug)}${data.get("apply") ? " --apply" : ""}`;
      case "bases-emit":
        return `research-hub bases emit --cluster ${shellQuote(slug)}${data.get("force") ? " --force" : ""}`;
      case "delete":
        return `research-hub clusters delete ${shellQuote(slug)}${data.get("apply") ? " --apply --force" : ""}`;
      default:
        return null;
    }
  }

  function buildManageFields(form) {
    const action = form.dataset.action;
    const data = new FormData(form);
    switch (action) {
      case "rename":
        return { new_name: (data.get("new_name") || "").trim() };
      case "merge":
        return { target: (data.get("target") || "").trim() };
      case "split":
        return {
          query: (data.get("query") || "").trim(),
          new_name: (data.get("new_name") || "").trim()
        };
      case "bind-zotero":
        return { zotero: (data.get("zotero") || "").trim() };
      case "bind-nlm":
        return { notebooklm: (data.get("notebooklm") || "").trim() };
      case "notebooklm-bundle":
        return {};
      case "notebooklm-upload":
        return { visible: !!data.get("visible") };
      case "notebooklm-generate":
        return { kind: (data.get("kind") || "brief").trim() };
      case "notebooklm-download":
        return { kind: (data.get("kind") || "brief").trim() };
      case "notebooklm-ask":
        return {
          question: (data.get("question") || "").trim(),
          timeout: (data.get("timeout") || "").trim()
        };
      case "vault-polish-markdown":
        return { apply: !!data.get("apply") };
      case "bases-emit":
        return { force: !!data.get("force") };
      case "delete":
        return { apply: !!data.get("apply") };
      default:
        return {};
    }
  }

  function buildPaperActionFields(form) {
    const data = new FormData(form);
    const action = form.dataset.action;
    if (action === "move") {
      return { target_cluster: (data.get("target_cluster") || "").trim() };
    }
    if (action === "label") {
      return { label: (data.get("label") || "").trim() };
    }
    if (action === "mark") {
      return { status: (data.get("status") || "").trim() };
    }
    if (action === "remove") {
      return { dry_run: !data.get("apply") };
    }
    return {};
  }

  function buildPaperActionCommand(form) {
    const action = form.dataset.action;
    const slug = form.dataset.slug || "";
    const fields = buildPaperActionFields(form);
    if (action === "move") {
      if (!fields.target_cluster) {
        return null;
      }
      return `research-hub move ${shellQuote(slug)} --to ${shellQuote(fields.target_cluster)}`;
    }
    if (action === "label") {
      if (!fields.label) {
        return null;
      }
      return `research-hub label ${shellQuote(slug)} --set ${shellQuote(fields.label)}`;
    }
    if (action === "mark") {
      if (!fields.status) {
        return null;
      }
      return `research-hub mark ${shellQuote(slug)} --status ${shellQuote(fields.status)}`;
    }
    if (action === "remove") {
      return `research-hub remove ${shellQuote(slug)}${fields.dry_run ? " --dry-run" : ""}`;
    }
    return null;
  }

  function buildComposeCommand(form) {
    const cluster = (form.querySelector('[name="cluster"]').value || "").trim();
    const outline = (form.querySelector('[name="outline"]').value || "")
      .split(/\r?\n/)
      .map(function (s) { return s.trim(); })
      .filter(Boolean)
      .join(";");
    const style = (form.querySelector('[name="style"]:checked') || {}).value || "apa";
    const includeBib = !!form.querySelector('[name="include_bibliography"]:checked');
    const selectedSlugs = Array.from(
      form.querySelectorAll('.composer-quote-list input[type="checkbox"]:checked')
    )
      .filter(function (el) { return (el.dataset.cluster || "") === cluster; })
      .map(function (el) { return el.dataset.slug || ""; })
      .filter(Boolean);

    if (!cluster) {
      return null;
    }

    const parts = ["research-hub compose-draft", "--cluster", shellQuote(cluster)];
    if (outline) {
      parts.push("--outline", shellQuote(outline));
    }
    if (selectedSlugs.length) {
      parts.push("--quotes", shellQuote(selectedSlugs.join(",")));
    }
    parts.push("--style", style);
    if (!includeBib) {
      parts.push("--no-bibliography");
    }
    return {
      command: parts.join(" "),
      fields: {
        cluster_slug: cluster,
        outline: outline,
        quote_slugs: selectedSlugs,
        style: style,
        include_bibliography: includeBib
      }
    };
  }

  function handleLabelFilter() {
    doc.querySelectorAll(".cluster-label").forEach(function (chip) {
      chip.addEventListener("click", function (event) {
        event.preventDefault();
        activateTab("library");
        const cluster = chip.dataset.cluster || "";
        const isArchived = chip.dataset.archived === "1";
        const label = chip.dataset.label || "";
        const wasActive = chip.classList.contains("cluster-label--active");
        if (wasActive) {
          activeLibraryLabelFilter = null;
          activeLibraryArchivedFilter = false;
          activeLibraryClusterFilter = null;
        } else if (isArchived) {
          activeLibraryLabelFilter = null;
          activeLibraryArchivedFilter = true;
          activeLibraryClusterFilter = cluster;
        } else {
          activeLibraryLabelFilter = label;
          activeLibraryArchivedFilter = false;
          activeLibraryClusterFilter = cluster;
        }
        applyLibraryFilters();
        const targetCard = doc.querySelector('.cluster-card[data-cluster="' + cluster + '"]');
        if (targetCard) {
          targetCard.open = true;
        }
      });
    });
  }

  function handleQuoteLabelFilter() {
    doc.querySelectorAll(".quote-filter-chip").forEach(function (chip) {
      chip.addEventListener("click", function (event) {
        event.preventDefault();
        const label = chip.dataset.label || "all";
        doc.querySelectorAll(".quote-filter-chip").forEach(function (other) {
          other.classList.remove("active");
        });
        chip.classList.add("active");
        doc.querySelectorAll(".quote-card").forEach(function (card) {
          const labels = (card.dataset.paperLabels || "")
            .split(",")
            .map(function (item) { return item.trim(); })
            .filter(Boolean);
          const visible = label === "all" || labels.includes(label);
          card.style.display = visible ? "" : "none";
        });
      });
    });
  }

  function updateApplyButtonLabel(form) {
    const button = form.querySelector(".manage-build-btn, .paper-action-submit");
    const checkbox = form.querySelector('input[name="apply"]');
    if (!button || !checkbox) {
      return;
    }
    const preview = button.dataset.previewLabel;
    const apply = button.dataset.applyLabel;
    if (preview && apply) {
      button.textContent = checkbox.checked ? apply : preview;
    }
  }

  function initApplyLabels() {
    doc.querySelectorAll(".manage-form, .paper-action-form").forEach(function (form) {
      updateApplyButtonLabel(form);
      const checkbox = form.querySelector('input[name="apply"]');
      if (checkbox) {
        checkbox.addEventListener("change", function () {
          updateApplyButtonLabel(form);
        });
      }
    });
  }

  function applyManageFilters() {
    const search = (doc.getElementById("manage-search")?.value || "").trim().toLowerCase();
    const sort = doc.getElementById("manage-sort")?.value || "name";
    const show = doc.getElementById("manage-show")?.value || "all";
    const grid = doc.querySelector(".manage-grid");
    if (!grid) {
      return;
    }
    const now = Date.now();
    const sevenDays = 7 * 24 * 60 * 60 * 1000;
    const cards = Array.from(grid.querySelectorAll(".manage-card"));
    cards.forEach(function (card) {
      const haystack = `${card.dataset.name || ""} ${card.dataset.cluster || ""}`.toLowerCase();
      const createdAt = Date.parse(card.dataset.createdAt || "");
      const isRecent = Number.isFinite(createdAt) && (now - createdAt <= sevenDays);
      const isUnbound = card.dataset.unbound === "1";
      const matchesSearch = !search || haystack.includes(search);
      const matchesShow = show === "all" || (show === "recent" && isRecent) || (show === "unbound" && isUnbound);
      card.hidden = !(matchesSearch && matchesShow);
    });
    cards.sort(function (a, b) {
      if (sort === "paper-count") {
        return Number(b.dataset.paperCount || 0) - Number(a.dataset.paperCount || 0);
      }
      if (sort === "last-activity") {
        return (Date.parse(b.dataset.lastActivity || "") || 0) - (Date.parse(a.dataset.lastActivity || "") || 0);
      }
      if (sort === "unbound") {
        return Number(b.dataset.unbound || 0) - Number(a.dataset.unbound || 0);
      }
      return (a.dataset.name || a.dataset.cluster || "").localeCompare(b.dataset.name || b.dataset.cluster || "");
    });
    cards.forEach(function (card) {
      grid.appendChild(card);
    });
  }

  function initManageFilters() {
    ["manage-search", "manage-sort", "manage-show"].forEach(function (id) {
      const control = doc.getElementById(id);
      if (control) {
        control.addEventListener("input", applyManageFilters);
        control.addEventListener("change", applyManageFilters);
      }
    });
    applyManageFilters();
  }

  const search = doc.getElementById("vault-search");
  if (search) {
    search.addEventListener("input", function (event) {
      searchQuery = (event.target.value || "").trim().toLowerCase();
      applyLibraryFilters();
    });
  }

  doc.querySelectorAll(".cite-btn").forEach(function (btn) {
    btn.addEventListener("click", function () {
      showCitePopup(btn.dataset.bibtex || "", btn.dataset.slug || "paper", btn);
    });
  });

  doc.querySelectorAll(".quote-btn").forEach(function (btn) {
    btn.addEventListener("click", function () {
      showQuotePopup(btn);
    });
  });

  doc.querySelectorAll(".cluster-cite-btn").forEach(function (btn) {
    btn.addEventListener("click", function () {
      const bibtex = btn.dataset.bibtex || "";
      const cluster = btn.dataset.cluster || "cluster";
      downloadText(bibtex, `${cluster}.bib`, "application/x-bibtex");
    });
  });

  doc.querySelectorAll(".open-btn").forEach(function (btn) {
    btn.addEventListener("click", function () {
      showOpenMenu(btn);
    });
  });

  doc.querySelectorAll(".copy-brief-btn").forEach(function (btn) {
    btn.addEventListener("click", function () {
      const original = btn.textContent;
      copyText(btn.dataset.text || "", function () {
        btn.textContent = "Copied!";
        setTimeout(function () {
          btn.textContent = original;
        }, 1500);
      });
    });
  });

  doc.querySelectorAll(".copy-cmd-btn").forEach(function (btn) {
    btn.addEventListener("click", async function () {
      const original = btn.textContent;
      if (LIVE_MODE.active && btn.dataset.action) {
        let fields = {};
        if (btn.dataset.fields) {
          try {
            fields = JSON.parse(btn.dataset.fields);
          } catch (_) {
            fields = {};
          }
        }
        const ok = await execAction(btn.dataset.action, btn.dataset.slug || null, fields, btn);
        if (ok) {
          return;
        }
      }
      copyText(btn.dataset.text || "", function () {
        btn.textContent = "Copied!";
        setTimeout(function () {
          btn.textContent = original;
        }, 1500);
      });
    });
  });

  doc.querySelectorAll("[data-jump-tab]").forEach(function (el) {
    el.addEventListener("click", function (event) {
      event.preventDefault();
      const target = el.dataset.jumpTab;
      const radio = activateTab(target);
      if (radio) {
        const panel = doc.getElementById("tab-" + target);
        if (panel && panel.scrollIntoView) {
          panel.scrollIntoView({ behavior: "smooth", block: "start" });
        }
      }
    });
  });

  const debugToggle = doc.getElementById("debug-toggle-btn");
  const debugSnapshot = doc.getElementById("debug-snapshot");
  if (debugToggle && debugSnapshot) {
    debugToggle.addEventListener("click", function () {
      const visible = debugSnapshot.classList.toggle("is-visible");
      debugToggle.textContent = visible ? "Hide snapshot" : "Show snapshot";
    });
  }

  const debugCopy = doc.getElementById("debug-copy-btn");
  if (debugCopy) {
    debugCopy.addEventListener("click", function () {
      const text = debugCopy.dataset.snapshot || "";
      const original = debugCopy.textContent;
      copyText(text, function () {
        debugCopy.textContent = "Copied!";
        debugCopy.classList.add("copied");
        setTimeout(function () {
          debugCopy.textContent = original;
          debugCopy.classList.remove("copied");
        }, 1500);
      });
    });
  }

  doc.querySelectorAll(".manage-form").forEach(function (form) {
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      const button = form.querySelector(".manage-build-btn");
      if (button) {
        button.click();
      }
      return false;
    });
    const button = form.querySelector(".manage-build-btn");
    if (!button) {
      return;
    }
    button.addEventListener("click", async function () {
      const command = buildManageCommand(form);
      if (!command) {
        button.textContent = "Fill the fields first";
        setTimeout(function () {
          const labels = {
            rename: "Copy rename command",
            merge: "Copy merge command",
            split: "Copy split command",
            "bind-zotero": "Copy bind command",
            "bind-nlm": "Copy bind command",
            "notebooklm-bundle": "Bundle papers",
            "notebooklm-upload": "Upload to NotebookLM",
            "notebooklm-generate": "Generate artifact",
            "notebooklm-download": "Download brief",
            "notebooklm-ask": "Ask NotebookLM",
            "vault-polish-markdown": "Polish markdown",
            "bases-emit": "Emit .base dashboard",
            delete: "Preview cascade (dry-run)"
          };
          button.textContent = labels[form.dataset.action] || "Copy command";
        }, 1500);
        return;
      }
      if (["merge", "delete"].includes(form.dataset.action || "") && !button.dataset.confirmed) {
        confirmAction({
          title: form.dataset.action === "delete" ? "Delete cluster" : "Merge cluster",
          message: form.dataset.action === "delete"
            ? `Delete ${form.dataset.slug || "this cluster"}${form.querySelector('input[name="apply"]')?.checked ? "" : " dry-run preview"}?`
            : `Merge ${form.dataset.slug || "this cluster"} into the selected cluster?`,
          confirmLabel: form.dataset.action === "delete" ? "Delete" : "Merge",
          danger: form.dataset.action === "delete",
          onConfirm: function () {
            button.dataset.confirmed = "1";
            button.click();
            delete button.dataset.confirmed;
          }
        });
        return;
      }
      if (LIVE_MODE.active) {
        const ok = await execAction(form.dataset.action || "", form.dataset.slug || null, buildManageFields(form), button);
        if (ok) {
          return;
        }
      }
      const original = button.textContent;
      copyText(command, function () {
        showCopiedState(button, original);
      });
    });
  });

  doc.addEventListener("click", function (event) {
    const btn = event.target.closest('[data-action="delete-artifact"]');
    if (!btn) {
      return;
    }
    event.preventDefault();
    confirmAction({
      title: "Delete artifact",
      message: `Delete this ${btn.dataset.kind || "NotebookLM"} artifact?`,
      confirmLabel: "Delete",
      danger: true,
      onConfirm: async function () {
        const original = btn.textContent;
        btn.textContent = "Deleting...";
        btn.disabled = true;
        try {
          const response = await fetch(`/artifact-delete?path=${btn.dataset.path || ""}`, {
            method: "POST",
            headers: { "X-CSRF-Token": csrfToken },
          });
          const data = await response.json();
          if (data.ok) {
            window.location.reload();
            return;
          }
          btn.textContent = data.error ? `Failed: ${data.error}` : "Delete failed";
        } catch (_) {
          btn.textContent = "Delete failed";
        } finally {
          setTimeout(function () {
            btn.textContent = original;
            btn.disabled = false;
          }, 2500);
        }
      }
    });
  });

  doc.querySelectorAll(".paper-action-form").forEach(function (form) {
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      const button = form.querySelector(".paper-action-submit");
      const command = buildPaperActionCommand(form);
      if (!command) {
        if (button) {
          const original = button.textContent;
          button.textContent = "Fill the fields first";
          setTimeout(function () { button.textContent = original; }, 1500);
        }
        return false;
      }
      const run = async function () {
        if (LIVE_MODE.active) {
          const ok = await execAction(form.dataset.action || "", form.dataset.slug || null, buildPaperActionFields(form), button);
          if (ok) {
            return;
          }
        }
        if (button) {
          const original = button.textContent;
          copyText(command, function () {
            showCopiedState(button, original);
          });
        }
      };
      const fields = buildPaperActionFields(form);
      if ((form.dataset.action === "remove" && !fields.dry_run) || (form.dataset.action === "mark" && fields.status === "archived")) {
        confirmAction({
          title: form.dataset.action === "remove" ? "Remove paper" : "Archive paper",
          message: form.dataset.action === "remove"
            ? `Remove ${form.dataset.slug || "this paper"} from the vault?`
            : `Archive ${form.dataset.slug || "this paper"}?`,
          confirmLabel: form.dataset.action === "remove" ? "Remove" : "Archive",
          danger: form.dataset.action === "remove",
          onConfirm: run,
        });
      } else {
        run();
      }
      return false;
    });
  });

  doc.querySelectorAll(".composer-form").forEach(function (form) {
    const buildBtn = form.querySelector(".composer-build-btn");
    const preview = form.parentElement.querySelector(".composer-cmd-preview");
    if (!buildBtn) {
      return;
    }

    form.addEventListener("submit", function (event) {
      event.preventDefault();
      buildBtn.click();
      return false;
    });

    buildBtn.addEventListener("click", async function () {
      const built = buildComposeCommand(form);
      if (!built) {
        preview.hidden = false;
        preview.textContent = "Pick a cluster first.";
        return;
      }

      preview.hidden = false;
      preview.textContent = built.command;

      if (LIVE_MODE.active) {
        const ok = await execAction("compose-draft", null, built.fields, buildBtn);
        if (ok) {
          return;
        }
      }

      const original = buildBtn.textContent;
      copyText(built.command, function () {
        showCopiedState(buildBtn, original);
      });
    });
  });

  handleLabelFilter();
  handleQuoteLabelFilter();
  initApplyLabels();
  initManageFilters();
  applyLibraryFilters();
  csrfToken = doc.querySelector('meta[name="csrf-token"]')?.getAttribute("content") || "";
  detectLiveMode();
})();
