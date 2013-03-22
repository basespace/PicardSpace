PicardSpace
===========

A website that runs Picard tools for BaseSpace.


Setup
=====
1. Download the BaseSpace python SDK

        git clone https://github.com/basespace/basespace-python-sdk.git
        cd basespace-python-sdk/src
        sudo python setup.py install
        or
        python setup.py install --prefix=/in/your/PYTHONPATH

2. Download and unzip web2py Source Code (download Current version. If on Mac OSX, don't download the pre-built Mac application.

        wget http://www.web2py.com/examples/static/web2py_src.zip
        unzip web2py_src.zip

3. Clone this PicardSpace repository into the web2py applications directory.

        cd web2py/applications
        git clone https://github.com/basespace/PicardSpace.git


4. Start web2py (and the web2py Scheduler), first navigating to the main 'web2py' directory. A web browser should launch with address localhost:8000).

        cd ..
        python web2py.py -K PicardSpace -X

5. Register your new PicardSpace app on the BaseSpace dev portal (developer.basespace.illumina.com) with these settings:
App Launch Location: Projects
Home Page: http://localhost:8000/PicardSpace
Redirect URI: http://localhost:8000/PicardSpace/default/handle_redirect_uri

6. Go to baseSpace.illumina.com and launch your new app from any Project that contains an AppResult with a small BAM file.


