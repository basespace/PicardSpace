# -*- coding: utf-8 -*-
import os.path
import re
from picardSpace import File


def view_textfile():
    """
    Display the contents of a local text file (up to 50K lines)
    """
    # edit file info here    
    local_dir = 'path/to/file/'
    file_name = 'file.bam' + current.file_ext['mult_metrics_stderr']
    
    ret = dict(back="", file_name="", file_contents="", err_msg="")    
    ret['back'] = ""
    
    f = File(app_result_id=None,
             file_name= file_name,
             file_num=None,
             local_path = os.path.join(local_dir, file_name))
    if f:
        ret['file_name'] = f.file_name
        with open(f.local_path, "r") as FH:
            cnt = 0
            for line in FH:
                ret['file_contents'] += line
                cnt += 1
                # don't display too many lines
                if cnt > 50000:
                    ret['file_contents'] += '(truncated)'
                    break
    return ret


def view_alignment_metrics():
    """
    Display picard's alignment metrics
    """
    # edit local file info here
    local_dir = 'path/to/file/'
    file_name = 'file.bam' + current.file_ext['aln_txt']
    
    ret = dict(aln_tbl="", hdr="", sample_name="", sample_num="", 
               input_file_name="", input_project_name="", 
               input_app_result_name="", output_app_result_name="", 
               output_project_name="", ar_back="",
               input_project_href="", output_project_href="",
               mult_metrics_stderr="",
               qual_by_cycle_txt="", qual_by_cycle_pdf="", qual_by_cycle_stderr="",
               qual_dist_txt="", qual_dist_pdf="", qual_dist_stderr="",
               gc_bias_txt="", gc_bias_pdf="", gc_bias_summary="", gc_bias_stderr="",
               insert_size_txt="", insert_size_hist="", insert_size_stderr="",
               err_msg="")
    ret['aln_tbl'] = [["data not available"]]
        
    # get 'back' url of view results page
    if (request.vars['ar_back']):
        ret['ar_back'] = request.vars['ar_back']
    else:
        ret['ar_back'] = URL('view_results')        
        
    # get alignment metrics table
    f = File(app_result_id = None,
                    file_name = file_name,
                    file_num = None,
                    local_path = os.path.join(local_dir, file_name))     
    if f:
        # read local file into array (for display in view)
        aln_tbl = []
        with open( f.local_path, "r") as ALN_QC:

            # get picard output header - collect lines finding line starting with 'CATEGORY'
            line = ALN_QC.readline()
            while line and not re.match("CATEGORY", line):
                ret['hdr'] += line
                line = ALN_QC.readline()
            # get picard metric data (and table headings)
            if line:
                aln_tbl.append(line.rstrip().split("\t"))
                for line in ALN_QC:
                    if line.rstrip():
                        aln_tbl.append(line.rstrip().split("\t"))
                # transpose list (for viewing - so it is long instead of wide)(now its a tuple)
                ret['aln_tbl'] = zip(*aln_tbl)                            
    return ret


def view_qual_by_cycle_metrics():
    """
    Display picard's quality by cycle metrics
    """
    # edit local file info here
    local_dir = 'path/to/file/'
    file_name = 'file.bam' + current.file_ext['qual_by_cycle_txt']
    
    ret = dict(back = "", data_tbl="", hdr="", sample_name="", err_msg="")    
    ret['data_tbl'] = [["data not available"]]    
    ret['back'] = "" 
            
    # get alignment metrics table
    f = File(app_result_id = None,
                    file_name = file_name,
                    file_num = None,
                    local_path = os.path.join(local_dir, file_name))     
    if f:
        # read local file into array (for display in view)
        data_tbl = []
        with open( f.local_path, "r") as QC:

            # get picard output header
            line = QC.readline()
            while line and not re.match("CYCLE", line):
                ret['hdr'] += line
                line = QC.readline()
            # get picard metric data (and table headings)
            if line:
                data_tbl.append(line.rstrip().split("\t"))
                for line in QC:
                    if line.rstrip():
                        data_tbl.append(line.rstrip().split("\t"))
                ret['data_tbl'] = data_tbl                
    return ret


def view_qual_dist_metrics():
    """
    Display picard's quality distribution metrics
    """
    # edit local file info here
    local_dir = 'path/to/file/'
    file_name = 'file.bam' + current.file_ext['qual_dist_txt']
    
    ret = dict(back = "", data_tbl="", hdr="", sample_name="", err_msg="")    
    ret['data_tbl'] = [["data not available"]]    
    ret['back'] = ""     
            
    # get alignment metrics table
    f = File(app_result_id = None,
                    file_name = file_name,
                    file_num = None,
                    local_path = os.path.join(local_dir, file_name))     
    if f:
        # read local file into array (for display in view)
        data_tbl = []
        with open( f.local_path, "r") as QC:

            # get picard output header
            line = QC.readline()
            while line and not re.match("QUALITY", line):
                ret['hdr'] += line
                line = QC.readline()
            # get picard metric data (and table headings)
            if line:
                data_tbl.append(line.rstrip().split("\t"))
                for line in QC:
                    if line.rstrip():
                        data_tbl.append(line.rstrip().split("\t"))
                ret['data_tbl'] = data_tbl                
    return ret


def view_gc_bias_metrics():
    """
    Display picard's gc-bias summary and histogram metrics
    """
    # edit local file info here
    local_dir = 'path/to/file/'
    sum_file_name = 'file.bam' + current.file_ext['gc_bias_summary']
    hist_file_name = 'file.bam' + current.file_ext['gc_bias_txt']
    
    ret = dict(back = "", sum_tabl="", data_tbl="", hdr="", sample_name="", err_msg="")        
    ret['sum_tbl'] = [["data not available"]]
    ret['data_tbl'] = [["data not available"]]    
    ret['back'] = ""     
    
    # first parse summary metrics file (then histogram data file)
    ret['hdr'] += 'GC Bias Summary Values:\n'            
    f = File(app_result_id = None,
                    file_name = sum_file_name,
                    file_num = None,
                    local_path = os.path.join(local_dir, sum_file_name))     
    if f:
        # read local file into array (for display in view)
        sum_tbl = []
        with open( f.local_path, "r") as QC:

            # get picard output header
            line = QC.readline()
            while line and not re.match("WINDOW_SIZE", line):
                ret['hdr'] += line
                line = QC.readline()
            # get picard metric data (and table headings)
            if line:
                sum_tbl.append(line.rstrip().split("\t"))
                for line in QC:
                    if line.rstrip():
                        sum_tbl.append(line.rstrip().split("\t"))
                ret['sum_tbl'] = sum_tbl                


    # parse histogram data file
    ret['hdr'] += '\nGC-Bias Histogram Values:\n'
    hf = File(app_result_id = None,
              file_name = hist_file_name,
              file_num = None,
              local_path = os.path.join(local_dir, hist_file_name))     
    if hf:
        # read local file into array (for display in view)
        data_tbl = []
        with open( hf.local_path, "r") as QC:

            # get picard output header
            line = QC.readline()
            while line and not re.match("GC", line):
                ret['hdr'] += line
                line = QC.readline()
            # get picard metric data (and table headings)
            if line:
                data_tbl.append(line.rstrip().split("\t"))
                for line in QC:
                    if line.rstrip():
                        data_tbl.append(line.rstrip().split("\t"))
                ret['data_tbl'] = data_tbl                
    return ret


def view_insert_size_metrics():
    """
    Display picard's insert size metrics
    """
    # edit local file info here
    local_dir = 'path/to/file/'
    file_name = 'file.bam' + current.file_ext['insert_size_txt']

    ret = dict(back = "", hist_tbl="", data_tbl="", hdr="", sample_name="", err_msg="")    
    ret['hist_tbl'] = [["data not available"]]
    ret['data_tbl'] = [["data not available"]]        
    ret['back'] = ""
        
    # get alignment metrics table
    f = File(app_result_id = None,
                    file_name = file_name,
                    file_num = None,
                    local_path = os.path.join(local_dir, file_name))     
    if f:
        # read local file into array (for display in view)
        hist_tbl = []
        data_tbl = []
        with open( f.local_path, "r") as QC:

            # get picard output header
            line = QC.readline()
            while line and not re.match("MEDIAN_INSERT_SIZE", line):
                ret['hdr'] += line
                line = QC.readline()
            # get picard metric data (and table headings)
            if line:                
                data_tbl.append(line.rstrip().split("\t")) # summary headers
                line = QC.readline()
                if line:
                    data_tbl.append(line.rstrip().split("\t")) # summary data line
                    line = QC.readline()
                    ret['data_tbl'] = zip(*data_tbl)
                    while line and not re.match("insert_size", line): # add to header
                        ret['hdr'] += line
                        line = QC.readline()
                    if line:
                        hist_tbl.append(line.rstrip().split("\t")) # histogram header
                        for line in QC:
                            if line.rstrip():
                                hist_tbl.append(line.rstrip().split("\t")) # histogram data
                ret['hist_tbl'] = hist_tbl                
    return ret

