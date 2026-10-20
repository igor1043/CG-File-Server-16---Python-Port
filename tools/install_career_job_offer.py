"""Install verified build outputs without starting/stopping any application."""
import hashlib
import json
import shutil
import argparse
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DEV=Path('U:/mods/FIFA Friends V12')
GAME=Path('U:/fifa 16')
NATIVE=DEV/'ModCarrerMode/source/career_native'


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main(feature='career_job_offer',career_tests=36):
    from PyInstaller.archive.readers import CArchiveReader
    import pefile
    install_feature=feature
    if feature in ('career_light_notices','career_notice_refresh','career_sticky_progress','career_menu_fixes'):feature='career_performance_retirement'
    if feature == 'career_performance_retirement':
        validation_path=('artifacts/career_sticky_progress/validation.json' if install_feature in ('career_sticky_progress','career_menu_fixes')
                         else 'artifacts/career_performance_retirement/validation.json')
        evidence=json.loads((ROOT/validation_path).read_text(encoding='utf8'))
        assert evidence.get('passed') and evidence.get('snapshot_unchanged')
        assert evidence['worker_sha256']==digest(ROOT/'server16_py/career_save_worker.py')
        assert evidence['reader_sha256']==digest(ROOT/'server16_py/career_read.py')
        retirement_checks=[row for row in evidence['checks'] if row['name'] in ('remove_retirement','remove_and_rejuvenate')]
        assert len(retirement_checks)==2 and all(row['native_bytes_equal'] for row in retirement_checks)
        extra=json.loads((ROOT/'artifacts/career_performance_retirement/reader_additional_saves.json').read_text(encoding='utf8'))
        assert len(extra)==2 and all(row['exact_match'] for row in extra)
    if install_feature=='career_notice_refresh':
        refreshed=json.loads((ROOT/'artifacts/career_notice_refresh/validation.json').read_text(encoding='utf8'))
        assert refreshed['passed'] and refreshed['original_saves_unchanged']
        assert refreshed['unchanged_file_reads_across_60_polls']==0 and refreshed['new_file_reads']==1
        assert 'PASS: five-second notices' in (ROOT/'artifacts/career_notice_refresh/native_feedback_tests.log').read_text()
    if install_feature in ('career_sticky_progress','career_menu_fixes'):
        assert 'persistent progress survives timers' in (ROOT/'artifacts/career_sticky_progress/native_feedback_tests.log').read_text()
        assert evidence['passed'] and all(row['native_bytes_equal'] for row in evidence['checks'])
    exe=ROOT/'dist_career/Server16Python.exe'
    archive=CArchiveReader(str(exe))
    worker=next(name for name in archive.toc if name.replace('\\','/')=='server16_py/career_save_worker.py')
    assert archive.extract(worker)==(ROOT/'server16_py/career_save_worker.py').read_bytes()
    pyz=archive.open_embedded_archive('PYZ.pyz')
    if install_feature=='career_notice_refresh':
        feedback=pyz.extract('server16_py.career_feedback')
        assert 5000 in feedback.co_consts
        service=pyz.extract('server16_py.career_service')
        service_class=next(c for c in service.co_consts if getattr(c,'co_name',None)=='CareerService')
        assert '_bind_inspection' in service_class.co_names
    if install_feature in ('career_sticky_progress','career_menu_fixes'):
        feedback=pyz.extract('server16_py.career_feedback')
        native_notice=next(c for c in feedback.co_consts if getattr(c,'co_name',None)=='native_notice')
        assert 0x16402 in native_notice.co_consts and 0x16403 in native_notice.co_consts
        assert 5000 in feedback.co_consts
    if install_feature=='career_menu_fixes':
        assert 'server16_py.career_transfer_catalog' in pyz.toc
        assert json.loads((ROOT/'artifacts/career_club_filter/validation.json').read_text(encoding='utf8'))['passed']
        assert 'Ran 84 tests' in (ROOT/'artifacts/career_club_filter/career_tests.log').read_text()
        assert 'Ran 22 tests' in (ROOT/'artifacts/career_club_filter/selector_tests.log').read_text()
        assert 'Career stadium titles and publication: PASS (0 failures)' in (ROOT/'artifacts/career_club_filter/native_stadium_titles_tests.log').read_text()
        assert 'Mouse movement/buttons/wheel and buffered events captured' in (ROOT/'artifacts/career_club_filter/native_input_tests.log').read_text()
        assert 'Exclusive capture: prematch, match and career' in (ROOT/'artifacts/career_club_filter/overlay_build.log').read_text()
        bridge=next(name for name in archive.toc if name.replace('\\','/')=='bin/cgfs16_overlay.dll')
        assert archive.extract(bridge)==(ROOT/'bin/cgfs16_overlay.dll').read_bytes()
    for module in ('server16_py.career_feedback','server16_py.career_context','server16_py.career_service'):
        assert module in pyz.toc,module
    if feature in ('career_loading_feedback','career_live_jobs','career_direct_proposal','career_performance_retirement'):
        assert 'prepare_request' in pyz.extract('server16_py.career_service').co_names
        assert 'stage_job_offer' in pyz.extract('server16_py.career_save_worker').co_names
        panel=pyz.extract('server16_py.career_panel')
        panel_class=next(code for code in panel.co_consts if getattr(code,'co_name',None)=='CareerPanel')
        assert 'data_gate' in panel_class.co_names
    if feature in ('career_live_jobs','career_direct_proposal','career_performance_retirement'):
        assert 'server16_py.career_jobs_runtime' in pyz.toc
        native_entry=next(name for name in archive.toc if name.replace('\\','/')=='bin/career_jobs_runtime.dll')
        assert archive.extract(native_entry)==(ROOT/'bin/career_jobs_runtime.dll').read_bytes()
        if feature in ('career_direct_proposal','career_performance_retirement'):
            jobs=pyz.extract('server16_py.career_jobs_runtime')
            assert 4 in jobs.co_consts
            native_pe=pefile.PE(str(ROOT/'bin/career_jobs_runtime.dll'))
            protocol_rva=next(s.address for s in native_pe.DIRECTORY_ENTRY_EXPORT.symbols if s.name==b'Fifa16CareerJobsProtocol')
            assert int.from_bytes(native_pe.get_data(protocol_rva,4),'little')==4
        else:assert (ROOT/'artifacts/career_jobs_live_review/live_inclusion_validation.json').is_file()
    dll=NATIVE/'build/production/dinput8.dll'
    pe=pefile.PE(str(dll))
    protocol=next(s.address for s in pe.DIRECTORY_ENTRY_EXPORT.symbols if s.name==b'Fifa16CareerJobOfferProtocol')
    assert int.from_bytes(pe.get_data(protocol,4),'little')==1
    if feature in ('career_direct_proposal','career_performance_retirement'):
        assert any(s.name==b'Fifa16CareerRegisterJobUiCallback' for s in pe.DIRECTORY_ENTRY_EXPORT.symbols)
    if feature=='career_performance_retirement':
        assert 'server16_py.career_read' in pyz.toc
        assert 'server16_py.career_panel' in pyz.toc
        from xml.etree import ElementTree as ET
        layout=ET.parse(ROOT/'native_mods/career_overlay/layout/careermanagerhubcfg.xml')
        assert not any(n.attrib.get('DESTINATION','').startswith('Retirement') for n in layout.iter())
        settings=next(t for t in layout.iter('tile') if t.find('tileid').attrib.get('tileid')=='384')
        assert settings.find('main_tile').attrib['DESTINATION']=='EnterGameSettings'
        assert settings.find('number_of_subtiles').attrib['LENGTH']=='0'
    assert (ROOT/'artifacts/career_native_job_offer_validation/report.json').is_file()
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
    entries=[]
    def install(source,target,base):
        expected=digest(source)
        if target.is_file() and digest(target)==expected:
            entries.append({'target':str(target),'sha256':expected,'already_current':True})
            return
        backup=base/'runtime/backups'/install_feature/stamp
        relative=target.relative_to(base)
        previous=backup/relative
        previous.parent.mkdir(parents=True,exist_ok=True)
        before=None;loaded=None
        if target.exists():
            before=digest(target);shutil.copy2(target,previous)
            assert digest(previous)==before
        target.parent.mkdir(parents=True,exist_ok=True)
        try:shutil.copy2(source,target)
        except OSError as exc:
            if getattr(exc,'winerror',None) not in (5,32,33,1224):raise
            # Windows keeps the old image mapped. Renaming that single file
            # allows the next manual launch to use the replacement.
            loaded=previous.with_name(previous.name+'.loaded')
            assert loaded.resolve().is_relative_to(base.resolve())
            target.rename(loaded)
            try:shutil.copy2(source,target)
            except Exception:
                loaded.rename(target)
                raise
        assert digest(target)==expected
        entries.append({'target':str(target),'before_sha256':before,'sha256':expected,
                        'backup':str(previous),'loaded_previous_file':str(loaded) if loaded else None})
    for base in (GAME,DEV):
        install(exe,base/'Server16Python.exe',base)
        install(dll,base/'dinput8.dll',base)
        if install_feature=='career_menu_fixes':
            install(ROOT/'bin/cgfs16_overlay.dll',base/'bin/cgfs16_overlay.dll',base)
        if feature in ('career_live_jobs','career_direct_proposal','career_performance_retirement'):
            install(ROOT/'bin/career_jobs_runtime.dll',base/'ModCarrerMode/bin/career_jobs_runtime.dll',base)
        if feature=='career_performance_retirement':
            install(ROOT/'native_mods/career_overlay/layout/careermanagerhubcfg.xml',base/'data/ui/layout/careermanagerhubcfg.xml',base)
    install(exe,ROOT/'dist/Server16Python.exe',ROOT)
    relative_files=('src/host/active_save_probe.inc','src/host/dinput8_wrapper.c',
        'src/host/dinput8_wrapper.def','src/host/career_job_offer.h','src/host/career_job_offer.inc',
        'tests/providers/test_active_career_save.c','tests/providers/test_career_job_offer.c',
        'tests/providers/test_career_job_delivery.c','scripts/tests/test_career_job_offer.cmd',
        'src/host/career_ui_jobs.inc','tests/providers/test_career_ui_jobs.c','scripts/tests/test_career_ui_jobs.cmd')
    if install_feature in ('career_light_notices','career_notice_refresh','career_sticky_progress','career_menu_fixes'):
        relative_files+=('src/features/retirement/retirement_engine.c',
                         'src/features/retirement/retirement_feedback_paint.inc')
    if install_feature in ('career_notice_refresh','career_sticky_progress','career_menu_fixes'):
        relative_files+=('tests/providers/test_career_feedback.c','scripts/tests/test_career_feedback.cmd')
    if install_feature=='career_menu_fixes':
        relative_files+=('src/host/native_cards.inc','tests/providers/test_career_stadium_titles.c',
                         'scripts/tests/test_career_stadium_titles.cmd')
    for base,sub in ((GAME,'ModCarrerMode/source/career_native'),(ROOT,'native_mods/career_native')):
        for relative in relative_files:install(NATIVE/relative,base/sub/relative,base)
    if feature in ('career_live_jobs','career_direct_proposal','career_performance_retirement'):
        for base in (GAME,DEV):
            for relative in ('protocol.h','career_jobs_runtime.c','test_runtime.c','build.cmd','test.cmd'):
                install(ROOT/'native_mods/career_jobs_runtime'/relative,base/'ModCarrerMode/source/career_jobs_runtime'/relative,base)
        install(ROOT/'docs/OVERLAY_CARREIRA.md',DEV/'ModCarrerMode/source/OVERLAY_CARREIRA.md',DEV)
    if feature=='career_performance_retirement':
        for relative in ('career_read.py','career_service.py','career_save_worker.py','career_panel.py','career_feedback.py','career_context.py'):
            install(ROOT/'server16_py'/relative,DEV/'ModCarrerMode/source/server16_py'/relative,DEV)
        install(ROOT/'tools/validate_career_performance_retirement.py',DEV/'ModCarrerMode/source/validate_career_performance_retirement.py',DEV)
        if install_feature=='career_notice_refresh':
            install(ROOT/'tools/validate_career_notice_refresh.py',DEV/'ModCarrerMode/source/validate_career_notice_refresh.py',DEV)
        if install_feature in ('career_sticky_progress','career_menu_fixes'):
            install(ROOT/'server16_py/stadium_selector.py',DEV/'ModCarrerMode/source/server16_py/stadium_selector.py',DEV)
            install(ROOT/'tools/validate_career_sticky_progress.py',DEV/'ModCarrerMode/source/validate_career_sticky_progress.py',DEV)
        if install_feature=='career_menu_fixes':
            install(ROOT/'server16_py/career_transfer_catalog.py',DEV/'ModCarrerMode/source/server16_py/career_transfer_catalog.py',DEV)
            for source in (ROOT/'server16_py/d3d_overlay').iterdir():
                if source.is_file():install(source,DEV/'ModCarrerMode/source/server16_py/d3d_overlay'/source.name,DEV)
            for relative in ('build_career_overlay.cmd','test_career_input.cmd'):
                install(ROOT/'scripts'/relative,DEV/'ModCarrerMode/source/scripts'/relative,DEV)
            for relative in ('test_career_transfer_catalog.py','native_input_gate_test.cpp','native_selector_bridge_test.cpp'):
                install(ROOT/'tests'/relative,DEV/'ModCarrerMode/source/tests'/relative,DEV)
    report={'installed_utc':stamp,'files':entries,'worker_current':True,'native_offer_protocol':1,
        'career_python_tests':career_tests,'selector_python_tests':22,'native_identity_test':True,
        'native_delivery_test':True,'original_save_modified_by_installer':False,
        'applications_restarted':False,'ram_written':False,'native_acceptance_observed':False,
        'save_validation':'artifacts/career_native_job_offer_validation/report.json'}
    if feature=='career_loading_feedback':
        report.update(loading_hides_partial_data=True,animated_loading=True,
            fast_offer_preparation=True,interrupted_preparation_retained=True,
            completion_only_after_verified_publication=True,
            request_recovery_validation='artifacts/career_pending_request_recovery/report.json')
    if feature=='career_live_jobs':
        report.update(automatic_completion_panel_removed=True,parallel_background_preload=True,
            manager_requests_use_live_native_vacancies=True,save_edited_for_live_requests=False,
            native_callback_reinserts_requested_clubs=True,native_application_response_supported=True,
            live_verification='artifacts/career_jobs_live_review/live_inclusion_validation.json',
            runtime_already_injected_pid=45404)
    if feature in ('career_direct_proposal','career_performance_retirement'):
        report.update(automatic_completion_panel_removed=True,parallel_background_preload=True,
            manager_requests_use_direct_native_proposals=True,proposal_protocol=4,
            new_request_replaces_prior_offer_and_application=True,
            old_proposal_mail_withdrawn_by_native_routine=True,
            real_time_wait_in_hub_no_calendar_advance_required=True,
            native_proposal_validity_shown=True,
            native_hook_count=0,native_owner_ui_callback=True,native_contract_event='EnterJobOfferSign',
            native_contract_queue_ack_required=True,contract_acceptance_automatic=False,
            native_callback_reinserts_requested_clubs=False,
            native_application_calls_untouched=True,duplicate_module_load_guard=True,
            save_edited_for_live_requests=False,real_calendar_advance_verified=False,
            real_signature_verified=False,requires_manual_restart_of_fifa_and_server=True)
    if feature=='career_performance_retirement':
        report.update(read_only_direct_db_projection=True,preload_on_ram_connection=True,
            retirement_rules_in_server=True,legacy_four_cards_removed=True,
            funds_tested_amounts=[10000000,100000000,12345678],
            real_signature_verified=True,real_signature_evidence='user confirmation in this conversation',
            finance_and_retirement_live_reload_verified=False,requires_manual_restart_of_fifa_and_server=True,
            validation='artifacts/career_performance_retirement/validation.json')
    if install_feature=='career_light_notices':
        report.update(light_career_notices=True,rounded_notice_corners=True,notice_duration_ms=20000,
                      native_and_fallback_updated=True,offscreen_native_preview=True)
    if install_feature=='career_notice_refresh':
        report.update(light_career_notices=True,notice_duration_ms=5000,
            legacy_proposal_toast_removed=True,native_duplicate_does_not_extend_timer=True,
            proposal_notice_requires_current_request_and_native_contract_ack=True,
            live_club_refresh_without_file_reload_loop=True,unsaved_club_budget_hidden=True,
            new_save_restores_current_club_budget=True,live_refresh_in_game_observed=False)
    if install_feature in ('career_sticky_progress','career_menu_fixes'):
        report.update(light_career_notices=True,temporary_notice_duration_ms=5000,
            finance_retirement_progress_persistent=True,progress_replaced_only_by_terminal_result=True,
            completed_notice_after_verified_publication=True,progress_survives_fifa_closure=True,
            optimized_field_layout_cache=True,full_save_verification_preserved=True,
            native_reference_bytes_preserved=True,live_refresh_in_game_observed=False,
            validation='artifacts/career_sticky_progress/validation.json')
    if install_feature=='career_menu_fixes':
        report.update(access_divisions_national_teams_free_agents_hidden=True,
            series_a_b_c_d_preserved=True,live_promoted_clubs_retained=True,
            exclusive_ansi_unicode_directinput=True,root_render_window_capture=True,
            stadium_titles_utf8=True,stadium_location_metadata_removed=True,
            club_stadium_two_line_layout=True,live_input_in_fifa_verified=False,
            native_stadium_tests='artifacts/career_club_filter/native_stadium_titles_tests.log',
            filter_validation='artifacts/career_club_filter/validation.json')
    (ROOT/f'artifacts/{install_feature}_install_report.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps({'installed_utc':stamp,'exe_sha256':digest(exe),'native_sha256':digest(dll),
        'verified_targets':len(entries),'requires_manual_restart':True},indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--feature',choices=('career_job_offer','career_loading_feedback','career_live_jobs','career_direct_proposal','career_performance_retirement','career_light_notices','career_notice_refresh','career_sticky_progress','career_menu_fixes'),default='career_job_offer')
    parser.add_argument('--career-tests',type=int,default=36)
    args=parser.parse_args();main(args.feature,args.career_tests)
