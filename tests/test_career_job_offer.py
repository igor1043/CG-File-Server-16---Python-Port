import struct
import unittest
import zlib
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
from test_career_overlay import container
from server16_py.career_save_worker import (JOB_OFFER_MARKER,job_offer_offset,
    read_job_offer,prepare_job_offer,blocks)
from server16_py.career_feedback import CareerFeedback
from server16_py.career_service import prepare_request


def fixture():
    data=bytearray(container()+b'jo002\0'+struct.pack('<11i',*([-1]*7+[0,-1,-1,-1]))+b'pj001\0')
    struct.pack_into('<I',data,132,zlib.crc32(data[160:]))
    return bytes(data)


class JobOfferTests(unittest.TestCase):
    def make_save(self):
        def row(**data):return SimpleNamespace(GetIntField=data.__getitem__)
        context={'userid':0,'club_id':1043,'player_id':None,'budget':35599420}
        save=SimpleNamespace(data=fixture(),context=lambda:dict(context))
        save.one=lambda table,*args: row(**({'level':1} if table=='leagues' else {'wage':38000} if table=='career_managerinfo' else {}))
        save.rows=lambda table: [row(currdate=20260409)] if table=='career_calendar' else [row(teamid=383,leagueid=7,secondarytable=0)]
        from server16_py.career_save_worker import fingerprint
        request={'team_id':383,'league_id':7,'context':context,'fingerprint':fingerprint(save.data)}
        return save,request

    def test_offer_preserves_all_databases_and_stages_native_dispatch(self):
        save,request=self.make_save();original=save.data
        result=prepare_job_offer(save,request)
        offset=job_offer_offset(result)
        self.assertEqual(len(result),len(original));blocks(result)
        self.assertEqual(read_job_offer(result),{'team_id':383,'league_id':7,'date':20260409,
            'wage':38000,'source_club':1043,'dispatch_pending':True})
        self.assertEqual(result[160:offset+6],original[160:offset+6])
        self.assertEqual(result[offset+50:],original[offset+50:])
        self.assertEqual(save.context()['club_id'],1043)

    def test_existing_offer_or_application_cannot_be_overwritten(self):
        for index,value in ((0,598),(8,383),(9,38000),(10,4)):
            save,request=self.make_save();data=bytearray(save.data)
            struct.pack_into('<i',data,job_offer_offset(data)+6+index*4,value)
            struct.pack_into('<I',data,132,zlib.crc32(data[160:]));save.data=bytes(data)
            from server16_py.career_save_worker import fingerprint
            request['fingerprint']=fingerprint(save.data)
            with self.assertRaisesRegex(ValueError,'andamento'):prepare_job_offer(save,request)

    def test_unknown_or_ambiguous_serialization_is_rejected(self):
        with self.assertRaises(ValueError):job_offer_offset(container())
        with self.assertRaises(ValueError):job_offer_offset(fixture()+b'jo002\0')
        with self.assertRaises(ValueError):job_offer_offset(fixture()[:-6]+b'wrong!')

    def test_context_and_league_mismatch_are_rejected(self):
        save,request=self.make_save();request['context']=dict(request['context'],club_id=598)
        with self.assertRaisesRegex(ValueError,'contexto'):prepare_job_offer(save,request)
        save,request=self.make_save();request['league_id']=83
        with self.assertRaisesRegex(ValueError,'divisão'):prepare_job_offer(save,request)

    def test_fast_preparation_uses_verified_seed_and_never_reopens_the_databases(self):
        save,request=self.make_save()
        expected=prepare_job_offer(save,request)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'DATA';path.write_bytes(save.data)
            output=Path(tmp)/'prepared_DATA'
            request.update(action='job_offer',path=str(path),output=str(output),
                           job_offer_seed={'date':20260409,'wage':38000})
            with patch('server16_py.career_service.run_worker') as worker:
                result=prepare_request(tmp,request);worker.assert_not_called()
            self.assertEqual(output.read_bytes(),expected)
            self.assertEqual(result['context'],save.context())
            self.assertEqual(path.read_bytes(),save.data)
            path.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'mudou'):prepare_request(tmp,request)

    def test_interrupted_preparation_recovery_rejects_unrelated_payload_changes(self):
        save,request=self.make_save();expected=prepare_job_offer(save,request)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'DATA';path.write_bytes(save.data)
            output=Path(tmp)/'prepared_DATA';output.write_bytes(expected)
            request.update(action='job_offer',path=str(path),output=str(output))
            with patch('server16_py.career_service.run_worker') as worker:
                result=prepare_request(tmp,request);worker.assert_not_called()
            self.assertEqual(result['job_offer']['team_id'],383)
            changed=bytearray(expected);changed[200]^=1
            struct.pack_into('<I',changed,132,zlib.crc32(changed[160:]));output.write_bytes(changed)
            with patch('server16_py.career_service.run_worker',return_value={'fallback':True}) as worker:
                self.assertEqual(prepare_request(tmp,request),{'fallback':True});worker.assert_called_once()

    def test_feedback_deduplicates_request_stages_without_using_real_windows_or_audio(self):
        app=SimpleNamespace(memory=SimpleNamespace(process_id=1234),log=Mock())
        feedback=CareerFeedback(app)
        with patch('server16_py.career_feedback.native_notice',return_value=True) as notice, \
             patch('server16_py.career_feedback.play_sound') as sound:
            feedback.show('prepared','Saia do save','abc')
            feedback.show('prepared','Saia do save','abc')
            feedback.show('applying','Aguarde','abc')
            feedback.show('done','Aplicado','abc')
            self.assertEqual(notice.call_count,3)
            self.assertEqual(sound.call_args_list,[unittest.mock.call('prepared'),unittest.mock.call('done')])


if __name__=='__main__':unittest.main()
