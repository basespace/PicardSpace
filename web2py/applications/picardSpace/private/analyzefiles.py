import time
while True:
    for row in db(db.analysis_queue.status=='pending').select():

        # query db for file to analyze, access token, project to writeback to
        f_row = db(db.bs_file.id==row.bs_file_id).select().first()

        f = File(
#            analysis_id=f_row.analysis_id,
            app_session_id=f_row.app_session_id,
            file_num=f_row.file_num,
            file_name=f_row.file_name,
            local_path=f_row.local_path)

        app_ssn_row = db(db.app_session.id==f.app_session_id).select().first()
        user_row = db(db.auth_user.id==app_ssn_row.user_id).select().first()

        # create new Analysis and analyze downloaded File
        new_als = Analysis(access_token=user_row.password, 
            project_num=app_ssn_row.project_num,
            app_action_num=app_ssn_row.app_action_num)
        fb = new_als.run_analysis_and_writeback(f)

        # update analysis queue with analysis feedback
        row.update_record(status=fb.status)
        row.update_record(message=fb.message)

        db.commit()
    time.sleep(5) # check every x seconds

#python web2py.py -S picardSpace -M -N -R applications/picardSpace/private/analyzefiles.py
