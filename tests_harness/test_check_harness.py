"""Tests of the documentation validator, not of the Stellaris product."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'check_harness.py'
spec = importlib.util.spec_from_file_location('check_harness', SCRIPT)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class HarnessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.feature = {'id': 'F-001', 'title': 'Demo', 'status': 'planned', 'docs': ['docs/spec.md'], 'evidence': []}
        self.task = {'id': 'TASK-001', 'title': 'Demo', 'status': 'todo', 'feature_ids': ['F-001'], 'depends_on': [], 'eval_ids': ['E-001'], 'docs': ['docs/spec.md'], 'acceptance': ['Verified example'], 'evidence': []}
        self.case = {'id': 'E-001', 'title': 'Demo', 'status': 'not_run', 'feature_ids': ['F-001'], 'fixture': 'synthetic-demo', 'input': 'Example', 'expected': ['Example'], 'evidence': []}
        self.state = {'schema_version': 1, 'active_task': None, 'next_task': 'TASK-001', 'last_session': 'harness/sessions/start.md'}
        self.put('docs/spec.md', '# Specification\n')
        self.put('harness/sessions/start.md', '# Not implemented\n')
        self.put('README.md', '[Spec](docs/spec.md)\n')
        self.save()

    def put(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')

    def save(self, extra_tasks=None):
        self.put('harness/features.json', json.dumps({'schema_version': 1, 'features': [self.feature]}))
        self.put('harness/tasks.json', json.dumps({'schema_version': 1, 'tasks': [self.task] + (extra_tasks or [])}))
        self.put('harness/evals.jsonl', json.dumps(self.case) + '\n')
        self.put('harness/state.json', json.dumps(self.state))

    def errors(self):
        return module.validate(self.root)[0]

    def test_valid_planned(self):
        self.assertEqual(self.errors(), [])

    def test_duplicate_task_id(self):
        self.save([dict(self.task)])
        self.assertTrue(any('duplicate id' in e for e in self.errors()))

    def test_cycle(self):
        self.task['depends_on'] = ['TASK-001']
        self.save()
        self.assertTrue(any('dependency cycle' in e for e in self.errors()))

    def test_missing_eval_reference(self):
        self.task['eval_ids'] = ['E-999']
        self.save()
        self.assertTrue(any('unknown eval_ids' in e for e in self.errors()))

    def test_done_requires_evidence_and_pass(self):
        self.task['status'] = 'done'
        self.save()
        errors = self.errors()
        self.assertTrue(any('requires evidence' in e for e in errors))
        self.assertTrue(any('evaluation not passed' in e for e in errors))

    def test_verified_requires_tasks(self):
        self.feature['status'] = 'verified'
        self.save()
        self.assertTrue(any('verified without' in e for e in self.errors()))

    def test_pass_requires_evidence(self):
        self.case['status'] = 'pass'
        self.save()
        self.assertTrue(any('E-001: completion requires evidence' in e for e in self.errors()))

    def test_broken_markdown_link(self):
        self.put('README.md', '[Missing](docs/missing.md)\n')
        self.assertTrue(any('broken/unsafe link' in e for e in self.errors()))

    def test_external_and_heading_links_are_not_fetched(self):
        self.put('README.md', '[Web](https://example.invalid/page) [Anchor](#section)\n')
        self.assertEqual(self.errors(), [])

    def test_unicode_relative_link(self):
        self.put('docs/\uac80\uc99d.md', '# Unicode\n')
        self.put('README.md', '[Unicode](docs/\uac80\uc99d.md)\n')
        self.assertEqual(self.errors(), [])

    def test_unsafe_evidence_path(self):
        self.task['evidence'] = ['../outside.txt']
        self.save()
        self.assertTrue(any('unsafe file' in e for e in self.errors()))

    def test_blocked_requires_reason(self):
        self.task['status'] = 'blocked'
        self.state['next_task'] = None
        self.save()
        self.assertTrue(any('blocked requires blocker' in e for e in self.errors()))

    def test_active_task_consistency(self):
        self.task['status'] = 'doing'
        self.save()
        self.assertTrue(any('active_task' in e for e in self.errors()))

    def test_unknown_status(self):
        self.task['status'] = 'probably_done'
        self.save()
        self.assertTrue(any('invalid status' in e for e in self.errors()))

    def test_invalid_json(self):
        self.put('harness/features.json', '{not json')
        self.assertTrue(self.errors())

    def test_completed_harness_allows_no_next_task(self):
        evidence = ['harness/evidence/result.txt']
        self.put(evidence[0], 'Synthetic execution evidence for validator test only.\n')
        for obj, status in ((self.feature, 'verified'), (self.task, 'done'), (self.case, 'pass')):
            obj['status'], obj['evidence'] = status, evidence
        self.state['next_task'] = None
        self.save()
        self.assertEqual(self.errors(), [])

    def test_cli_distinguishes_product_tests(self):
        result = subprocess.run([sys.executable, str(SCRIPT), '--root', str(self.root)], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload['harness_valid'])
        self.assertFalse(payload['product_tests_executed'])

    def test_malformed_list_fails_without_traceback(self):
        self.task['depends_on'] = None
        self.save()
        result = subprocess.run([sys.executable, str(SCRIPT), '--root', str(self.root)], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 1)
        self.assertNotIn('Traceback', result.stderr)


if __name__ == '__main__':
    unittest.main()
