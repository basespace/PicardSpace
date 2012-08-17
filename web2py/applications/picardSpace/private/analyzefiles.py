import time
while True:
    for row in db(db.analysis_queue.status=='pending').select():

        f_row = db(db.bs_file.id==row.bs_file_id).select().first()

        f = File(analysis_id=f_row.analysis_id,
            file_num=f_row.file_num,
            file_name=f_row.file_name,
            local_path=f_row.local_path)

        als_row = db(db.analysis.id==f.analysis_id).select().first()

        als = Analysis(access_token=als_row.access_token,
            project_num=als_row.project_num,
            analysis_name=als_row.analysis_name,
            analysis_num=als_row.analysis_num,
            app_action_num=als_row.app_action_num)

        #als_row = db(db.analysis.id==f.analysis_id).select().first()
        #project_num = als_row.project_num
        #access_token = als_row.access_token

        new_als = Analysis(access_token=als.access_token, 
            project_num=als.project_num,
            app_action_num=als.app_action_num)
        fb = new_als.run_analysis_and_writeback(f)
        #als = Analysis(row.bs_file_id)
        #fb = als.run_analysis_and_writeback()
        row.update_record(status=fb.status)
        row.update_record(message=fb.message)

        db.commit()
    time.sleep(5) # check every x seconds

#python web2py.py -S picardSpace -M -N -R applications/picardSpace/private/analyzefiles.py
