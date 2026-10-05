import contextlib
import io
import json
from pathlib import Path
import random
import tempfile
import unittest
from spanledger import analyze, duration, main, merge


def span(key, start, end, parent=None, service='api'):
    return dict(id=key, name=key, service=service, start_us=start, end_us=end, parent=parent)


class AccountingTests(unittest.TestCase):
    def test_overlapping_children(self):
        r = analyze([span('root', 0, 100), span('a', 10, 70, 'root'), span('b', 40, 90, 'root')])
        root = next(x for x in r['spans'] if x['id'] == 'root')
        self.assertEqual(root['self_us'], 20)
        self.assertEqual(root['child_union_us'], 80)
        self.assertEqual(root['child_overlap_us'], 30)
        self.assertEqual(r['active_union_us'], 100)

    def test_grandchild_not_subtracted_twice(self):
        r = analyze([span('r', 0, 100), span('c', 10, 90, 'r'), span('g', 20, 30, 'c')])
        rows = {s['id']:s for s in r['spans']}
        self.assertEqual(rows['r']['self_us'], 20)
        self.assertEqual(rows['c']['self_us'], 70)

    def test_gaps(self):
        r = analyze([span('a', 10, 20), span('b', 30, 45)])
        self.assertEqual(r['gaps'], [[20, 30]])
        self.assertEqual(r['window_us'], 35)
        self.assertEqual(r['uncovered_us'], 10)

    def test_touching_and_zero(self):
        self.assertEqual(merge([(0, 5), (5, 10), (3, 3)]), [[0, 10]])
        r = analyze([span('a', 0, 0), span('b', 10, 10)])
        self.assertEqual(r['uncovered_us'], 10)

    def test_single_zero(self):
        self.assertEqual(analyze([span('a', 7, 7)])['window_us'], 0)

    def test_random_union_against_integer_oracle(self):
        rng = random.Random(42)
        for _ in range(1000):
            intervals = [tuple(sorted((rng.randrange(30), rng.randrange(30)))) for _ in range(20)]
            expected = len({i for a, b in intervals for i in range(a, b)})
            self.assertEqual(duration(intervals), expected)

    def test_order_independence(self):
        items = [span('r',0,100), span('c',10,20,'r', 'db')]
        self.assertEqual(analyze(items), analyze(list(reversed(items))))

    def test_service_union_not_sum(self):
        r = analyze([span('a',0,10),span('b',5,15)])
        self.assertEqual(r['services'][0]['active_union_us'], 15)
        self.assertEqual(r['services'][0]['sum_self_us'], 20)

    def test_cycle(self):
        for items in [[span('a',0,10,'a')], [span('a',0,10,'b'),span('b',0,10,'a')]]:
            with self.assertRaises(ValueError): analyze(items)

    def test_parent_errors(self):
        for items in [[span('a',0,10,'missing')], [span('a',0,10),span('b',1,11,'a')]]:
            with self.assertRaises(ValueError): analyze(items)

    def test_invalid_input(self):
        for items in [None, [], {}, [span('a',-1,10)], [span('a',10,0)],
                      [span('a',True,10)], [span('a',1.5,10)],
                      [span('a',0,10), span('a',0,10)], [span('',0,10)], [{}]]:
            with self.assertRaises(ValueError): analyze(items)

    def test_deep_tree(self):
        items = [span(str(i),0,10, str(i-1) if i else None) for i in range(2000)]
        self.assertEqual(analyze(items)['span_count'], 2000)

    def test_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'trace.json'
            path.write_text(json.dumps([span('a',0,10)]))
            with contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(main([str(path)]), 0)
            self.assertEqual(json.loads(out.getvalue())['active_union_us'], 10)
            for text in ['{', '[{"id":"a","id":"b"}]', '[]']:
                path.write_text(text)
                with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()) as out:
                    with self.assertRaises(SystemExit) as e: main([str(path)])
                self.assertEqual(e.exception.code, 2)
                self.assertEqual(out.getvalue(), '')


if __name__ == '__main__': unittest.main()
