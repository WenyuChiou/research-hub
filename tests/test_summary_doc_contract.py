"""Documentation contracts; no provider/model execution."""
from pathlib import Path
import hashlib
import unittest
ROOT=Path(__file__).resolve().parents[1]
class SummaryDocContract(unittest.TestCase):
 def test_optional_mcp(self):
  guide=(ROOT/'docs/first-10-minutes.md').read_text()
  self.assertNotIn('`[mcp]` is included by default',guide)
  self.assertIn('install `research-hub-pipeline[mcp]` explicitly',guide)
 def test_current_skill_truth_and_mirror(self):
  text=(ROOT/'skills/paper-summarize/SKILL.md').read_text()
  self.assertEqual(text,(ROOT/'src/research_hub/skills_data/paper-summarize/SKILL.md').read_text())
  self.assertNotIn('- Idempotent:',text)
  self.assertNotIn('one transactional unit per paper',text)
  self.assertIn('not preview flags',text)
  self.assertIn('explicitly owned',text)
 def test_historical_profile_bytes_and_constructors(self):
  expected={'paper-summarize/SKILL.md':'385162d00efc94406fd41aacb30aecbb4ee219dabc4b5184c8573ac96af6b800','research-hub/references/research-protocol.md':'b5eeb2dde4430a5c88f55e586fa5f5fd262da8402815d61fc1c906b211f1d109','research-hub/references/source-claim-audit.md':'9775a88b2c3845c4dcf3424c0e76af6c7c104e129b0e91d0ba16bcdce792d881'}
  for path,sha in expected.items():self.assertEqual(hashlib.sha256((ROOT/'src/research_hub/skills_data/_profiles/abstract-draft-instructions-v1'/path).read_bytes()).hexdigest(),sha)
  from research_hub.workspace.research_draft import AbstractDraftAdapter
  for version in (1,2,3):AbstractDraftAdapter(version)
if __name__=='__main__':unittest.main()
