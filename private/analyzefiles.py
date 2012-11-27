import time
from picardSpace import AnalysisInputFile, AppResult

while True:
    for row in db(db.analysis_queue.status=='pending').select():

        # get queued app result from db
        # note: assuming we're analyzing a single file per app result, for now
        ar_row = db(db.app_result.id==row.app_result_id).select().first()
        f_row = db(db.bs_file.app_result_id==row.app_result_id).select().first()

        f = AnalysisInputFile(
            app_result_id=row.app_result_id,
            #app_session_id=f_row.app_session_id,
            file_num=f_row.file_num,
            file_name=f_row.file_name,
            local_path=f_row.local_path)

        # create AppResult object to analyze downloaded File
        new_als = AppResult(
            app_result_id=row.app_result_id,
            app_session_id=ar_row.app_session_id,
            project_num=ar_row.project_num,
            app_result_name=ar_row.app_result_name,
            app_result_num=ar_row.app_result_num,
            status=ar_row.status)
        # run analysis and writeback results to BaseSpace
        try:
            fb = new_als.run_analysis_and_writeback(f)
            status = fb.status
            message = fb.message
        except Exception as e:
            # TODO print to log file
            print "Error: {0}".format(str(e))
            status = 'error'
            message = str(e)
        # update analysis queue with analysis feedback
        row.update_record(status=status)
        row.update_record(message=message)

        db.commit()
    time.sleep(5) # check every x seconds

#python web2py.py -S PicardSpace -M -R applications/PicardSpace/private/analyzefiles.py
