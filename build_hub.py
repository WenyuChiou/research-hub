import os, re
import sys as _sys
from pathlib import Path as _Path

# Merge mapping: normalize duplicate/typo Zotero collection names to canonical wiki names
WIKI_MERGE = {
    "Agent-Based Model": "ABM",
    "agent-based model": "ABM",
    "Agent-Based Modeling": "ABM",
    "Soical capital": "Social Capital",
    "Social norm/ Social capital": "Social Capital",
    "Soical Vulnerability": "Social Vulnerability",
    "Study area": "Study Area",
    "study area": "Study Area",
    "Flood insurance": "Insurance & Risk Transfer",
    "Insurance": "Insurance & Risk Transfer",
    "survey": "Survey Methods",
    "survey paper": "Survey Methods",
    "LR": "Literature Review",
    "SM": "Social Media",
    "SEM": "Structural Equation Modeling",
    "Buoyout": "Buyout Programs",
}

def normalize_collections(collections):
    """Apply WIKI_MERGE to normalize collection names, deduplicating results."""
    normalized = []
    seen = set()
    for c in collections:
        canonical = WIKI_MERGE.get(c, c)
        if canonical.lower() not in seen:
            seen.add(canonical.lower())
            normalized.append(canonical)
    return normalized

_sys.path.insert(0, str(_Path(__file__).parent))
from hub_config import get_config as _get_config

_cfg = _get_config()
raw_dir = str(_cfg.raw)
hub_dir = str(_cfg.hub)
proj_dir = str(_cfg.projects)
root = str(_cfg.root)

os.makedirs(hub_dir, exist_ok=True)
os.makedirs(proj_dir, exist_ok=True)

# Parse all raw files (recursively scan raw/ and all subdirectories)
papers = []
all_md_files = []
for dirpath, dirnames, filenames in os.walk(raw_dir):
    for f in sorted(filenames):
        if f.endswith('.md'):
            all_md_files.append((dirpath, f))

for dirpath, f in all_md_files:
    path = os.path.join(dirpath, f)
    with open(path, 'r', encoding='utf-8') as fh:
        content = fh.read()
    m = re.match(r'^---\n(.*?)\n---', content, re.DOTALL)
    if not m: continue
    meta = {}
    for line in m.group(1).split('\n'):
        if ':' in line:
            key = line.split(':')[0].strip()
            val = ':'.join(line.split(':')[1:]).strip().strip('"')
            meta[key] = val
    # Parse collections array and normalize via WIKI_MERGE
    coll_m = re.search(r'collections:\s*\[(.*?)\]', m.group(1))
    if coll_m:
        raw_colls = [c.strip().strip('"').strip("'") for c in coll_m.group(1).split(',')]
        meta['collections'] = normalize_collections(raw_colls)
    # Parse tags array
    tags_m = re.search(r'tags:\s*\[(.*?)\]', m.group(1))
    if tags_m:
        meta['tags'] = [t.strip().strip('"').strip("'") for t in tags_m.group(1).split(',')]
    # Compute relative path from knowledge-base root for proper wiki links
    rel_dir = os.path.relpath(dirpath, root).replace('\\', '/')
    if rel_dir == 'raw':
        meta['filename'] = f.replace('.md','')
    else:
        meta['filename'] = rel_dir + '/' + f.replace('.md','')
    meta['title_line'] = meta.get('title', f.replace('.md',''))
    papers.append(meta)

print(f'Parsed {len(papers)} papers')

# Topic mapping for wiki pages
topic_map = {
    'Agent-Based-Modeling': {
        'keywords': ['agent-based', 'ABM', 'DYNAMO', 'agent based', 'multi-agent'],
        'desc': 'Agent-based modeling approaches for simulating human behavior in complex systems.'
    },
    'Flood-Insurance': {
        'keywords': ['flood insurance', 'NFIP', 'insurance', 'premium', 'Risk Rating'],
        'desc': 'National Flood Insurance Program, premium structures, and insurance market dynamics.'
    },
    'Flood-Risk': {
        'keywords': ['flood risk', 'flood inundation', 'flood fragility', 'coastal flood', 'flood model'],
        'desc': 'Flood risk assessment, modeling, and management strategies.'
    },
    'LLM-Agents': {
        'keywords': ['LLM', 'large language model', 'generative agent', 'GPT', 'AI-driven', 'AI agent'],
        'desc': 'Large language model applications in agent simulation and decision-making.'
    },
    'Place-Attachment': {
        'keywords': ['place attachment', 'community attachment', 'neighborhood attachment'],
        'desc': 'How emotional bonds to places influence disaster response and recovery decisions.'
    },
    'Social-Vulnerability': {
        'keywords': ['social vulnerability', 'racial inequit', 'environmental justice', 'equity', 'socioeconomic'],
        'desc': 'Social vulnerability, equity, and environmental justice in disaster contexts.'
    },
    'Managed-Retreat': {
        'keywords': ['managed retreat', 'buyout', 'relocation', 'acquisition'],
        'desc': 'Managed retreat programs, voluntary buyouts, and post-disaster relocation.'
    },
    'Disaster-Preparedness': {
        'keywords': ['preparedness', 'mitigation', 'risk perception', 'protective action'],
        'desc': 'Household disaster preparedness, risk perception, and protective behavior.'
    },
    'Climate-Adaptation': {
        'keywords': ['climate change', 'adaptation', 'sea level rise', 'resilience'],
        'desc': 'Climate change adaptation strategies and resilience building.'
    }
}

# Build wiki pages
for topic, info in topic_map.items():
    matched = []
    for p in papers:
        text = (p.get('title_line','') + ' ' + ' '.join(p.get('tags',[])) + ' ' + ' '.join(p.get('collections',[]))).lower()
        if any(kw.lower() in text for kw in info['keywords']):
            matched.append(p)
    
    content = f"""---
type: hub-topic
papers: {len(matched)}
---

# {topic.replace('-',' ')}

{info['desc']}

## Key Papers ({len(matched)})

"""
    for p in sorted(matched, key=lambda x: x.get('year','0'), reverse=True):
        content += f"- [[{p['filename']}|{p['title_line'][:80]}]] ({p.get('year','n.d.')})\n"
    
    content += f"\n## Related Topics\n\n"
    other_topics = [t for t in topic_map if t != topic]
    content += ' '.join(f'[[{t}]]' for t in other_topics[:5]) + '\n'
    
    hub_path = os.path.join(hub_dir, f'{topic}.md')
    with open(hub_path, 'w', encoding='utf-8') as fh:
        fh.write(content)
    print(f'  Hub: {topic}.md ({len(matched)} papers)')

# Build project pages
projects = {
    'ABM-Paper': {
        'desc': 'Agent-based model for flood insurance decision-making with LLM-powered agents.',
        'status': 'In Progress',
        'collections': ['ABM', 'Flood-Simulation', 'LLM AI agent']
    },
    'Survey-Paper': {
        'desc': 'Survey of computational approaches to flood risk and insurance modeling.',
        'status': 'In Progress',
        'collections': ['Survey', 'Literature Review', 'survey paper']
    },
    'Governed-Broker-Framework': {
        'desc': 'Governed Broker Framework for AI-mediated flood insurance markets.',
        'status': 'Planning',
        'collections': ['GBF', 'Governed Broker Framework']
    }
}

for proj_name, info in projects.items():
    matched = []
    for p in papers:
        p_colls = [c.lower() for c in (p.get('collections') or [])]
        if any(c.lower() in p_colls for c in info['collections']):
            matched.append(p)
    
    content = f"""---
type: project
status: {info['status']}
papers: {len(matched)}
---

# {proj_name.replace('-',' ')}

**Status:** {info['status']}

{info['desc']}

## Source Papers ({len(matched)})

"""
    for p in sorted(matched, key=lambda x: x.get('year','0'), reverse=True):
        content += f"- [ ] [[{p['filename']}|{p['title_line'][:80]}]] ({p.get('year','n.d.')})\n"
    
    proj_path = os.path.join(proj_dir, f'{proj_name}.md')
    with open(proj_path, 'w', encoding='utf-8') as fh:
        fh.write(content)
    print(f'  Project: {proj_name}.md ({len(matched)} papers)')

# Build root index
index_content = f"""---
type: index
total_papers: {len(papers)}
---

# Knowledge Base Index

Total papers: **{len(papers)}**

## Research Projects

- ABM Paper — Agent-based flood insurance model
- Survey Paper — Computational flood risk survey
- Governed Broker Framework — AI-mediated insurance markets

## Research Hub

"""
for topic in sorted(topic_map.keys()):
    index_content += f"- {topic.replace('-',' ')}\n"

index_content += f"""
## All Papers by Year

"""
by_year = {}
for p in papers:
    yr = p.get('year', 'Unknown')
    by_year.setdefault(yr, []).append(p)

for yr in sorted(by_year.keys(), reverse=True):
    index_content += f"### {yr}\n\n"
    for p in by_year[yr]:
        index_content += f"- {p['title_line'][:80]} ({p.get('year','n.d.')})\n"
    index_content += "\n"

index_path = os.path.join(root, 'index.md')
with open(index_path, 'w', encoding='utf-8') as fh:
    fh.write(index_content)
print(f'  Index: index.md')
print('DONE')
