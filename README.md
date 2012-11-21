PicardSpace
===========

A website that runs Picard tools for BaseSpace.


Setup
=====
1. Download and unzip web2py for linux (download Current version, Source Code).
    wget http://www.web2py.com/examples/static/web2py_src.zip
    unzip web2py_src.zip

2. Clone this PicardSpace repository into the web2py applications directory.
    cd web2py/applications
    git clone https://github.com/basespace/PicardSpace.git

3. Start web2py, first navigating to the main 'web2py' directory. A web browser should launch with address localhost:8000).
    cd ..
    python web2py.py

4. Start the download and analysis scripts:
    python web2py.py -S PicardSpace -M -R applications/PicardSpace/private/downloadfiles.py &
    python web2py.py -S PicardSpace -M -R applications/PicardSpace/private/analyzefiles.py &

5. Register your new PicardSpace app on the BaseSpace dev portal (developer.basespace.illumina.com) with these settings:
App Launch Location: Projects
Home Page: localhost:8000/PicardSpace
Redirect URI: localhost:8000/PicardSpace

6. Go to BaseSpace.com and launch your new app from any Project that contains an AppResult with a BAM file.


Known Issues
============
1. Files downloaded from BaseSpace and files output by Picard aren't cleaned up (deleted).
