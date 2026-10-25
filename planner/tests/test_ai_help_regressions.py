import copy
import json
import os
import tempfile
import unittest
from unittest import mock
import ai_help
import briefs
from test_ai_help import COURSE, DEADLINE, LEDGER, Done

class HelperRegressions(unittest.TestCase):
    def test_full_assignment_id_separates_same_title(self):
        other = copy.deepcopy(DEADLINE)
        other['priority']['id'] = 'abc123999999'
        self.assertNotEqual(ai_help.slug(COURSE, DEADLINE), ai_help.slug(COURSE, other))

    def test_missing_id_does_not_match_unidentified_assignment(self):
        self.assertEqual(ai_help.find({'courses':[{'key':'a','deadlines':[{'title':'x'}]}]},'a',None),(None,None))

    def test_changed_source_failure_cannot_reuse_old_text(self):
        with tempfile.TemporaryDirectory() as root:
            folder=ai_help.prepare(COURSE, DEADLINE, LEDGER, root=root, gather=lambda *a:'ev',source=lambda d:'OLD RUBRIC')
            other=dict(DEADLINE,url='https://example.invalid/new')
            ai_help.prepare(COURSE,other,LEDGER,root=root,gather=lambda *a:'new ev',source=lambda d:'')
            with open(os.path.join(folder,'CONTEXT.md')) as f: self.assertIn('could not be fetched',f.read())
            self.assertFalse(os.path.exists(os.path.join(folder,ai_help.SOURCE)))

    def test_malformed_cli_json_is_error_not_exception(self):
        with tempfile.TemporaryDirectory() as folder:
            for payload in ([],None,{'result':22},{'result':'ok'}):
                r=ai_help.chat(folder,'question',exe='/fake/claude',runner=lambda *a,**k:Done(json.dumps(payload)))
                self.assertEqual(r['messages'][-1]['role'],'error')
                self.assertFalse(r['ok'])

    def test_resumed_turn_receives_updated_context(self):
        with tempfile.TemporaryDirectory() as folder:
            ai_help._atomic(os.path.join(folder,'CONTEXT.md'),'Unique assignment: build an image grid. Current requirement: four images.')
            ai_help._write(folder,ai_help.SESSION,{'id':'session-one'})
            calls=[]
            def run(cmd,**kw):
                calls.append(cmd);return Done(json.dumps({'result':'reply','session_id':'session-one'}))
            ai_help.chat(folder,'next?',exe='/fake/claude',runner=run)
            self.assertIn('Current requirement: four images',' '.join(calls[0]))

    def test_progress_rejects_string_as_completed_steps(self):
        self.assertEqual(ai_help.clean_progress({'done':'wrong type'})['done'],[])

class BriefRegressions(unittest.TestCase):
    def test_malformed_model_steps_do_not_crash_sync(self):
        for steps in ({"name":"wrong shape"}, [{"name":"x","minutes":"inf"}]):
            self.assertEqual(briefs.validate(json.dumps([{"id":"x","gist":"g","steps":steps}])), {})

    def test_stale_brief_is_not_attached_when_refresh_fails(self):
        d = dict(DEADLINE)
        c = dict(COURSE, deadlines=[d])
        with mock.patch('briefs.load',return_value={d['priority']['id']:{'gist':'old generic','steps':[],'textHash':'old'}}), mock.patch('briefs.ask',return_value={}):
            briefs.apply([c], gather=lambda *a:'')
        self.assertNotIn('brief',d)

    def test_hash_changes_when_assignment_materials_change(self):
        self.assertNotEqual(briefs._text_hash(dict(DEADLINE,materials=[{'title':'Reading A'}])),briefs._text_hash(dict(DEADLINE,materials=[{'title':'Reading B'}])))

    def test_each_assignment_is_requested_independently(self):
        calls=[]
        def backend(prompt):
            calls.append(prompt)
            return '[]'
        with mock.patch('briefs._ask_claude',side_effect=backend),mock.patch('briefs._ask_itp',return_value='[]'):
            briefs.ask([{'id':'one','title':'Photo essay'},{'id':'two','title':'Statistics worksheet'}])
        self.assertEqual(len(calls),2)
        self.assertNotIn('Statistics worksheet',calls[0])

    def test_ambiguous_title_does_not_share_body(self):
        courses=[{'key':k,'deadlines':[{'title':'Homework 1','due':'2099-01-01','priority':{'id':k}}]} for k in ('a','b')]
        with mock.patch('briefs.load',return_value={}),mock.patch('briefs.ask',return_value={}) as ask:
            briefs.apply(courses,bodies={'Homework 1':'ONLY FOR A'},gather=lambda *a:'')
        self.assertTrue(all(not it['body'] for it in ask.call_args.args[0]))
