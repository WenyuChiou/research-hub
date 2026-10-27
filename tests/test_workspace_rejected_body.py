"""Non-socket sequencing/budget checks, not proof of Windows TCP reset cause."""
from email.message import Message
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from research_hub.workspace import server as module


class RejectedBodyTests(unittest.TestCase):
    def attempt(self, length='12', body=b'x' * 12, extra=(), cost=0.0, read_error=False, restore_error=False, timeout=15.0):
        events=[]; clock=[0.0]; state=[timeout]; consumed=[0]; reads=[]
        connection=Mock()
        connection.gettimeout.side_effect=lambda:state[0]
        def settimeout(value):
            if restore_error and value == timeout: raise OSError('Synthetic restore failure')
            state[0]=value
        connection.settimeout.side_effect=settimeout
        def read1(size):
            events.append('read');reads.append(size)
            if read_error:raise OSError('Synthetic read failure')
            if cost > state[0]:clock[0]+=state[0];raise TimeoutError('Synthetic slow body')
            clock[0]+=cost
            chunk=body[consumed[0]:consumed[0]+size];consumed[0]+=len(chunk);return chunk
        handler=module.WorkspaceHandler.__new__(module.WorkspaceHandler)
        handler.connection=connection;handler.close_connection=False
        handler.headers=Message();handler.headers['Host']='127.0.0.1:43210'
        if length is not None:handler.headers['Content-Length']=length
        for key,value in extra:handler.headers[key]=value
        handler.rfile=SimpleNamespace(read1=read1)
        handler.server=SimpleNamespace(csrf='synthetic',server_port=43210,_call=Mock())
        handler._reply=lambda status,body:events.append(('reply',status))
        original=handler._trusted_origin
        def decision():events.append('decision');return original()
        handler._trusted_origin=decision
        with patch.object(module,'time',SimpleNamespace(monotonic=lambda:clock[0]),create=True),patch.object(module.json,'loads',side_effect=AssertionError('Must not parse denied body')):
            handler.do_POST()
        self.assertEqual(events[0],'decision')
        self.assertEqual(events[-1],('reply',403))
        handler.server._call.assert_not_called()
        return handler,events,reads,consumed[0],clock[0],state[0]

    def test_bounded_denied_body_is_discarded_after_auth_decision_before_403(self):
        handler,events,reads,count,elapsed,timeout=self.attempt()
        self.assertEqual(count,12)
        self.assertEqual(events,['decision','read',('reply',403)])
        self.assertTrue(handler.close_connection)
        self.assertEqual(timeout,15)

    def test_ambiguous_or_large_framing_is_never_drained(self):
        cases=[(None,()),('-1',()),('65537',()),('1e2',()),('１２',()),('0',()),('9'*100,()),('12',(('Content-Length','12'),)),('12',(('Transfer-Encoding',''),))]
        for length,extra in cases:
            with self.subTest(length=length,extra=extra):
                handler,events,reads,count,elapsed,timeout=self.attempt(length=length,extra=extra)
                self.assertEqual(reads,[]);self.assertEqual(count,0)
                self.assertTrue(handler.close_connection)

    def test_maximum_bytes_and_absolute_deadline(self):
        handler,events,reads,count,elapsed,timeout=self.attempt('65536',b'x'*65536)
        self.assertEqual(count,65536);self.assertEqual(reads,[8192]*8)
        _,_,reads,count,elapsed,_=self.attempt('65536',b'x'*65536,cost=0.1)
        self.assertLessEqual(elapsed,0.25);self.assertLessEqual(len(reads),3)
        self.assertLess(count,65536)

    def test_tighter_timeout_eof_read_and_restore_failure_still_refuse(self):
        _,_,_,count,elapsed,timeout=self.attempt(cost=0.1,timeout=0.01)
        self.assertEqual(count,0);self.assertLessEqual(elapsed,0.01);self.assertEqual(timeout,0.01)
        for kwargs in ({'body':b''},{'read_error':True},{'restore_error':True}):
            with self.subTest(kwargs=kwargs):self.attempt(**kwargs)

    def test_wrong_origin_with_valid_csrf_still_denies_before_draining(self):
        handler,events,reads,count,elapsed,timeout=self.attempt(extra=(('Origin','https://example.invalid'),('X-CSRF-Token','synthetic')))
        self.assertEqual(count,12)
        self.assertEqual(events,['decision','read',('reply',403)])
        self.assertTrue(handler.close_connection)
