from pathlib import Path
import sys
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

from course_sim import NODES, PRESETS, SINGLE_NODE, Job, gantt_svg, schedule  # noqa: E402


def by_id(placements):
    return {p.job_id: p for p in placements}


class FifoBackfillTest(unittest.TestCase):
    def setUp(self):
        self.jobs, self.nodes = PRESETS['先來先服務／回填']
        self.assertIs(self.nodes, SINGLE_NODE)

    def test_without_backfill(self):
        p = by_id(schedule(self.jobs, backfill=False, nodes=self.nodes))
        self.assertEqual((p['A'].node, p['A'].start, p['A'].end, p['A'].slots), ('cpu01', 0, 4, (0, 1, 2)))
        self.assertEqual((p['B'].start, p['B'].end), (4, 7))
        self.assertEqual((p['C'].start, p['C'].end), (7, 9))
        self.assertEqual(p['A'].reason, '')
        self.assertEqual(p['B'].reason, 'Resources')
        self.assertEqual(p['C'].reason, 'Priority')

    def test_with_backfill(self):
        p = by_id(schedule(self.jobs, backfill=True, nodes=self.nodes))
        self.assertEqual((p['A'].start, p['A'].end), (0, 4))
        self.assertEqual((p['C'].start, p['C'].end, p['C'].slots), (0, 2, (3,)))
        self.assertEqual((p['B'].start, p['B'].end), (4, 7))
        self.assertEqual(p['C'].reason, '')
        self.assertEqual(p['B'].reason, 'Resources')


class GpuPartitionTest(unittest.TestCase):
    def test_gpu_preset(self):
        jobs, nodes = PRESETS['GPU 分區']
        self.assertIs(nodes, NODES)
        p = by_id(schedule(jobs, nodes=nodes))
        self.assertEqual((p['A'].node, p['A'].start, p['A'].end), ('cpu01', 0, 3))
        self.assertEqual((p['G1'].node, p['G1'].start, p['G1'].end), ('gpu01', 0, 4))
        self.assertEqual((p['G2'].node, p['G2'].start, p['G2'].end), ('gpu01', 4, 6))


class UnschedulableTest(unittest.TestCase):
    def test_too_many_cpus(self):
        [p] = schedule([Job('X', 5, 1)], nodes=SINGLE_NODE)
        self.assertIsNone(p.node)
        self.assertIsNone(p.start)
        self.assertIsNone(p.end)
        self.assertTrue(p.reason.startswith('ReqNodeNotAvail'))

    def test_does_not_block_queue(self):
        for backfill in (False, True):
            p = by_id(schedule([Job('X', 5, 1), Job('Y', 1, 2)], backfill=backfill, nodes=SINGLE_NODE))
            self.assertIsNone(p['X'].node)
            self.assertEqual((p['Y'].node, p['Y'].start, p['Y'].end, p['Y'].reason), ('cpu01', 0, 2, ''))


class GanttTest(unittest.TestCase):
    def test_svg_parses(self):
        for name, (jobs, nodes) in PRESETS.items():
            svg = gantt_svg(schedule(jobs, nodes=nodes), nodes=nodes)
            root = ET.fromstring(svg)
            self.assertTrue(root.tag.endswith('svg'), name)
        svg = gantt_svg(schedule([Job('X<&>', 5, 1), Job('Y', 1, 2)], nodes=SINGLE_NODE), nodes=SINGLE_NODE)
        ET.fromstring(svg)
        self.assertIn('無法排程：X&lt;&amp;&gt;（ReqNodeNotAvail）', svg)


if __name__ == '__main__':
    unittest.main()
