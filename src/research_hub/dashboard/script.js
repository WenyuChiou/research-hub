(function () {
  "use strict";

  const doc = document;
  let activePopup = null;

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
    popup.className = "popup";
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

  const search = doc.getElementById("vault-search");
  if (search) {
    search.addEventListener("input", function (event) {
      const q = (event.target.value || "").trim().toLowerCase();
      doc.querySelectorAll(".paper-row").forEach(function (row) {
        const title = row.dataset.title || "";
        const tags = row.dataset.tags || "";
        const cluster = row.closest(".cluster-card")?.querySelector("summary")?.textContent?.toLowerCase() || "";
        const hit = !q || title.includes(q) || tags.includes(q) || cluster.includes(q);
        row.hidden = !hit;
      });
      doc.querySelectorAll(".cluster-card").forEach(function (card) {
        if (!q) {
          return;
        }
        const anyVisible = !!card.querySelector(".paper-row:not([hidden])");
        card.open = anyVisible;
      });
    });
  }

  doc.querySelectorAll(".cite-btn").forEach(function (btn) {
    btn.addEventListener("click", function () {
      showCitePopup(btn.dataset.bibtex || "", btn.dataset.slug || "paper", btn);
    });
  });

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
})();
