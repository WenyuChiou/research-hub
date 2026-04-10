"""
Improve Obsidian graph by adding research-line tags to each paper.
This creates clear visual clusters in Graph View using tag-based filtering.

v2 - Expanded keywords, collection mapping, title scanning, and fallback logic.
"""
import os, re
import shutil
import sys as _sys
import time
from pathlib import Path
from pathlib import Path as _Path

_sys.path.insert(0, str(_Path(__file__).parent))
from hub_config import get_config as _get_config

_cfg = _get_config()
raw_dir = str(_cfg.raw)
hub_dir = str(_cfg.hub)


def make_backup(graph_path: Path) -> Path | None:
    """Backup graph.json before graph-related updates."""

    if not graph_path.exists():
        return None
    backup_path = graph_path.parent / f"{graph_path.name}.bak.{int(time.time())}"
    shutil.copy2(str(graph_path), str(backup_path))
    return backup_path


make_backup(_cfg.graph_json)

# Define 4 clear research lines + general-reference fallback
RESEARCH_LINES = {
    'flood-abm': {
        'label': 'Flood & ABM',
        'keywords': [
            # Core flood/hazard terms
            'flood', 'insurance', 'NFIP', 'buyout', 'retreat', 'inundation',
            'hurricane', 'disaster', 'hazard', 'resilience', 'vulnerability',
            'socio-hydro', 'risk perception', 'preparedness', 'adaptation',
            'agent-based', 'ABM', 'DYNAMO', 'simulation',
            # Expanded flood/water terms
            'FEMA', 'risk rating', 'floodplain', 'levee', 'dam', 'stormwater',
            'sea level', 'coastal', 'erosion', 'mitigation', 'evacuation',
            'hydrology', 'hydrological', 'hydroclimatic', 'streamflow',
            'watershed', 'catchment', 'water resource', 'river basin',
            'climate change', 'climate risk', 'precipitation', 'rainfall',
            'repetitive loss', 'elevation', 'house lifting', 'retrofit',
            'damage', 'loss estimation', 'exposure', 'claim',
            'land use', 'urban planning', 'zoning', 'managed retreat',
            'CRSS', 'Colorado River', 'Passaic', 'Rockaway',
            'institutional', 'water management', 'water treaty',
            'poverty', 'carless', 'vehicle', 'mobility', 'low-income',
            'disadvantage', 'census', 'economic characteristics',
        ],
        'collections': [
            'ABM', 'Flood-Simulation', 'Survey', 'survey paper', 'Literature Review',
            'Study area', 'study area', 'introduction',
            'Paper1b_NatureWater', 'Paper1b_NatureWater-3', 'Paper1b_NatureWater-4',
            'RQ2-Institutional-Feedback', 'WAGF-Paper',
            'vehicle', 'LR',
        ]
    },
    'llm-agent': {
        'label': 'LLM & Agent',
        'keywords': [
            # Core LLM terms
            'LLM', 'large language model', 'GPT', 'generative agent', 'multi-agent',
            'prompt', 'context engineering', 'hallucination', 'transformer',
            'reinforcement learning', 'AI agent', 'chatbot', 'NLP',
            # Expanded AI/ML terms
            'deep learning', 'neural network', 'machine learning', 'attention mechanism',
            'fine-tuning', 'embedding', 'token', 'diffusion model',
            'natural language', 'text generation', 'language model',
            'retrieval augmented', 'RAG', 'chain of thought', 'reasoning',
            'autonomous agent', 'tool use', 'function calling',
            # Cognitive architecture for agents
            'cognitive architecture', 'memory architecture', 'working memory',
            'active inference', 'free energy', 'bayesian surprise',
            'interference', 'inhibition', 'memory retrieval',
            'bounded rationality', 'dual process', 'thinking fast',
            'magical number', 'cognitive load',
            'social learning', 'communication layer', 'MAS',
        ],
        'collections': [
            'LLM AI agent', 'Reflection', 'Generative-Agents',
            'Memory-and-Cognition', 'RQ1-Memory-Heterogeneity',
            'Active-Inference', 'RQ3-Social-Information',
            'WRR_WAGF_2026_Intro', 'WRR-Technical-Report',
        ]
    },
    'social-behavior': {
        'label': 'Social & Behavior',
        'keywords': [
            # Core social terms
            'social capital', 'place attachment', 'community', 'equity',
            'environmental justice', 'racial', 'tenure', 'empathy',
            'norm', 'trust', 'social network', 'behavioral',
            # Expanded social/governance terms
            'governance', 'governed broker', 'GBF', 'stakeholder',
            'collective action', 'cooperation', 'social influence',
            'social information', 'opinion dynamics', 'cultural',
            'demographic', 'socioeconomic', 'inequality', 'gentrification',
            'displacement', 'migration', 'relocation',
            'health equity', 'health policy', 'population-level',
            'diversity', 'entropy', 'broker',
            'WRR-GBF', 'WAGF',
        ],
        'collections': [
            'GBF', 'Governed Broker Framework',
            '01-Theoretical-Foundations',
        ]
    },
    'methodology': {
        'label': 'Methodology',
        'keywords': [
            # Core method terms
            'ODD protocol', 'survey method', 'SEM', 'structural equation',
            'statistical', 'benchmark', 'evaluation', 'framework',
            'review', 'meta-analysis', 'validation',
            # Expanded method terms
            'cronbach', 'alpha', 'reliability', 'coefficient',
            'partial least squares', 'PLS', 'multigroup invariance',
            'Spearman-Brown', 'Pearson', 'correlation',
            'regression', 'factor analysis', 'latent variable',
            'psychometric', 'measurement model', 'scale development',
            'content analysis', 'coding scheme', 'inter-rater',
            'experiment design', 'sample size', 'power analysis',
            'Bayesian', 'Monte Carlo', 'bootstrap',
            'systematic review', 'scoping review', 'literature review',
            'methodology', 'methodological',
        ],
        'collections': [
            'Method', 'Methodology',
        ]
    },
    'general-reference': {
        'label': 'General Reference',
        'keywords': [],
        'collections': []
    }
}

# Parse all raw files
updated = 0
stats = {k: 0 for k in RESEARCH_LINES}
before_uncat = 0
after_uncat = 0

for f in sorted(os.listdir(raw_dir)):
    if not f.endswith('.md'):
        continue
    path = os.path.join(raw_dir, f)
    with open(path, 'r', encoding='utf-8') as fh:
        content = fh.read()

    m = re.match(r'^---\n(.*?)\n---', content, re.DOTALL)
    if not m:
        continue
    frontmatter = m.group(1)
    body = content[m.end():]

    # Get existing tags, collections, title
    tags_m = re.search(r'tags:\s*\[(.*?)\]', frontmatter)
    existing_tags = tags_m.group(1) if tags_m else ''
    coll_m = re.search(r'collections:\s*\[(.*?)\]', frontmatter)
    existing_colls = coll_m.group(1) if coll_m else ''
    title_m = re.search(r'title:\s*"?(.*?)"?\s*$', frontmatter, re.MULTILINE)
    title = title_m.group(1) if title_m else ''

    # Build comprehensive search text: filename + title + tags + collections + first 500 chars of body
    text = (f + ' ' + title + ' ' + existing_tags + ' ' + existing_colls + ' ' + body[:500]).lower()
    # Clean collection list for matching
    colls_lower = existing_colls.lower()

    assigned_lines = []
    for line_key, line_info in RESEARCH_LINES.items():
        if line_key == 'general-reference':
            continue  # fallback only
        # Check keywords against full text (title + tags + collections + body snippet)
        if any(kw.lower() in text for kw in line_info['keywords']):
            assigned_lines.append(line_key)
            continue
        # Check collections (partial match against collection strings)
        if 'collections' in line_info and line_info['collections']:
            if any(c.lower() in colls_lower for c in line_info['collections']):
                assigned_lines.append(line_key)

    # Fallback: assign to general-reference so it still gets a color
    if not assigned_lines:
        assigned_lines = ['general-reference']
        after_uncat += 1
    
    # Track if it was previously uncategorized
    if 'research/uncategorized' in existing_tags:
        before_uncat += 1

    # Remove old uncategorized tag if we now have a real category
    if assigned_lines != ['general-reference'] and assigned_lines != ['uncategorized']:
        existing_tags = re.sub(r',?\s*"research/uncategorized"', '', existing_tags)
        existing_tags = re.sub(r'"research/uncategorized",?\s*', '', existing_tags)
        # Also remove old uncategorized category
        frontmatter = re.sub(r'\ncategory:\s*"uncategorized"', '', frontmatter)
        # Re-extract tags_m after frontmatter change
        tags_m = re.search(r'tags:\s*\[(.*?)\]', frontmatter)
        if tags_m:
            existing_tags = tags_m.group(1)
            existing_tags = re.sub(r',?\s*"research/uncategorized"', '', existing_tags)
            existing_tags = re.sub(r'"research/uncategorized",?\s*', '', existing_tags)

    # Add research-line tags to frontmatter
    for line in assigned_lines:
        tag = f'research/{line}'
        if tag not in existing_tags:
            if existing_tags.strip():
                existing_tags = existing_tags.rstrip().rstrip(',') + f', "{tag}"'
            else:
                existing_tags = f'"{tag}"'
        if line in stats:
            stats[line] += 1

    # Update the tags line in frontmatter
    if tags_m:
        new_fm = frontmatter[:tags_m.start(1)] + existing_tags + frontmatter[tags_m.end(1):]
    else:
        # Add tags line before the closing ---
        new_fm = frontmatter + f'\ntags: [{existing_tags}]'

    # Update or add category field
    primary = assigned_lines[0]
    cat_pattern = re.search(r'category:\s*"?[^"\n]*"?', new_fm)
    if cat_pattern:
        new_fm = new_fm[:cat_pattern.start()] + f'category: "{primary}"' + new_fm[cat_pattern.end():]
    else:
        new_fm += f'\ncategory: "{primary}"'

    new_content = f'---\n{new_fm}\n---{body}'

    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(new_content)
    updated += 1

print(f'Updated {updated} papers')
print(f'Previously uncategorized (had research/uncategorized tag): {before_uncat}')
print(f'Still uncategorized after update (general-reference): {after_uncat}')
print()
for k, v in stats.items():
    print(f'  {k}: {v} papers')
print('DONE')
