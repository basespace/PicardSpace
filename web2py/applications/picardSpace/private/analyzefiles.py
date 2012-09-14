import time
while True:
    for row in db(db.analysis_queue.status=='pending').select():

        # get queued app result from db
        # note: assuming we're analyzing a single file per app result, for now
        f_row = db(db.bs_file.app_result_id==row.app_result_id).select().first()

        f = AnalysisInputFile(
            app_result_id=f_row.app_result_id,
            app_session_id=f_row.app_session_id,
            file_num=f_row.file_num,
            file_name=f_row.file_name,
            local_path=f_row.local_path)

        # create new AppResult object and analyze downloaded File
        new_als = AppResult(
            app_result_id=row.app_result_id,
            app_session_id=f_row.app_session_id,
            project_num=f_row.app_result_id.project_num,
            app_result_name=f_row.app_result_id.app_result_name,
            app_result_num=f_row.app_result_id.app_result_num,
            description=f_row.app_result_id.description,
            status=f_row.app_result_id.status)
        # TODO add try except
        fb = new_als.run_analysis_and_writeback(f)

        # update analysis queue with analysis feedback
        row.update_record(status=fb.status)
        row.update_record(message=fb.message)

        db.commit()
    time.sleep(5) # check every x seconds

#python web2py.py -S picardSpace -M -N -R applications/picardSpace/private/analyzefiles.py
