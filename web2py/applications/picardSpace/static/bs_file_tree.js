$(document).ready( function() {    
    $('#file_chooser').fileTree({ root: '/home', script: '/picardSpace/default/dirlist' }, function(file) {
        alert(file);
    });
});
