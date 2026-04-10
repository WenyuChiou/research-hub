"""
Fix orphan papers: find papers with no hub links and assign them
to the closest topic based on title/abstract keyword matching.
Also ensure every paper has at least one [[hub link]].
"""
import os, re

from research_hub.config import get_config as _get_config

_cfg = _get_config()
raw_dir = str(_cfg.raw)
hub_dir = str(_cfg.hub)

# All hub topics that exist
hub_topics = [f.replace('.md','') for f in os.listdir(hub_dir) if f.endswith('.md')]
print(f"Hub topics: {len(hub_topics)}")

# Keyword mapping for each wiki topic
topic_keywords = {
    'Agent-Based-Modeling': ['agent-based', 'abm', 'dynamo', 'simulation', 'computational model', 'simulate'],
    'Flood-Insurance': ['insurance', 'nfip', 'premium', 'risk rating', 'underwriting', 'coverage'],
    'Flood-Risk': ['flood risk', 'flood model', 'inundation', 'flood damage', 'flood hazard', 'coastal flood'],
    'LLM-Agents': ['llm', 'large language', 'gpt', 'chatgpt', 'language model', 'prompt engineer'],
    'Place-Attachment': ['place attachment', 'sense of place', 'community attachment', 'neighborhood'],
    'Social-Vulnerability': ['social vulnerability', 'vulnerability index', 'sovi', 'marginalized'],
    'Managed-Retreat': ['retreat', 'buyout', 'relocation', 'acquisition', 'voluntary purchase'],
    'Social-Capital': ['social capital', 'bonding capital', 'bridging capital', 'civic engagement'],
    'Risk-Perception': ['risk perception', 'perceived risk', 'worry', 'dread', 'risk awareness'],
    'Disaster-Preparedness': ['preparedness', 'mitigation', 'protective action', 'evacuation', 'early warning'],
    'Climate-Adaptation': ['climate change', 'adaptation', 'sea level', 'resilience', 'global warming'],
    'Generative-Agents': ['generative agent', 'believable agent', 'simulacra', 'persona', 'role-play'],
    'Multi-Agent-Systems': ['multi-agent', 'multiagent', 'collective behavior', 'emergent behavior'],
    'Bounded-Rationality': ['bounded rationality', 'heuristic', 'cognitive bias', 'prospect theory', 'decision-making'],
    'Socio-Hydrology': ['socio-hydro', 'human-flood', 'coupled system', 'co-evolution'],
    'Reflection-Metacognition': ['reflection', 'metacognition', 'self-evaluation', 'chain of thought'],
    'Protection-Motivation-Theory': ['protection motivation', 'pmt', 'threat appraisal', 'coping appraisal'],
    'Relocation-Decisions': ['relocation', 'displacement', 'post-disaster', 'housing recovery', 'mobile home'],
    'Trust-in-Risk-Management': ['trust', 'institutional trust', 'government trust', 'credibility'],
    'Reinforcement-Learning': ['reinforcement learning', 'q-learning', 'reward', 'policy gradient'],
    'Memory-Systems': ['memory', 'forgetting', 'recall', 'interference', 'retrieval'],
    'Governance': ['governance', 'policy', 'regulation', 'institutional', 'broker framework'],
    'Social-Networks': ['social network', 'network analysis', 'peer effect', 'diffusion'],
    'Active-Inference': ['active inference', 'free energy', 'bayesian brain'],
    'Structural-Equation-Modeling': ['structural equation', 'sem', 'path analysis', 'latent variable'],
    'Flood-Adaptation': ['flood adaptation', 'dry floodproof', 'wet floodproof', 'elevation', 'retrofit'],
}

orphan_count = 0
fixed_count = 0

for f in sorted(os.listdir(raw_dir)):
    if not f.endswith('.md'): continue
    path = os.path.join(raw_dir, f)
    with open(path, 'r', encoding='utf-8') as fh:
        content = fh.read()
    
    # Check if paper has any wiki links
    existing_links = re.findall(r'\[\[([^\]]+)\]\]', content)
    existing_hub = [l.split('|')[0] for l in existing_links if l.split('|')[0] in hub_topics]
    
    if existing_hub:
        continue  # Already linked, skip
    
    orphan_count += 1
    
    # Find best matching topics
    text = content.lower()
    scores = {}
    for topic, keywords in topic_keywords.items():
        if topic not in hub_topics:
            continue
        score = sum(1 for kw in keywords if kw.lower() in text)
        if score > 0:
            scores[topic] = score
    
    if not scores:
        # Fallback: try filename
        fname_lower = f.lower()
        for topic, keywords in topic_keywords.items():
            if topic not in hub_topics:
                continue
            score = sum(1 for kw in keywords if kw.lower().replace(' ','-') in fname_lower or kw.lower().replace(' ','') in fname_lower)
            if score > 0:
                scores[topic] = score
    
    if not scores:
        continue  # Truly no match
    
    # Take top 2 matches
    top_topics = sorted(scores, key=scores.get, reverse=True)[:2]
    wiki_links_str = '  '.join(f'[[{t}]]' for t in top_topics)
    
    # Add Related Concepts section
    if '## Related Concepts' in content:
        content = re.sub(
            r'## Related Concepts\n\n.*?\n',
            f'## Related Concepts\n\n{wiki_links_str}\n',
            content, count=1
        )
    elif '## Notes' in content:
        content = content.replace(
            '## Notes',
            f'## Related Concepts\n\n{wiki_links_str}\n\n## Notes'
        )
    else:
        content += f'\n## Related Concepts\n\n{wiki_links_str}\n'
    
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(content)
    fixed_count += 1

print(f'Orphan papers (no wiki links): {orphan_count}')
print(f'Fixed (assigned to topics): {fixed_count}')
print(f'Remaining unlinked: {orphan_count - fixed_count}')
print('DONE')
