$(document).ready( function() {    
    $('#file_chooser').fileTree({ root: '/home', script: '/PicardSpace/default/browse_bs_app_results' }, function(file) {
        window.location('none');
        //TODO window.location('/PicardSpace/default/confirm_analysis_inputs');
        //alert(file);
    });
});
