import json
import os
import re
from collections import defaultdict
from datetime import datetime, timezone

import requests

from research_hub.paper_summarize import is_bad_abstract, pending_sections_markdown

def make_paper_slug(author, year, title) -> str:
    """Compute canonical paper slug (without .md extension).

    Single source of truth for the slug formula. Used by both:
    - `safe_filename()` to derive note filenames
    - Cross-reference wikilink generation in `pipeline.py`, `discover.py`,
      `operations.py` (formerly used divergent `slugify(title)[:60]` formulas
      that produced long-format slugs not matching actual filenames, causing
      1,199 broken `[[wikilink]]` phantom mega-hubs in user vaults — see
      v0.84.0 changelog for incident details).

    Formula: `{author_last}{year}-{4-keyword-stopword-filtered-short-title}`
    """
    author_last = re.sub(r'[^\w]', '', author.split(',')[0].split()[-1]).lower() if author else 'unknown'
    year_str = str(year) if year else 'nd'
    words = re.sub(r'[^\w\s]', '', title.lower()).split()
    stop = {'a','an','the','of','in','on','at','to','for','with','and','or','by','from','as','its','is','are','this','that'}
    key_words = [w for w in words if w not in stop][:4]
    short = '-'.join(key_words) if key_words else 'untitled'
    return f"{author_last}{year_str}-{short}"


def safe_filename(author, year, title):
    """Compute the .md filename for a paper note. Delegates to make_paper_slug."""
    return f"{make_paper_slug(author, year, title)}.md"

def get_all_items(base, collection_key):
    items = []
    start = 0
    while True:
        url = f"{base}/collections/{collection_key}/items?itemType=-attachment&limit=100&start={start}"
        try:
            r = requests.get(url, timeout=30)
            if r.status_code != 200:
                break
            batch = r.json()
            if not batch:
                break
            items.extend(batch)
            if len(batch) < 100:
                break
            start += 100
        except Exception as e:
            print(f"  Error fetching {collection_key} at {start}: {e}")
            break
    return items

def get_notes(base, item_key):
    url = f"{base}/items/{item_key}/children"
    try:
        r = requests.get(url, timeout=30)
        if r.status_code == 200:
            children = r.json()
            notes = []
            for child in children:
                if child.get('data', {}).get('itemType') == 'note':
                    note_text = child['data'].get('note', '')
                    note_text = re.sub(r'<[^>]+>', ' ', note_text)
                    note_text = re.sub(r'\s+', ' ', note_text).strip()
                    if note_text:
                        notes.append(note_text)
            return notes
    except:
        pass
    return []

def extract_item_data(item):
    data = item.get('data', {})
    item_type = data.get('itemType', '')
    if item_type in ('attachment', 'note'):
        return None
    title = data.get('title', 'Untitled')
    creators = data.get('creators', [])
    authors = []
    for c in creators:
        if c.get('creatorType') in ('author', 'editor'):
            last = c.get('lastName', '')
            first = c.get('firstName', '')
            if last:
                authors.append(f"{last}, {first}" if first else last)
            elif c.get('name'):
                authors.append(c['name'])
    year = data.get('date', '')
    if year:
        m = re.search(r'\d{4}', year)
        year = m.group(0) if m else year
    journal = (data.get('publicationTitle', '') or data.get('publisher', '') or
               data.get('bookTitle', '') or data.get('proceedingsTitle', '') or
               data.get('conferenceName', ''))
    doi = data.get('DOI', '')
    url_str = data.get('url', '')
    abstract = data.get('abstractNote', '')
    tags = [t['tag'] for t in data.get('tags', [])]
    key = item.get('key', '')
    return {
        'key': key,
        'item_type': item_type,
        'title': title,
        'authors': authors,
        'year': year,
        'journal': journal,
        'doi': doi,
        'url': url_str,
        'abstract': abstract,
        'tags': tags,
    }

# Concept tags emitted in the "Related Concepts" section of paper bodies.
# v0.82.0: Changed from [[Wikilink]] to #tag syntax.
# Prior values like "[[LLM-Agents]]" pointed at non-existent .md files, producing
# unresolved-link "mega-hub stars" in the Obsidian graph view (one hub had 115+ radial
# connections from this alone). Tags are the right primitive for cross-paper concept
# categorization; wikilinks are for explicit named cross-references to real notes.
# See: https://github.com/WenyuChiou/research-hub/issues (graph hygiene write-up).
TAG_WIKI_MAP = {
    'pmt': '#protection-motivation-theory',
    'protection motivation': '#protection-motivation-theory',
    'abm': '#agent-based-modeling',
    'agent-based': '#agent-based-modeling',
    'agent based': '#agent-based-modeling',
    'llm': '#llm-agents',
    'large language model': '#llm-agents',
    'generative agent': '#generative-agents',
    'memory': '#memory-systems',
    'retrieval': '#memory-systems',
    'flood risk': '#flood-risk',
    'flood': '#flood-risk',
    'risk perception': '#risk-perception',
    'social vulnerability': '#social-vulnerability',
    'social capital': '#social-capital',
    'social network': '#social-networks',
    'bounded rationality': '#bounded-rationality',
    'active inference': '#active-inference',
    'reinforcement learning': '#reinforcement-learning',
    'socio-hydrology': '#socio-hydrology',
    'sociohydrology': '#socio-hydrology',
    'governance': '#governance',
    'multi-agent': '#multi-agent-systems',
    'multiagent': '#multi-agent-systems',
    'trust': '#trust-in-risk-management',
    'relocation': '#relocation-decisions',
    'insurance': '#flood-insurance',
    'place attachment': '#place-attachment',
    'sem': '#structural-equation-modeling',
    'structural equation': '#structural-equation-modeling',
    'reflection': '#reflection-metacognition',
    'metacognition': '#reflection-metacognition',
    'adaptation': '#flood-adaptation',
    'natural language': '#natural-language-processing',
}


def tags_to_wiki_links(tags):
    """Return sorted unique concept tags matching the Zotero tag keywords.

    Despite the legacy name (kept for backward import compat), this returns
    `#tag` strings, not `[[Wikilink]]` strings since v0.82.0.
    """
    links = set()
    for tag in tags:
        tag_lower = tag.lower()
        for keyword, link in TAG_WIKI_MAP.items():
            if keyword in tag_lower:
                links.add(link)
    return sorted(links)

def make_raw_md(
    item_data,
    collections_list,
    notes,
    *,
    topic_cluster: str = "",
    cluster_queries: list[str] | None = None,
    ingestion_source: str = "research-hub-v0.3.0",
    verified: bool | None = None,
    verified_at: str = "",
    include_pending_summary_sections: bool = True,
):
    title = item_data['title'].replace('"', "'")
    authors = item_data['authors']
    year = item_data['year']
    journal = item_data['journal']
    volume = item_data.get('volume', '')
    issue = item_data.get('issue', '')
    pages = item_data.get('pages', '')
    doi = item_data['doi']
    abstract = item_data['abstract'] or ""
    tags = item_data['tags']
    key = item_data['key']

    author_str = '; '.join(authors) if authors else 'Unknown'
    # v0.87.1 #6: ensure topic:<slug> tag is present so Obsidian tag pane
    # surfaces the cluster + graph view can color-group papers by topic.
    # Locked decision (V087_PLAN.md / V088_PLAN.md Q1): use `topic:` prefix.
    if topic_cluster:
        topic_tag = f"topic:{topic_cluster}"
        if topic_tag not in tags:
            tags = list(tags) + [topic_tag]
    tags_yaml = '[' + ', '.join(f'"{t}"' for t in tags) + ']' if tags else '[]'
    collections_yaml = '[' + ', '.join(f'"{c}"' for c in collections_list) + ']'
    cluster_queries_yaml = '[' + ', '.join(
        f'"{query}"' for query in (cluster_queries or [])
    ) + ']'
    ingested_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    pdf_path_line = ""
    if item_data.get("pdf_path"):
        pdf_path_line = f'zotero-pdf-path: "{item_data["pdf_path"]}"\n'

    # v0.83.0: Compute human-readable graph display fields.
    # Obsidian's storage filename uses dash-slug (URL-safe). Graph view shows
    # `display_title` (via Front Matter Title plugin) or first `aliases` entry
    # (via Obsidian 1.5+ inline title). This avoids the visually-noisy dash-slug
    # node labels users complained about (2026-05-11 graph hygiene audit).
    aliases_list: list[str] = []
    display_title_val = ""
    if authors:
        first_author = authors[0] or ""
        # "Lamond, Jessica" -> "Lamond"; "Lamond" -> "Lamond"; "(See arXiv...)" -> ""
        first_last = first_author.split(',')[0].strip()
        if first_last and not first_last.startswith('('):
            year_label = str(year) if year else 'n.d.'
            short = f"{first_last} {year_label}"
            aliases_list.append(short)
            if len(authors) > 1:
                aliases_list.append(f"{first_last} et al. {year_label}")
            if title and not title.startswith('(See '):
                display_title_val = f"{first_last} {year_label} — {title}"
            else:
                display_title_val = short
    aliases_yaml = '[' + ', '.join(f'"{a}"' for a in aliases_list) + ']' if aliases_list else '[]'

    wiki_links = tags_to_wiki_links(tags)

    notes_section = ""
    if notes:
        notes_section = "\n## Notes & Annotations\n\n"
        for note in notes[:3]:
            truncated = note[:600] + ('...' if len(note) > 600 else '')
            notes_section += f"> {truncated}\n\n"

    related_section = ""
    if wiki_links:
        related_section = "\n## Related Concepts\n\n" + "  ".join(wiki_links) + "\n"

    summarize_status = "failed_no_abstract" if is_bad_abstract(str(abstract)) else "pending"
    abstract_section = f"\n## Abstract\n\n{abstract}\n" if abstract else ""
    pending_summary_sections = ""
    if include_pending_summary_sections:
        pending_summary_sections = "\n" + pending_sections_markdown() + "\n"
    doi_line = f'doi: "{doi}"' if doi else 'doi: ""'

    citation_line = journal
    if volume: citation_line += f", {volume}"
    if issue: citation_line += f"({issue})"
    if pages: citation_line += f", {pages}"

    content = f"""---
title: "{title}"
aliases: {aliases_yaml}
display_title: "{display_title_val}"
authors: "{author_str}"
year: {year if year else 'null'}
journal: "{journal}"
volume: "{volume}"
issue: "{issue}"
pages: "{pages}"
{doi_line}
zotero-key: {key}
collections: {collections_yaml}
tags: {tags_yaml}
ingested_at: "{ingested_at}"
ingestion_source: "{ingestion_source}"
topic_cluster: "{topic_cluster}"
cluster_queries: {cluster_queries_yaml}
summarize_status: {summarize_status}
{pdf_path_line}verified: {"null" if verified is None else ("true" if verified else "false")}
verified_at: "{verified_at}"
status: unread
---

# {title}

**Authors:** {author_str}
**Year:** {year}
**Citation:** {citation_line}
{"**DOI:** " + doi if doi else ""}
{abstract_section}{related_section}{notes_section}{pending_summary_sections}
---
*Source: Zotero key `{key}`*
"""
    return content

def _load_zotero_settings():
    from research_hub.config import get_config

    cfg = get_config()
    collections = {}
    for key, metadata in cfg.zotero_collections.items():
        if not isinstance(metadata, dict):
            continue
        collections[key] = (
            metadata.get("name", key),
            metadata.get("parent"),
            metadata.get("section"),
        )
    return cfg, collections


def main() -> None:
    cfg, collections = _load_zotero_settings()
    if cfg.zotero_library_id is None:
        raise RuntimeError(
            "Zotero library_id not configured — set zotero.library_id in config.json or "
            "ZOTERO_LIBRARY_ID env var"
        )
    if not collections:
        raise RuntimeError("No Zotero collections configured in config.json")

    base = f"http://localhost:23119/api/{cfg.zotero_library_type}s/{cfg.zotero_library_id}"
    kb = str(cfg.root)

    print("Starting Zotero extraction...")

    all_items = {}
    item_collections = defaultdict(list)

    for ckey, (cname, parent, section) in collections.items():
        items = get_all_items(base, ckey)
        count = 0
        for item in items:
            idata = extract_item_data(item)
            if idata is None:
                continue
            ikey = idata['key']
            if ikey not in all_items:
                all_items[ikey] = idata
            if cname not in item_collections[ikey]:
                item_collections[ikey].append(cname)
            count += 1
        print(f"  {cname}: {count} items")

    print(f"\nTotal unique items: {len(all_items)}")

    os.makedirs(f"{kb}/raw", exist_ok=True)

    filename_map = {}
    used_filenames = set()

    for ikey, idata in all_items.items():
        authors = idata['authors']
        first_author = authors[0] if authors else 'unknown'
        year = idata['year']
        title = idata['title']

        base_fname = safe_filename(first_author, year, title)
        base_name = base_fname[:-3]

        final_fname = base_fname
        counter = 1
        while final_fname in used_filenames:
            final_fname = f"{base_name}-{counter}.md"
            counter += 1
        used_filenames.add(final_fname)
        filename_map[ikey] = final_fname[:-3]

    print("Fetching notes and writing files...")
    written = 0
    for ikey, idata in all_items.items():
        notes = get_notes(base, ikey)
        colls = item_collections[ikey]
        content = make_raw_md(idata, colls, notes)
        fname = filename_map[ikey] + '.md'
        filepath = os.path.join(kb, 'raw', fname)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        written += 1
        if written % 50 == 0:
            print(f"  Written {written} files...")

    print(f"Written {written} raw/ files")

    with open(os.path.join(kb, 'filename_map.json'), 'w', encoding='utf-8') as f:
        json.dump(filename_map, f)

    combined = {}
    for k, v in all_items.items():
        combined[k] = dict(v)
        combined[k]['collections'] = item_collections[k]
        combined[k]['filename'] = filename_map.get(k, '')
    with open(os.path.join(kb, 'all_items.json'), 'w', encoding='utf-8') as f:
        json.dump(combined, f, ensure_ascii=False, indent=2)

    print("Done!")


if __name__ == "__main__":
    main()
