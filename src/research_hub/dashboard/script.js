// research-hub dashboard v2 — vanilla JS interactivity.
// Bound to a single VAULT_DATA constant injected by Python at render time.
// Scope: search filter, status chip filter, sortable columns, copy-to-clipboard.
// Render limit: 50 rows visible; "Show more" reveals the rest.

(function () {
  "use strict";

  const ROW_LIMIT = 50;

  const search = document.getElementById("search-input");
  const tbody = document.getElementById("paper-rows");
  const showMore = document.getElementById("show-more");
  const filterChips = document.querySelectorAll(".filter-chip");
  const sortHeaders = document.querySelectorAll("th[data-sort]");
  const copyButtons = document.querySelectorAll(".copy-button");

  if (!tbody) {
    return;
  }

  const allRows = Array.from(tbody.querySelectorAll("tr.paper-row"));
  let visibleLimit = ROW_LIMIT;
  let activeStatus = "all";
  let searchTerm = "";
  let sortKey = null;
  let sortDir = "asc";

  function rowMatches(row) {
    const status = row.dataset.status || "";
    if (activeStatus !== "all" && status !== activeStatus) {
      return false;
    }
    if (searchTerm) {
      const title = row.dataset.title || "";
      const cluster = row.dataset.cluster || "";
      if (!title.includes(searchTerm) && !cluster.includes(searchTerm)) {
        return false;
      }
    }
    return true;
  }

  function applyFilters() {
    const filtered = allRows.filter(rowMatches);
    if (sortKey) {
      filtered.sort(function (a, b) {
        const av = (a.dataset[sortKey] || "").toLowerCase();
        const bv = (b.dataset[sortKey] || "").toLowerCase();
        if (av < bv) return sortDir === "asc" ? -1 : 1;
        if (av > bv) return sortDir === "asc" ? 1 : -1;
        return 0;
      });
    }
    tbody.innerHTML = "";
    filtered.slice(0, visibleLimit).forEach(function (row) {
      row.hidden = false;
      tbody.appendChild(row);
    });
    if (showMore) {
      showMore.hidden = filtered.length <= visibleLimit;
    }
  }

  if (search) {
    search.addEventListener("input", function (event) {
      searchTerm = (event.target.value || "").trim().toLowerCase();
      visibleLimit = ROW_LIMIT;
      applyFilters();
    });
  }

  filterChips.forEach(function (chip) {
    chip.setAttribute("aria-pressed", chip.dataset.status === "all" ? "true" : "false");
    chip.addEventListener("click", function () {
      activeStatus = chip.dataset.status || "all";
      filterChips.forEach(function (other) {
        other.setAttribute("aria-pressed", other === chip ? "true" : "false");
      });
      visibleLimit = ROW_LIMIT;
      applyFilters();
    });
  });

  sortHeaders.forEach(function (header) {
    header.addEventListener("click", function () {
      const key = header.dataset.sort;
      if (sortKey === key) {
        sortDir = sortDir === "asc" ? "desc" : "asc";
      } else {
        sortKey = key;
        sortDir = "asc";
      }
      sortHeaders.forEach(function (other) {
        other.setAttribute("aria-sort", "none");
      });
      header.setAttribute("aria-sort", sortDir === "asc" ? "ascending" : "descending");
      applyFilters();
    });
  });

  if (showMore) {
    showMore.addEventListener("click", function () {
      visibleLimit += ROW_LIMIT;
      applyFilters();
    });
  }

  copyButtons.forEach(function (button) {
    button.addEventListener("click", function () {
      const text = button.dataset.copy || "";
      const reset = function () {
        button.classList.remove("copied");
        button.textContent = "Copy ⧉";
      };
      const ok = function () {
        button.classList.add("copied");
        button.textContent = "Copied!";
        setTimeout(reset, 1500);
      };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(ok, function () {
          fallbackCopy(text, ok);
        });
      } else {
        fallbackCopy(text, ok);
      }
    });
  });

  function fallbackCopy(text, onDone) {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.style.position = "absolute";
    ta.style.left = "-9999px";
    document.body.appendChild(ta);
    ta.select();
    try {
      document.execCommand("copy");
      onDone();
    } catch (_) {
      // ignore
    }
    document.body.removeChild(ta);
  }

  applyFilters();
})();
