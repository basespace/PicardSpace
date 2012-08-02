import time
while True:
    for row in db(db.analysis_queue.status=='pending').select():

        als_file = AnalysisInputFile(row.bs_file_id)
        if als_file.run_analysis_and_writeback():
        #if AnalysisInputFile.run_analysis_and_writeback(bs_file_id=row.bs_file_id):
            row.update_record(status='complete')
        else:
            row.update_record(status='failed')
        db.commit()
    time.sleep(5) # check every x seconds

#python web2py.py -S picardSpace -M -N -R applications/picardSpace/private/analyzefiles.py
