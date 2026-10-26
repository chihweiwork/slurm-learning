from pathlib import Path
import sys
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

import course_diagrams  # noqa: E402
from course_diagrams import strip_style  # noqa: E402

EXPECTED = {
    'COMPONENTS': 8, 'JOB_STATES': 6, 'ALLOCATION_STEP_TASK': 5, 'SCHEDULING': 5, 'ARRAY_DEPENDENCY': 4,
    'GPU_GRES': 4, 'FAILURE_LAYERS': 4, 'ACCOUNTING_FLOW': 3, 'DRAIN_FLOW': 4,
}
SVG = '{http://www.w3.org/2000/svg}'


def classes(root):
    return {cls for el in root.iter() for cls in el.get('class', '').split()}


class DiagramTests(unittest.TestCase):
    def test_all_lists_every_diagram_in_order(self):
        self.assertEqual(course_diagrams.ALL, [getattr(course_diagrams, name) for name in EXPECTED])

    def test_step_counts_and_text(self):
        for name, count in EXPECTED.items():
            diagram = getattr(course_diagrams, name)
            with self.subTest(name):
                self.assertEqual(len(diagram.steps), count)
                self.assertTrue(diagram.title)
                for step in diagram.steps:
                    self.assertTrue(step.caption and step.detail)
                    self.assertNotRegex(step.caption, '^[①-⑨]')

    def test_autoplay_render(self):
        for diagram in course_diagrams.ALL:
            with self.subTest(diagram.id):
                html = diagram.render(None)
                self.assertTrue(html.startswith(f'<div class="dg-{diagram.id}"><style>'))
                self.assertIn(f'@keyframes dg-{diagram.id}-0', html)
                self.assertIn(f'.dg-{diagram.id} .s0 {{ animation: dg-{diagram.id}-0', html)
                root = ET.fromstring(strip_style(html))
                self.assertEqual(root.tag, f'{SVG}svg')
                found = classes(root)
                for i in range(len(diagram.steps)):
                    self.assertIn(f's{i}', found)

    def test_static_render_per_step(self):
        for diagram in course_diagrams.ALL:
            for k in range(len(diagram.steps)):
                with self.subTest(diagram.id, step=k):
                    svg = diagram.render(k)
                    self.assertNotIn('<style', svg)
                    root = ET.fromstring(svg)
                    groups = [g for g in root.iter(f'{SVG}g') if g.get('class', '').startswith('s')]
                    self.assertEqual({g.get('class') for g in groups}, {f's{i}' for i in range(len(diagram.steps))})
                    for g in groups:
                        self.assertEqual(g.get('opacity'), '1' if g.get('class') == f's{k}' else '0.15')

    def test_marker_ids_unique_across_renders(self):
        ids = []
        for diagram in course_diagrams.ALL:
            for step in [None, *range(len(diagram.steps))]:
                root = ET.fromstring(strip_style(diagram.render(step)))
                ids += [m.get('id') for m in root.iter(f'{SVG}marker')]
        self.assertEqual(len(ids), len(set(ids)))

    def test_out_of_range_step_rejected(self):
        with self.assertRaises(ValueError):
            course_diagrams.DRAIN_FLOW.render(4)


if __name__ == '__main__':
    unittest.main()
