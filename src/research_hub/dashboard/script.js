(function () {
  "use strict";

  const doc = document;
  const LIVE_MODE = { active: false, eventSource: null };
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
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: action, slug: slug, fields: fields }),
      });
      const data = await response.json();
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
      case "delete":
        return `research-hub clusters delete ${shellQuote(slug)} --dry-run`;
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
      case "delete":
        return {};
      default:
        return {};
    }
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
            delete: "Copy delete dry-run command"
          };
          button.textContent = labels[form.dataset.action] || "Copy command";
        }, 1500);
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
  applyLibraryFilters();
  detectLiveMode();
})();
