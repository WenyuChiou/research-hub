import json
import requests
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

BASE = "http://localhost:23119/api/users/14772686"
sys.path.insert(0, str(Path(__file__).parent))
from hub_config import get_config

_cfg = get_config()
KB = str(_cfg.root)

COLLECTIONS = {
    # ABM
    "GH5CN2ZZ": ("ABM", None, "ABM"),
    "RGWPTYWR": ("Flood damage", "GH5CN2ZZ", "ABM"),
    "YSSPJU2R": ("Flood insurance", "GH5CN2ZZ", "ABM"),
    "BLWKV8H9": ("Implication", "GH5CN2ZZ", "ABM"),
    "95LER8AR": ("introduction", "GH5CN2ZZ", "ABM"),
    "L65BIR88": ("LLM AI agent", "GH5CN2ZZ", "ABM"),
    "NT5LVLTV": ("LLM-related (not ABM)", "L65BIR88", "ABM"),
    "S4XREM5K": ("Memory & Retrieval", "L65BIR88", "ABM"),
    "PNNWUSLV": ("multi-agent framework", "L65BIR88", "ABM"),
    "RA2LDSS5": ("Reflection", "L65BIR88", "ABM"),
    "CS7B3C8U": ("Methodology", "GH5CN2ZZ", "ABM"),
    "VLGFRI65": ("SM", "GH5CN2ZZ", "ABM"),
    "K6ZVAIXT": ("Study Area", "GH5CN2ZZ", "ABM"),
    # survey
    "JXEJYEZR": ("survey", None, "survey"),
    "4XMKX9QE": ("Buoyout", "JXEJYEZR", "survey"),
    "QNGSIHMK": ("Flood mitigation", "JXEJYEZR", "survey"),
    "ZHV8WQBY": ("Insurance", "JXEJYEZR", "survey"),
    "6A34KKZP": ("Place attachment", "JXEJYEZR", "survey"),
    "6N5XA43F": ("Relocation", "JXEJYEZR", "survey"),
    "UCZTX2Z7": ("Risk percpetion", "JXEJYEZR", "survey"),
    "9UE64WEN": ("SEM", "JXEJYEZR", "survey"),
    "6HL63X3F": ("Social norm/ Social capital", "JXEJYEZR", "survey"),
    "YLJ5PGYH": ("Soical capital", "JXEJYEZR", "survey"),
    "WJ9TMU5C": ("Soical Vulnerability", "JXEJYEZR", "survey"),
    "58HG7SNF": ("Trust in Risk Management", "JXEJYEZR", "survey"),
    "JRR3C9EC": ("vehicle", "JXEJYEZR", "survey"),
    # GBF
    "MDMG47ZS": ("Governed Broker Framework", None, "GBF"),
    "4EM52NPV": ("01-Theoretical-Foundations", "MDMG47ZS", "GBF"),
    "VMU7U3ID": ("Active-Inference", "4EM52NPV", "GBF"),
    "QD723EMF": ("Bounded-Rationality", "4EM52NPV", "GBF"),
    "UKN6BJNI": ("Memory-and-Cognition", "4EM52NPV", "GBF"),
    "6AFGP7RT": ("PMT-and-Behavior", "4EM52NPV", "GBF"),
    "U7SZM77A": ("Reflection-Metacognition", "4EM52NPV", "GBF"),
    "TKRV48C6": ("Reinforcement-Learning", "4EM52NPV", "GBF"),
    "AQP8NC4V": ("02-Flood-Risk-Adaptation", "MDMG47ZS", "GBF"),
    "4HQFBVZA": ("Flood-Experience-Studies", "AQP8NC4V", "GBF"),
    "DTQD83QT": ("PMT-Empirical-Validation", "AQP8NC4V", "GBF"),
    "9RPGHHHR": ("Water-Resources-ABM", "AQP8NC4V", "GBF"),
    "7TBRD6Q5": ("03-LLM-Agent-Architecture", "MDMG47ZS", "GBF"),
    "DNR7TSEF": ("Generative-Agents", "7TBRD6Q5", "GBF"),
    "85TNJFBC": ("Memory-Systems", "7TBRD6Q5", "GBF"),
    "EGE2XWAN": ("04-Multi-Agent-Systems", "MDMG47ZS", "GBF"),
    "DZVMZZBI": ("Coordination", "EGE2XWAN", "GBF"),
    "HA9EBB7X": ("Governance", "EGE2XWAN", "GBF"),
    "U2Z7REWZ": ("Social-Networks", "EGE2XWAN", "GBF"),
    "FIBNX7JQ": ("05-Domain-Applications", "MDMG47ZS", "GBF"),
    "27EPKPQF": ("ABM-Methodology", "FIBNX7JQ", "GBF"),
    "N4VF3FSD": ("Flood-Simulation", "FIBNX7JQ", "GBF"),
    "CRDRDZZJ": ("Paper1b_NatureWater", "MDMG47ZS", "GBF"),
    "SNZD9AU4": ("Paper1b_NatureWater-2", "MDMG47ZS", "GBF"),
    "UM8N5CRU": ("Paper1b_NatureWater-3", "MDMG47ZS", "GBF"),
    "G4N4I8VN": ("Paper1b_NatureWater-4", "MDMG47ZS", "GBF"),
    "XZ22GHJA": ("Paper3-WRR-LLM-Flood-ABM", "MDMG47ZS", "GBF"),
    "D7WBAFPU": ("Methodology-LLM-ABM", "XZ22GHJA", "GBF"),
    "W2FV7HXK": ("RQ1-Memory-Heterogeneity", "XZ22GHJA", "GBF"),
    "V74GSCPK": ("RQ2-Institutional-Feedback", "XZ22GHJA", "GBF"),
    "BI67K7TG": ("RQ3-Social-Information", "XZ22GHJA", "GBF"),
    "UNJ2ZNIW": ("WAGF-Paper", "MDMG47ZS", "GBF"),
    "4KDW9UZ9": ("WRR_WAGF_2026_Intro", "MDMG47ZS", "GBF"),
    "XJH8C6W6": ("WRR-Technical-Report", "MDMG47ZS", "GBF"),
    # survey paper
    "ZGQSEF9G": ("survey paper", None, "survey-paper"),
    "VGD2QAWL": ("influecning factors of RP and MB", "ZGQSEF9G", "survey-paper"),
    "AK4INJ99": ("LR", "ZGQSEF9G", "survey-paper"),
    "XUMBTXHF": ("Method", "ZGQSEF9G", "survey-paper"),
    "BTSNLGE9": ("Study area", "ZGQSEF9G", "survey-paper"),
    # Literature Review
    "MKFXT8VS": ("Literature Review", None, "lit-review"),
    "ZAJHRXA3": ("20260111_llm_agent_based_modeling", "MKFXT8VS", "lit-review"),
    "ENI38UPQ": ("20260112_llm_abm_disaster_flood", "MKFXT8VS", "lit-review"),
    "4UDDNN4F": ("20260112_llm_abm_flood_risk", "MKFXT8VS", "lit-review"),
    "I6GNS46Q": ("20260112_llm_agent_memory", "MKFXT8VS", "lit-review"),
    "RK2PG4TU": ("20260113_agentic_ai_components_abm", "MKFXT8VS", "lit-review"),
    "2N5EXU2W": ("20260113_llm_abm_flood", "MKFXT8VS", "lit-review"),
}

def safe_filename(author, year, title):
    author_last = re.sub(r'[^\w]', '', author.split(',')[0].split()[-1]).lower() if author else 'unknown'
    year_str = str(year) if year else 'nd'
    words = re.sub(r'[^\w\s]', '', title.lower()).split()
    stop = {'a','an','the','of','in','on','at','to','for','with','and','or','by','from','as','its','is','are','this','that'}
    key_words = [w for w in words if w not in stop][:4]
    short = '-'.join(key_words) if key_words else 'untitled'
    return f"{author_last}{year_str}-{short}.md"

def get_all_items(collection_key):
    items = []
    start = 0
    while True:
        url = f"{BASE}/collections/{collection_key}/items?itemType=-attachment&limit=100&start={start}"
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

def get_notes(item_key):
    url = f"{BASE}/items/{item_key}/children"
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

TAG_WIKI_MAP = {
    'pmt': '[[Protection-Motivation-Theory]]',
    'protection motivation': '[[Protection-Motivation-Theory]]',
    'abm': '[[Agent-Based-Modeling]]',
    'agent-based': '[[Agent-Based-Modeling]]',
    'agent based': '[[Agent-Based-Modeling]]',
    'llm': '[[LLM-Agents]]',
    'large language model': '[[LLM-Agents]]',
    'generative agent': '[[Generative-Agents]]',
    'memory': '[[Memory-Systems]]',
    'retrieval': '[[Memory-Systems]]',
    'flood risk': '[[Flood-Risk]]',
    'flood': '[[Flood-Risk]]',
    'risk perception': '[[Risk-Perception]]',
    'social vulnerability': '[[Social-Vulnerability]]',
    'social capital': '[[Social-Capital]]',
    'social network': '[[Social-Networks]]',
    'bounded rationality': '[[Bounded-Rationality]]',
    'active inference': '[[Active-Inference]]',
    'reinforcement learning': '[[Reinforcement-Learning]]',
    'socio-hydrology': '[[Socio-Hydrology]]',
    'sociohydrology': '[[Socio-Hydrology]]',
    'governance': '[[Governance]]',
    'multi-agent': '[[Multi-Agent-Systems]]',
    'multiagent': '[[Multi-Agent-Systems]]',
    'trust': '[[Trust-in-Risk-Management]]',
    'relocation': '[[Relocation-Decisions]]',
    'insurance': '[[Flood-Insurance]]',
    'place attachment': '[[Place-Attachment]]',
    'sem': '[[Structural-Equation-Modeling]]',
    'structural equation': '[[Structural-Equation-Modeling]]',
    'reflection': '[[Reflection-Metacognition]]',
    'metacognition': '[[Reflection-Metacognition]]',
    'adaptation': '[[Flood-Adaptation]]',
    'natural language': '[[Natural-Language-Processing]]',
}

def tags_to_wiki_links(tags):
    links = set()
    for tag in tags:
        tag_lower = tag.lower()
        for keyword, link in TAG_WIKI_MAP.items():
            if keyword in tag_lower:
                links.add(link)
    return sorted(links)

def make_raw_md(item_data, collections_list, notes):
    title = item_data['title'].replace('"', "'")
    authors = item_data['authors']
    year = item_data['year']
    journal = item_data['journal']
    doi = item_data['doi']
    abstract = item_data['abstract']
    tags = item_data['tags']
    key = item_data['key']

    author_str = '; '.join(authors) if authors else 'Unknown'
    tags_yaml = '[' + ', '.join(f'"{t}"' for t in tags) + ']' if tags else '[]'
    collections_yaml = '[' + ', '.join(f'"{c}"' for c in collections_list) + ']'

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

    abstract_section = f"\n## Abstract\n\n{abstract}\n" if abstract else ""
    doi_line = f'doi: "{doi}"' if doi else 'doi: ""'

    content = f"""---
title: "{title}"
authors: "{author_str}"
year: {year if year else 'null'}
journal: "{journal}"
{doi_line}
zotero-key: {key}
collections: {collections_yaml}
tags: {tags_yaml}
---

# {title}

**Authors:** {author_str}
**Year:** {year}
**Journal/Source:** {journal}
{"**DOI:** " + doi if doi else ""}
{abstract_section}{related_section}{notes_section}
---
*Source: Zotero key `{key}`*
"""
    return content

# ========== MAIN PROCESSING ==========

print("Starting Zotero extraction...")

all_items = {}
item_collections = defaultdict(list)

for ckey, (cname, parent, section) in COLLECTIONS.items():
    items = get_all_items(ckey)
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

os.makedirs(f"{KB}/raw", exist_ok=True)

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
    notes = get_notes(ikey)
    colls = item_collections[ikey]
    content = make_raw_md(idata, colls, notes)
    fname = filename_map[ikey] + '.md'
    filepath = os.path.join(KB, 'raw', fname)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    written += 1
    if written % 50 == 0:
        print(f"  Written {written} files...")

print(f"Written {written} raw/ files")

with open(os.path.join(KB, 'filename_map.json'), 'w', encoding='utf-8') as f:
    json.dump(filename_map, f)

combined = {}
for k, v in all_items.items():
    combined[k] = dict(v)
    combined[k]['collections'] = item_collections[k]
    combined[k]['filename'] = filename_map.get(k, '')
with open(os.path.join(KB, 'all_items.json'), 'w', encoding='utf-8') as f:
    json.dump(combined, f, ensure_ascii=False, indent=2)

print("Done!")
