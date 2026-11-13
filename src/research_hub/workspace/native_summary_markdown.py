"""Plain Markdown transfer, not application acceptance or a semantic verdict."""
import re


def _text(value):
    # Treat source/author prose as text, not HTML, Markdown links or embeds.
    value = str(value).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    return re.sub(r'([\\`*_{}\[\]()#+.!|~=-])', r'\\\1', value).replace('\n', '\n    ')


def render(summary):
    from .native_summary import SECTIONS
    lines = ['# ' + _text(summary['source']['title']), '',
             'Human acceptance: pending', 'Semantic support: not_assessed',
             'This authored candidate is not an independently verified scientific summary.', '',
             'Source locator: ' + _text(summary['source']['locator']),
             'Reading scope: ' + _text(summary['reading_scope']),
             'Project: ' + _text(summary['project_id']),
             'Source record: ' + _text(summary['source_record_id']),
             'Source revision: ' + _text(summary['source_revision']), '', '## Evidence bindings']
    for selection in summary['selections']:
        lines.append('- Artifact: ' + _text(selection['artifact_id']))
        for key in ('sha256', 'text_sha256', 'start', 'end'):
            lines.append('  ' + key + ': ' + _text(selection[key]))
    lines += ['', 'Offsets: zero-based, half-open Python Unicode code points in the source file.']
    for section in SECTIONS:
        items = summary['sections'][section]
        lines += ['', '## ' + section.replace('_', ' ').title()]
        for item in items:
            lines += ['- [' + item['status'] + '] ' + _text(item['text']),
                      '  Reason: ' + _text(item['reason'])]
            for quote in item['evidence']:
                lines += ['  Evidence (' + _text(quote['artifact_id']) + ', ' +
                          str(quote['start']) + ':' + str(quote['end']) + '): ' + _text(quote['quote'])]
    return '\n'.join(lines) + '\n'
