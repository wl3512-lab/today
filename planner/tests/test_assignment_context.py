import unittest
from unittest import mock
import assignment_context as ac

class ContextTests(unittest.TestCase):
    def test_anchor_stops_before_the_next_assignment(self):
        html='<div id="ex3"><h2>Nine photos</h2><div>Include captions</div></div><div id="ex4">Unrelated essay</div>'
        self.assertEqual(ac.section(html,'ex3',limit=60000).split(), 'Nine photos Include captions'.split())

    def test_missing_anchor_does_not_return_another_assignments_page(self):
        with mock.patch.object(ac,'fetch',return_value='<div id="ex4">Unrelated essay</div>'):
            self.assertEqual(ac.page_text('https://profsite.example.org/class#ex3'),'')

    def test_source_limit_is_per_call(self):
        html='<div id="ex3">'+('a'*3000)+'RUBRIC</div>'
        with mock.patch.object(ac,'fetch',return_value=html):
            self.assertNotIn('RUBRIC',ac.page_text('https://profsite.example.org/class#ex3'))
            self.assertIn('RUBRIC',ac.page_text('https://profsite.example.org/class#ex3',limit=60000))
            self.assertEqual(ac.PAGE_CHARS,2500)

    def test_schedule_matches_homework_one_not_ten(self):
        with mock.patch.object(ac,'fetch',return_value='Homework 1,First\nHomework 10,Tenth\n'):
            self.assertEqual(ac.sheet_rows('https://docs.google.com/spreadsheets/d/abc/pubhtml','Homework 1'),['Homework 1 | First'])
